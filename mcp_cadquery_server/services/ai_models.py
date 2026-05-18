from __future__ import annotations

import os
import uuid
from typing import Callable

from ..schemas.ai_models import GenerateModelArgs, ListModelsArgs, ModifyModelArgs
from ..state import log
from .ai_generator import generate_cadquery_code, modify_cadquery_code
from .cadquery import _ensure_exportable_script, handle_execute_cadquery_script, handle_export_shape
from .model_store import (
    MODELS_DIR,
    list_models as store_list_models,
    load_latest_code,
    load_model,
    save_model,
    validate_model_id,
)


AI_WORKSPACE_DIR = os.path.expanduser("~/.mcp/mcp-cad/workspace")


def _first_execution_summary(execution_result: dict, shape_index: int) -> dict:
    execution_summaries = execution_result.get("results", [])
    if not execution_summaries:
        raise RuntimeError("CadQuery build produced no execution result.")

    summary = execution_summaries[0]
    if not summary.get("success"):
        raise RuntimeError(f"CadQuery build failed: {summary.get('error') or 'unknown error'}")
    if summary.get("shapes_count", 0) <= shape_index:
        raise RuntimeError(f"CadQuery build produced no shape at index {shape_index}.")
    return summary


def _execute_and_export_generated_model(
    request_id: str,
    model_id: str,
    code: str,
    shape_index: int = 0,
) -> tuple[str, dict, dict]:
    os.makedirs(AI_WORKSPACE_DIR, exist_ok=True)
    execution_result = handle_execute_cadquery_script(
        {
            "request_id": request_id,
            "arguments": {
                "workspace_path": AI_WORKSPACE_DIR,
                "script": _ensure_exportable_script(code),
                "parameters": None,
            },
        }
    )

    summary = _first_execution_summary(execution_result, shape_index)
    export_result = handle_export_shape(
        {
            "request_id": request_id,
            "arguments": {
                "workspace_path": AI_WORKSPACE_DIR,
                "result_id": summary["result_id"],
                "shape_index": shape_index,
                "filename": f"{model_id}.stl",
                "format": "STL",
                "options": {},
            },
        }
    )

    return export_result["filename"], execution_result, export_result


def _run_generation_attempts(
    model_id: str,
    initial_code_fn: Callable[[], str],
    repair_instruction_fn: Callable[[str], str],
    request_id: str,
) -> tuple[str, str, dict, dict, int]:
    code = None
    last_error = None

    for attempt in range(1, 4):
        try:
            if code is None:
                code = initial_code_fn()
            else:
                code = modify_cadquery_code(code, repair_instruction_fn(str(last_error)))

            stl_path, execution_result, export_result = _execute_and_export_generated_model(
                request_id=f"{request_id}-{attempt}",
                model_id=model_id,
                code=code,
            )
            return code, stl_path, execution_result, export_result, attempt
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"3 attempts failed: {last_error}")


def handle_generate_model(request: dict) -> dict:
    """Generate a CadQuery model, export it to STL, and store version metadata."""
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling generate_model request (ID: {request_id})")
    args = GenerateModelArgs(**request.get("arguments", {}))
    model_id = validate_model_id(args.model_id or str(uuid.uuid4())[:8])

    try:
        code, stl_path, execution_result, export_result, attempt = _run_generation_attempts(
            model_id=model_id,
            initial_code_fn=lambda: generate_cadquery_code(args.description, image_path=args.image_path),
            repair_instruction_fn=lambda error: f"Fix this CadQuery execution/export error: {error}",
            request_id=request_id,
        )
    except Exception as exc:
        return {"success": False, "model_id": model_id, "message": str(exc)}

    meta = save_model(
        models_dir=MODELS_DIR,
        model_id=model_id,
        description=args.description,
        code=code,
        stl_path=stl_path,
    )
    return {
        "success": True,
        "model_id": model_id,
        "stl_path": stl_path,
        "cadquery_code": code,
        "version": len(meta["versions"]),
        "attempt": attempt,
        "execution": execution_result,
        "export": export_result,
    }


def handle_modify_model(request: dict) -> dict:
    """Modify a stored model, export a new STL, and append a model version."""
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling modify_model request (ID: {request_id})")
    args = ModifyModelArgs(**request.get("arguments", {}))
    model_id = validate_model_id(args.model_id)

    try:
        existing_code = load_latest_code(MODELS_DIR, model_id)
        existing_meta = load_model(MODELS_DIR, model_id)
    except FileNotFoundError:
        return {"success": False, "model_id": model_id, "message": f"model_id '{model_id}' was not found."}

    try:
        code, stl_path, execution_result, export_result, attempt = _run_generation_attempts(
            model_id=model_id,
            initial_code_fn=lambda: modify_cadquery_code(existing_code, args.instruction),
            repair_instruction_fn=lambda error: f"Fix this CadQuery execution/export error: {error}",
            request_id=request_id,
        )
    except Exception as exc:
        return {"success": False, "model_id": model_id, "message": str(exc)}

    description = f"{existing_meta.get('description', '')} -> {args.instruction}".strip()
    meta = save_model(
        models_dir=MODELS_DIR,
        model_id=model_id,
        description=description,
        code=code,
        stl_path=stl_path,
    )
    return {
        "success": True,
        "model_id": model_id,
        "stl_path": stl_path,
        "cadquery_code": code,
        "version": len(meta["versions"]),
        "attempt": attempt,
        "execution": execution_result,
        "export": export_result,
    }


def handle_list_models(request: dict) -> dict:
    """List stored AI-generated CadQuery models and latest STL metadata."""
    ListModelsArgs(**request.get("arguments", {}))
    models = store_list_models(MODELS_DIR)
    return {"success": True, "models": models, "count": len(models)}


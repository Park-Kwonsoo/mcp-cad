# This module contains all tool handler functions and the tool_handlers dict

import os
import uuid
import ast
from typing import Any, Callable

import cadquery as cq

from .ai_generator import generate_cadquery_code, modify_cadquery_code
from .env_setup import (
    prepare_workspace_env,
    get_workspace_results_dir,
    workspace_env_signature_cache,
)
from .model_store import (
    MODELS_DIR,
    list_models as store_list_models,
    load_latest_code,
    load_model,
    save_model,
    validate_model_id,
)
from .core import (
    export_shape_to_file,
    export_shape_to_svg_file,
    get_shape_properties as core_get_shape_properties,
    get_shape_description as core_get_shape_description,
    analyze_cad_file as core_analyze_cad_file,
    transform_stl_mesh as core_transform_stl_mesh,
    compare_stl_meshes as core_compare_stl_meshes,
    inspect_stl_sections as core_inspect_stl_sections,
    inspect_stl_plane_sections as core_inspect_stl_plane_sections,
    detect_mount_features as core_detect_mount_features,
    render_stl_preview as core_render_stl_preview,
    validate_stl_solid as core_validate_stl_solid,
    solidify_stl_mesh as core_solidify_stl_mesh,
    probe_stl_tunnel as core_probe_stl_tunnel,
)

from .models import (
    ExecuteCadqueryScriptArgs,
    BuildAndExportStlArgs,
    AnalyzeCadFileArgs,
    TransformStlMeshArgs,
    CompareStlMeshesArgs,
    InspectStlSectionsArgs,
    InspectStlPlaneSectionsArgs,
    DetectMountFeaturesArgs,
    RenderStlPreviewArgs,
    ValidateStlSolidArgs,
    SolidifyStlMeshArgs,
    ProbeStlTunnelArgs,
    GenerateModelArgs,
    ModifyModelArgs,
    ListModelsArgs,
)
from .worker_pool import cadquery_worker_pool

from .state import (
    log,
    shape_results,
    DEFAULT_OUTPUT_DIR_NAME,
    DEFAULT_RENDER_DIR_NAME,
)

AI_WORKSPACE_DIR = os.path.expanduser("~/.mcp/mcp-cad/workspace")

def _coerce_execute_args(args: Any, request_id: str) -> tuple[ExecuteCadqueryScriptArgs, str]:
    """Accept direct model calls and raw MCP request dictionaries."""
    if isinstance(args, ExecuteCadqueryScriptArgs):
        return args, request_id
    if isinstance(args, dict):
        if "arguments" in args:
            request_id = args.get("request_id", request_id)
            return ExecuteCadqueryScriptArgs(**args.get("arguments", {})), request_id
        return ExecuteCadqueryScriptArgs(**args), request_id
    raise TypeError(f"Unsupported execute_cadquery_script argument type: {type(args)}")


def _script_calls_show_object(script_content: str) -> bool:
    tree = ast.parse(script_content)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "show_object":
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "show_object":
            return True
    return False


def _script_assigns_result(script_content: str) -> bool:
    tree = ast.parse(script_content)
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.NamedExpr):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "result":
                return True
    return False


def _ensure_exportable_script(script_content: str) -> str:
    """
    CadQuery CQGI only exports objects passed through show_object. For build/export
    tools, accept the common `result = model` convention and expose it explicitly.
    """
    if _script_calls_show_object(script_content):
        return script_content
    if _script_assigns_result(script_content):
        return f"{script_content.rstrip()}\n\nshow_object(result)\n"
    return script_content


def handle_execute_cadquery_script(args: Any, request_id: str = "unknown") -> dict:
    """
    Run CadQuery Python to create or edit a CAD model when a script is already available.
    Ensures workspace environment exists and executes the script
    within that environment using a persistent CadQuery worker.
    """
    log.info(f"Handling execute_cadquery_script request (ID: {request_id})")
    try:
        execute_args, request_id = _coerce_execute_args(args, request_id)
        workspace_path = os.path.abspath(execute_args.workspace_path)
        script_content = execute_args.script

        # Determine parameter sets
        if execute_args.parameter_sets is not None:
            parameter_sets = execute_args.parameter_sets
        elif execute_args.parameters is not None:
            parameter_sets = [execute_args.parameters]
        else:
            parameter_sets = [{}]

        log.info(f"Target workspace: {workspace_path}")
        log.info(f"Script content received (first 100 chars): {script_content[:100]}...")
        log.info(f"Processing {len(parameter_sets)} parameter set(s).")
        results_dir = get_workspace_results_dir(workspace_path)

        # Ensure the workspace environment is ready
        previous_env_signature = workspace_env_signature_cache.get(workspace_path)
        workspace_python_exe = prepare_workspace_env(workspace_path)
        current_env_signature = workspace_env_signature_cache.get(workspace_path)
        if previous_env_signature is not None and current_env_signature != previous_env_signature:
            cadquery_worker_pool.close_workspace(workspace_path)

        results_summary = []

        for i, params in enumerate(parameter_sets):
            result_id = f"{request_id}_{i}"
            log_prefix = f"Exec({os.path.basename(workspace_path)}/{result_id})"
            log.info(f"[{log_prefix}] Preparing execution for parameter set {i} with params: {params}")

            try:
                runner_result = cadquery_worker_pool.execute(workspace_path, workspace_python_exe, {
                    "workspace_path": workspace_path,
                    "results_dir": results_dir,
                    "script_content": script_content,
                    "parameters": params,
                    "result_id": result_id
                })

                shape_results[result_id] = runner_result

                results_summary.append({
                    "result_id": result_id,
                    "success": runner_result.get("success", False),
                    "shapes_count": len(runner_result.get("results", [])),
                    "error": runner_result.get("exception_str")
                })
                log.info(f"[{log_prefix}] Stored execution result for set {i}. Success: {runner_result.get('success', False)}")

            except Exception as exec_err:
                log.error(f"[{log_prefix}] Subprocess execution/processing failed for parameter set {i}: {exec_err}", exc_info=True)
                results_summary.append({
                    "result_id": result_id,
                    "success": False,
                    "shapes_count": 0,
                    "error": f"Handler error during execution: {exec_err}"
                })
                if result_id in shape_results:
                    del shape_results[result_id]

        total_sets = len(parameter_sets)
        successful_sets = sum(1 for r in results_summary if r["success"])
        message = f"Script execution processed for {total_sets} parameter set(s). Successful: {successful_sets}, Failed: {total_sets - successful_sets}."
        return {"success": True, "message": message, "results": results_summary}

    except Exception as e:
        error_msg = f"Error during script execution handling: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_build_and_export_stl(request: dict) -> dict:
    """
    Create a 3D-printer-ready STL through MCP/CadQuery; use real boolean union/cut solids, not STL mesh concatenation.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling build_and_export_stl request (ID: {request_id})")
    try:
        args = BuildAndExportStlArgs(**request.get("arguments", {}))
        if args.shape_index < 0:
            raise ValueError("'shape_index' must be a non-negative integer.")

        execution_result = handle_execute_cadquery_script({
            "request_id": request_id,
            "arguments": {
                "workspace_path": args.workspace_path,
                "script": _ensure_exportable_script(args.script),
                "parameters": args.parameters,
            },
        })

        execution_summaries = execution_result.get("results", [])
        if not execution_summaries or not execution_summaries[0].get("success"):
            error = execution_summaries[0].get("error") if execution_summaries else "Script produced no result."
            raise RuntimeError(f"CadQuery build failed: {error}")
        if execution_summaries[0].get("shapes_count", 0) <= args.shape_index:
            raise RuntimeError(f"CadQuery build produced no shape at index {args.shape_index}.")

        result_id = f"{request_id}_0"
        export_result = handle_export_shape({
            "request_id": request_id,
            "arguments": {
                "workspace_path": args.workspace_path,
                "result_id": result_id,
                "shape_index": args.shape_index,
                "filename": args.filename,
                "format": "STL",
                "options": args.export_options or {},
            },
        })

        analysis = None
        try:
            analysis = core_analyze_cad_file(export_result["filename"], "stl")
        except Exception as analysis_error:
            log.warning(f"STL analysis failed after export: {analysis_error}")

        return {
            "success": True,
            "message": f"CadQuery model built and exported to STL: {export_result['filename']}",
            "result_id": result_id,
            "execution": execution_result,
            "export": export_result,
            "analysis": analysis,
        }
    except Exception as e:
        error_msg = f"Error during build/export STL handling: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_create_printable_stl(request: dict) -> dict:
    """
    Use this MCP tool for "make/print/output an STL" requests instead of local shell Python or mesh concatenation.
    """
    return handle_build_and_export_stl(request)


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
    """
    Generate a CadQuery model from text or image input, export it to STL, and store the model workspace metadata.
    """
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
        return {
            "success": False,
            "model_id": model_id,
            "message": str(exc),
        }

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
    """
    Modify a stored model by regenerating its CadQuery code, export a new STL, and append a model version.
    """
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
        return {
            "success": False,
            "model_id": model_id,
            "message": str(exc),
        }

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
    """
    List stored AI-generated CadQuery models and their latest STL metadata.
    """
    ListModelsArgs(**request.get("arguments", {}))
    models = store_list_models(MODELS_DIR)
    return {"success": True, "models": models, "count": len(models)}


def handle_analyze_cad_file(request: dict) -> dict:
    """
    Inspect STL/CAD files through MCP for dimensions, watertightness, non-manifold edges, and disconnected shells.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling analyze_cad_file request (ID: {request_id})")
    try:
        args = AnalyzeCadFileArgs(**request.get("arguments", {}))
        analysis = core_analyze_cad_file(args.file_path, args.file_format)
        return {
            "success": True,
            "message": f"CAD file analyzed successfully: {analysis['file']['path']}",
            "analysis": analysis,
        }
    except Exception as e:
        error_msg = f"Error during CAD file analysis: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_transform_stl_mesh(request: dict) -> dict:
    """
    Resize or reposition an STL through MCP for dimension edits; verify the result with analyze_cad_file or compare_stl_meshes.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling transform_stl_mesh request (ID: {request_id})")
    try:
        args = TransformStlMeshArgs(**request.get("arguments", {}))
        transform_result = core_transform_stl_mesh(
            file_path=args.file_path,
            output_path=args.output_path,
            scale=args.scale,
            target_size=args.target_size,
            translate=args.translate,
            rotate_degrees=args.rotate_degrees,
            center_at_origin=args.center_at_origin,
        )
        return {
            "success": True,
            "message": f"STL mesh transformed successfully: {transform_result['output_file']}",
            "result": transform_result,
        }
    except Exception as e:
        error_msg = f"Error during STL mesh transform: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_compare_stl_meshes(request: dict) -> dict:
    """
    Compare two STL files through MCP to verify redesigns, retained geometry, and added/removed 3D-print mesh regions.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling compare_stl_meshes request (ID: {request_id})")
    try:
        args = CompareStlMeshesArgs(**request.get("arguments", {}))
        comparison = core_compare_stl_meshes(
            source_file_path=args.source_file_path,
            target_file_path=args.target_file_path,
            source_translate=args.source_translate,
            target_translate=args.target_translate,
            round_decimals=args.round_decimals,
            z_thresholds=args.z_thresholds,
            target_only_z_ranges=args.target_only_z_ranges,
        )
        return {
            "success": True,
            "message": "STL meshes compared successfully.",
            "comparison": comparison,
        }
    except Exception as e:
        error_msg = f"Error during STL mesh comparison: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_inspect_stl_sections(request: dict) -> dict:
    """
    Slice an STL through MCP to read height/axis section loops, bounds, and possible hole profiles.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling inspect_stl_sections request (ID: {request_id})")
    try:
        args = InspectStlSectionsArgs(**request.get("arguments", {}))
        section_result = core_inspect_stl_sections(
            file_path=args.file_path,
            axis=args.axis,
            positions=args.positions,
            interval=args.interval,
            position_count=args.position_count,
            round_decimals=args.round_decimals,
            include_points=args.include_points,
            max_sections=args.max_sections,
        )
        return {
            "success": True,
            "message": "STL sections inspected successfully.",
            "sections": section_result,
        }
    except Exception as e:
        error_msg = f"Error during STL section inspection: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_inspect_stl_plane_sections(request: dict) -> dict:
    """
    Slice an STL with tilted planes through MCP to measure mount-face loops, hole bounds, and clearances.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling inspect_stl_plane_sections request (ID: {request_id})")
    try:
        args = InspectStlPlaneSectionsArgs(**request.get("arguments", {}))
        section_result = core_inspect_stl_plane_sections(
            file_path=args.file_path,
            origin=args.origin,
            normal=args.normal,
            x_direction=args.x_direction,
            offsets=args.offsets,
            round_decimals=args.round_decimals,
            include_points=args.include_points,
            max_sections=args.max_sections,
        )
        return {
            "success": True,
            "message": "STL tilted plane sections inspected successfully.",
            "sections": section_result,
        }
    except Exception as e:
        error_msg = f"Error during STL tilted plane section inspection: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_detect_mount_features(request: dict) -> dict:
    """
    Detect mounting hole/slot candidates from STL section loops through MCP.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling detect_mount_features request (ID: {request_id})")
    try:
        args = DetectMountFeaturesArgs(**request.get("arguments", {}))
        features = core_detect_mount_features(
            file_path=args.file_path,
            axis=args.axis,
            positions=args.positions,
            interval=args.interval,
            position_count=args.position_count,
            min_loop_area=args.min_loop_area,
            max_loop_area=args.max_loop_area,
            min_circularity=args.min_circularity,
            center_tolerance=args.center_tolerance,
            round_decimals=args.round_decimals,
        )
        return {
            "success": True,
            "message": "STL mount features detected successfully.",
            "features": features,
        }
    except Exception as e:
        error_msg = f"Error during STL mount feature detection: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_render_stl_preview(request: dict) -> dict:
    """
    Render an STL visual preview through MCP for quick top/front/right/iso review before or after repair.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling render_stl_preview request (ID: {request_id})")
    try:
        args = RenderStlPreviewArgs(**request.get("arguments", {}))
        preview = core_render_stl_preview(
            file_path=args.file_path,
            output_path=args.output_path,
            views=args.views,
            width=args.width,
            height=args.height,
            margin=args.margin,
            show_edges=args.show_edges,
        )
        return {
            "success": True,
            "message": f"STL preview rendered successfully: {preview['output_file']}",
            "preview": preview,
        }
    except Exception as e:
        error_msg = f"Error during STL preview rendering: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_validate_stl_solid(request: dict) -> dict:
    """
    Validate STL printability through MCP, including watertightness, manifold edges, and disconnected shells.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling validate_stl_solid request (ID: {request_id})")
    try:
        args = ValidateStlSolidArgs(**request.get("arguments", {}))
        validation = core_validate_stl_solid(
            file_path=args.file_path,
            allow_multiple_components=args.allow_multiple_components,
            expected_component_count=args.expected_component_count,
        )
        return {
            "success": True,
            "message": "STL solid validation completed.",
            "validation": validation,
        }
    except Exception as e:
        error_msg = f"Error during STL solid validation: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_solidify_stl_mesh(request: dict) -> dict:
    """
    Convert a watertight STL mesh to tessellated BREP/STEP through MCP instead of CadQuery importers.importShape.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling solidify_stl_mesh request (ID: {request_id})")
    try:
        args = SolidifyStlMeshArgs(**request.get("arguments", {}))
        result = core_solidify_stl_mesh(
            file_path=args.file_path,
            output_path=args.output_path,
            output_format=args.output_format,
            max_triangles=args.max_triangles,
            allow_multiple_components=args.allow_multiple_components,
            require_watertight=args.require_watertight,
        )
        return {
            "success": True,
            "message": f"STL mesh converted to tessellated solid reference: {result['output_file']}",
            "result": result,
        }
    except Exception as e:
        error_msg = f"Error during STL mesh solidification: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_probe_stl_tunnel(request: dict) -> dict:
    """
    Probe an STL tunnel/cable channel through MCP to verify a rectangular passage is clear.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling probe_stl_tunnel request (ID: {request_id})")
    try:
        args = ProbeStlTunnelArgs(**request.get("arguments", {}))
        tunnel = core_probe_stl_tunnel(
            file_path=args.file_path,
            start=args.start,
            end=args.end,
            width=args.width,
            height=args.height,
            up_direction=args.up_direction,
            length_samples=args.length_samples,
            width_samples=args.width_samples,
            height_samples=args.height_samples,
            max_blocked_samples=args.max_blocked_samples,
        )
        return {
            "success": True,
            "message": "STL tunnel probe completed.",
            "tunnel": tunnel,
        }
    except Exception as e:
        error_msg = f"Error during STL tunnel probe: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_export_shape(request: dict) -> dict:
    """
    Export a generated CadQuery shape to STL for 3D printing or to STEP/BREP/SVG formats.
    Imports shape from intermediate file and exports to target format/location.
    Resolves relative target paths based on the workspace.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling export_shape request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        workspace_path_arg = args.get("workspace_path") # Expect workspace path
        result_id = args.get("result_id")
        shape_index = args.get("shape_index", 0)
        filename_arg = args.get("filename") # Target filename/path
        export_format = args.get("format")
        export_options = args.get("options", {})

        if not workspace_path_arg: raise ValueError("Missing 'workspace_path' argument.")
        if not result_id: raise ValueError("Missing 'result_id' argument.")
        if not filename_arg: raise ValueError("Missing 'filename' argument.")
        if not isinstance(shape_index, int) or shape_index < 0: raise ValueError("'shape_index' must be a non-negative integer.")
        if not isinstance(export_options, dict): raise ValueError("'options' argument must be a dictionary.")

        workspace_path = os.path.abspath(workspace_path_arg)
        if not os.path.isdir(workspace_path): raise ValueError(f"Invalid workspace path: {workspace_path}")

        # Retrieve result dict from main process state
        result_dict = shape_results.get(result_id)
        if not result_dict: raise ValueError(f"Result ID '{result_id}' not found.")
        if not result_dict.get("success"): raise ValueError(f"Result ID '{result_id}' corresponds to a failed build.")

        results_list = result_dict.get("results", [])
        if not results_list or shape_index >= len(results_list): raise ValueError(f"Invalid shape_index {shape_index} for result ID '{result_id}'.")

        # Get the intermediate path from the stored result data
        shape_data = results_list[shape_index]
        intermediate_path = shape_data.get("intermediate_path")
        if not intermediate_path or not os.path.exists(intermediate_path):
             raise ValueError(f"Intermediate file path not found or file missing for shape {shape_index} in result ID '{result_id}'. Path: {intermediate_path}")

        # Import the shape from the intermediate BREP file
        log.info(f"Importing shape from intermediate file: {intermediate_path}")
        try:
            # Ensure CadQuery is available in the main server env for import/export ops
            shape_to_export = cq.importers.importBrep(intermediate_path)
            log.info(f"Successfully imported shape for export.")
        except Exception as import_err:
            log.error(f"Failed to import BREP file '{intermediate_path}': {import_err}", exc_info=True)
            raise RuntimeError(f"Failed to import intermediate shape file: {import_err}") from import_err

        # Determine final output path, resolving relative paths against the WORKSPACE
        output_path: str
        if os.path.isabs(filename_arg) or os.path.sep in filename_arg or (os.altsep and os.altsep in filename_arg):
            # If filename is absolute or contains a directory path, use it directly (but ensure it's absolute)
            output_path = os.path.abspath(filename_arg)
            log.info(f"Using provided absolute/relative path for export: '{output_path}'")
        else:
            # If filename is just a name, place it inside <workspace_path>/<output_dir_name>/
            output_dir_name = DEFAULT_OUTPUT_DIR_NAME # Use default from state
            output_path = os.path.join(workspace_path, output_dir_name, filename_arg)
            log.info(f"Using workspace default output directory '{output_dir_name}'. Exporting to: '{output_path}'")

        # Ensure the target directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
             os.makedirs(output_dir, exist_ok=True)

        log.info(f"Attempting to export shape to '{output_path}' (Format: {export_format or 'Infer'}, Options: {export_options})")
        # Call the core export function with the imported shape and calculated absolute path
        export_shape_to_file(shape_to_export, output_path, export_format, export_options)
        log.info(f"Shape successfully exported via export_shape_to_file to '{output_path}'.")
        # Return the final absolute path
        return {"success": True, "message": f"Shape successfully exported to {output_path}.", "filename": output_path}
    except Exception as e: error_msg = f"Error during shape export handling: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)

def handle_export_shape_to_svg(request: dict) -> dict:
    """
    Handles the 'export_shape_to_svg' tool request.
    Imports shape from intermediate file and exports SVG to workspace render dir.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling export_shape_to_svg request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        workspace_path_arg = args.get("workspace_path") # Expect workspace path
        result_id = args.get("result_id")
        shape_index = args.get("shape_index", 0)
        filename_arg = args.get("filename") # Optional target filename
        export_options = args.get("options", {})

        if not workspace_path_arg: raise ValueError("Missing 'workspace_path' argument.")
        if not result_id: raise ValueError("Missing 'result_id' argument.")
        if not isinstance(shape_index, int) or shape_index < 0: raise ValueError("'shape_index' must be a non-negative integer.")
        if not isinstance(export_options, dict): raise ValueError("'options' argument must be a dictionary.")

        workspace_path = os.path.abspath(workspace_path_arg)
        if not os.path.isdir(workspace_path): raise ValueError(f"Invalid workspace path: {workspace_path}")

        # Retrieve result dict
        result_dict = shape_results.get(result_id)
        if not result_dict: raise ValueError(f"Result ID '{result_id}' not found.")
        if not result_dict.get("success"): raise ValueError(f"Result ID '{result_id}' corresponds to a failed build.")

        results_list = result_dict.get("results", [])
        if not results_list or shape_index >= len(results_list): raise ValueError(f"Invalid shape_index {shape_index} for result ID '{result_id}'.")

        # Get intermediate path
        shape_data = results_list[shape_index]
        intermediate_path = shape_data.get("intermediate_path")
        if not intermediate_path or not os.path.exists(intermediate_path):
             raise ValueError(f"Intermediate file path not found or file missing for shape {shape_index} in result ID '{result_id}'. Path: {intermediate_path}")

        # Import shape
        log.info(f"Importing shape from intermediate file: {intermediate_path}")
        try:
            shape_to_render = cq.importers.importBrep(intermediate_path)
            log.info(f"Successfully imported shape for SVG export.")
        except Exception as import_err:
            log.error(f"Failed to import BREP file '{intermediate_path}': {import_err}", exc_info=True)
            raise RuntimeError(f"Failed to import intermediate shape file: {import_err}") from import_err

        # Determine output path within the workspace's render directory
        render_dir_name = DEFAULT_RENDER_DIR_NAME # Use default from state
        render_dir_path = os.path.join(workspace_path, DEFAULT_OUTPUT_DIR_NAME, render_dir_name)
        os.makedirs(render_dir_path, exist_ok=True)

        default_svg_name = f"render_{uuid.uuid4()}.svg"
        base_filename = os.path.basename(filename_arg or default_svg_name)
        if not base_filename.lower().endswith(".svg"):
             base_filename += ".svg"
             log.warning(f"Appended .svg to filename. New base filename: {base_filename}")

        output_path = os.path.join(render_dir_path, base_filename)

        # Default SVG options (can be overridden)
        svg_opts = {"width": 400, "height": 300, "marginLeft": 10, "marginTop": 10, "showAxes": False, "projectionDir": (0.5, 0.5, 0.5), "strokeWidth": 0.25, "strokeColor": (0, 0, 0), "hiddenColor": (0, 0, 255, 100), "showHidden": False}
        svg_opts.update(export_options)

        # Call core SVG export function
        export_shape_to_svg_file(shape_to_render, output_path, svg_opts)

        return {"success": True, "message": f"Shape successfully exported to SVG: {output_path}.", "filename": output_path}
    except Exception as e: error_msg = f"Error during SVG export handling: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)

def handle_get_shape_properties(request: dict) -> dict:
    """
    Handles the 'get_shape_properties' tool request.
    Imports shape from intermediate file and retrieves its properties.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling get_shape_properties request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        result_id = args.get("result_id")
        shape_index = args.get("shape_index", 0)

        if not result_id: raise ValueError("Missing 'result_id' argument.")
        if not isinstance(shape_index, int) or shape_index < 0: raise ValueError("'shape_index' must be a non-negative integer.")

        # Retrieve result dict
        result_dict = shape_results.get(result_id)
        if not result_dict: raise ValueError(f"Result ID '{result_id}' not found.")
        if not result_dict.get("success"): raise ValueError(f"Result ID '{result_id}' corresponds to a failed build.")

        results_list = result_dict.get("results", [])
        if not results_list or shape_index >= len(results_list): raise ValueError(f"Invalid shape_index {shape_index} for result ID '{result_id}'.")

        # Get intermediate path
        shape_data = results_list[shape_index]
        intermediate_path = shape_data.get("intermediate_path")
        if not intermediate_path or not os.path.exists(intermediate_path):
             raise ValueError(f"Intermediate file path not found or file missing for shape {shape_index} in result ID '{result_id}'. Path: {intermediate_path}")

        # Import shape
        log.info(f"Importing shape from intermediate file for properties: {intermediate_path}")
        try:
            shape_object = cq.importers.importBrep(intermediate_path)
            log.info(f"Successfully imported shape.")
        except Exception as import_err:
            log.error(f"Failed to import BREP file '{intermediate_path}': {import_err}", exc_info=True)
            raise RuntimeError(f"Failed to import intermediate shape file: {import_err}") from import_err

        # Get properties using the core function
        properties = core_get_shape_properties(shape_object)

        log.info(f"Retrieved properties for shape {shape_index} from result ID '{result_id}'.")
        return {"success": True, "message": "Shape properties retrieved successfully.", "properties": properties}

    except Exception as e: error_msg = f"Error getting shape properties: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)

def handle_get_shape_description(request: dict) -> dict:
    """
    Handles the 'get_shape_description' tool request.
    Imports shape from intermediate file and generates a textual description.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling get_shape_description request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        result_id = args.get("result_id")
        shape_index = args.get("shape_index", 0)

        if not result_id: raise ValueError("Missing 'result_id' argument.")
        if not isinstance(shape_index, int) or shape_index < 0: raise ValueError("'shape_index' must be a non-negative integer.")

        # Retrieve result dict
        result_dict = shape_results.get(result_id)
        if not result_dict: raise ValueError(f"Result ID '{result_id}' not found.")
        if not result_dict.get("success"): raise ValueError(f"Result ID '{result_id}' corresponds to a failed build.")

        results_list = result_dict.get("results", [])
        if not results_list or shape_index >= len(results_list): raise ValueError(f"Invalid shape_index {shape_index} for result ID '{result_id}'.")

        # Get intermediate path
        shape_data = results_list[shape_index]
        intermediate_path = shape_data.get("intermediate_path")
        if not intermediate_path or not os.path.exists(intermediate_path):
             raise ValueError(f"Intermediate file path not found or file missing for shape {shape_index} in result ID '{result_id}'. Path: {intermediate_path}")

        # Import shape
        log.info(f"Importing shape from intermediate file for description: {intermediate_path}")
        try:
            shape_object = cq.importers.importBrep(intermediate_path)
            log.info(f"Successfully imported shape.")
        except Exception as import_err:
            log.error(f"Failed to import BREP file '{intermediate_path}': {import_err}", exc_info=True)
            raise RuntimeError(f"Failed to import intermediate shape file: {import_err}") from import_err

        # Get description using the core function
        description = core_get_shape_description(shape_object)

        log.info(f"Generated description for shape {shape_index} from result ID '{result_id}'.")
        return {"success": True, "message": "Shape description generated successfully.", "description": description}

    except Exception as e: error_msg = f"Error getting shape description: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)


# --- Tool Handler Dictionary ---
# Maps tool names to their implementation functions
tool_handlers = {
    "execute_cadquery_script": handle_execute_cadquery_script,
    "build_and_export_stl": handle_build_and_export_stl,
    "create_printable_stl": handle_create_printable_stl,
    "generate_model": handle_generate_model,
    "modify_model": handle_modify_model,
    "list_models": handle_list_models,
    "export_shape": handle_export_shape,
    "export_shape_to_svg": handle_export_shape_to_svg,
    "analyze_cad_file": handle_analyze_cad_file,
    "transform_stl_mesh": handle_transform_stl_mesh,
    "compare_stl_meshes": handle_compare_stl_meshes,
    "inspect_stl_sections": handle_inspect_stl_sections,
    "inspect_stl_plane_sections": handle_inspect_stl_plane_sections,
    "detect_mount_features": handle_detect_mount_features,
    "render_stl_preview": handle_render_stl_preview,
    "validate_stl_solid": handle_validate_stl_solid,
    "solidify_stl_mesh": handle_solidify_stl_mesh,
    "probe_stl_tunnel": handle_probe_stl_tunnel,
    "get_shape_properties": handle_get_shape_properties,
    "get_shape_description": handle_get_shape_description,
}

"""Shared CadQuery execution helpers for one-shot and persistent runners."""

import contextlib
import json
import logging
import os
import sys
import traceback
from typing import Any, Dict


log = logging.getLogger(__name__)


def _ensure_import_path(path: str) -> None:
    if path not in sys.path:
        sys.path.insert(0, path)


def _format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def execute_cadquery_job(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute one CadQuery job and return the serialized runner result.

    The return schema intentionally matches the legacy script_runner.py output:
    success, results, and exception_str.
    """
    output_result: Dict[str, Any] = {"success": False, "results": [], "exception_str": None}

    try:
        workspace_path = input_data.get("workspace_path")
        script_content = input_data.get("script_content")
        parameters = input_data.get("parameters", {})
        result_id = input_data.get("result_id")

        if not result_id:
            raise ValueError("Missing 'result_id' in input.")
        if not workspace_path or not os.path.isdir(workspace_path):
            raise ValueError(f"Invalid or missing 'workspace_path': {workspace_path}")
        if not script_content:
            raise ValueError("Missing 'script_content' in input.")
        if not isinstance(parameters, dict):
            raise ValueError("'parameters' must be a dictionary.")

        modules_dir = os.path.join(workspace_path, "modules")
        if os.path.isdir(modules_dir):
            _ensure_import_path(modules_dir)
        _ensure_import_path(workspace_path)

        # Worker stdout is reserved for JSON protocol messages. CadQuery imports,
        # CQGI build hooks, and user scripts may print warnings or diagnostics;
        # route those to stderr so callers always receive parseable JSON.
        with contextlib.redirect_stdout(sys.stderr):
            import cadquery as cq
            from cadquery import cqgi

            model = cqgi.parse(script_content)
            build_result = model.build()

        output_result["success"] = build_result.success
        if build_result.exception:
            output_result["exception_str"] = _format_exception(build_result.exception)

        if build_result.results:
            result_files_dir = os.path.join(workspace_path, ".cq_results", result_id)
            os.makedirs(result_files_dir, exist_ok=True)

            shapes_to_export = []
            for i, res in enumerate(build_result.results):
                shape_name = res.options.get("name") if hasattr(res, "options") and isinstance(res.options, dict) else None
                shape_name = shape_name or f"shape_{i}"
                shapes_to_export.append({"name": shape_name, "shape": res.shape})

            for item in shapes_to_export:
                shape_info = {"name": item["name"], "type": type(item["shape"]).__name__}
                try:
                    intermediate_filename = f"{shape_info['name']}.brep"
                    intermediate_filepath = os.path.join(result_files_dir, intermediate_filename)
                    shape_to_export = item["shape"]
                    if isinstance(shape_to_export, cq.Assembly):
                        shape_to_export = shape_to_export.toCompound()

                    with contextlib.redirect_stdout(sys.stderr):
                        cq.exporters.export(shape_to_export, intermediate_filepath, exportType="BREP")
                    shape_info["intermediate_path"] = intermediate_filepath
                except Exception as export_err:
                    log.exception("Failed to export '%s' to BREP.", shape_info["name"])
                    shape_info["intermediate_path"] = None
                    shape_info["export_error"] = str(export_err)

                output_result["results"].append(shape_info)

    except Exception as exc:
        log.exception("Error during CadQuery job execution.")
        output_result["success"] = False
        output_result["results"] = []
        output_result["exception_str"] = _format_exception(exc)

    return output_result


def execute_cadquery_job_from_stdin() -> Dict[str, Any]:
    input_data_str = sys.stdin.read()
    if not input_data_str:
        return {
            "success": False,
            "results": [],
            "exception_str": "ValueError: No input data received from stdin.",
        }
    return execute_cadquery_job(json.loads(input_data_str))

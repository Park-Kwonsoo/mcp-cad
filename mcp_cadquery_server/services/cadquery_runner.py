"""Shared CadQuery execution helpers for one-shot and persistent runners."""

import contextlib
import hashlib
import logging
import os
import re
import sys
import traceback
from typing import Any, Dict


log = logging.getLogger(__name__)


def _remove_services_dir_from_import_path() -> None:
    """
    The worker may be launched by file path, which puts this services directory
    on sys.path and lets services/cadquery.py shadow the real cadquery package.
    """
    services_dir = os.path.realpath(os.path.dirname(__file__))
    sys.path[:] = [
        path
        for path in sys.path
        if os.path.realpath(path or os.getcwd()) != services_dir
    ]
    cadquery_module = sys.modules.get("cadquery")
    cadquery_file = getattr(cadquery_module, "__file__", None)
    if cadquery_file and os.path.realpath(cadquery_file) == os.path.join(services_dir, "cadquery.py"):
        del sys.modules["cadquery"]


def _ensure_import_path(path: str) -> None:
    if path not in sys.path:
        sys.path.insert(0, path)


def _format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _default_cache_root() -> str:
    configured = os.environ.get("MCP_CADQUERY_CACHE_DIR")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches/mcp-cadquery")
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(local_app_data, "mcp-cadquery", "Cache")
    return os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "mcp-cadquery")


def _workspace_cache_key(workspace_path: str) -> str:
    resolved = os.path.realpath(os.path.abspath(workspace_path))
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]
    base_name = os.path.basename(resolved) or "workspace"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", base_name).strip("._") or "workspace"
    return f"{safe_name}-{digest}"


def _default_results_dir(workspace_path: str) -> str:
    return os.path.join(_default_cache_root(), "workspaces", _workspace_cache_key(workspace_path), ".cq_results")


def execute_cadquery_job(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute one CadQuery job and return the serialized runner result.

    The return schema is shared by the worker process and the main server:
    success, results, and exception_str.
    """
    output_result: Dict[str, Any] = {"success": False, "results": [], "exception_str": None}

    try:
        workspace_path = input_data.get("workspace_path")
        script_content = input_data.get("script_content")
        parameters = input_data.get("parameters", {})
        result_id = input_data.get("result_id")
        results_dir = input_data.get("results_dir")

        if not result_id:
            raise ValueError("Missing 'result_id' in input.")
        if not workspace_path or not os.path.isdir(workspace_path):
            raise ValueError(f"Invalid or missing 'workspace_path': {workspace_path}")
        if not script_content:
            raise ValueError("Missing 'script_content' in input.")
        if not isinstance(parameters, dict):
            raise ValueError("'parameters' must be a dictionary.")
        if results_dir is not None and not isinstance(results_dir, str):
            raise ValueError("'results_dir' must be a string when provided.")

        # Worker stdout is reserved for JSON protocol messages. CadQuery imports,
        # CQGI build hooks, and user scripts may print warnings or diagnostics;
        # route those to stderr so callers always receive parseable JSON.
        with contextlib.redirect_stdout(sys.stderr):
            _remove_services_dir_from_import_path()
            import cadquery as cq
            from cadquery import cqgi

        modules_dir = os.path.join(workspace_path, "modules")
        if os.path.isdir(modules_dir):
            _ensure_import_path(modules_dir)
        _ensure_import_path(workspace_path)

        with contextlib.redirect_stdout(sys.stderr):
            model = cqgi.parse(script_content)
            build_result = model.build()

        output_result["success"] = build_result.success
        if build_result.exception:
            output_result["exception_str"] = _format_exception(build_result.exception)

        if build_result.results:
            result_root = results_dir or _default_results_dir(workspace_path)
            result_files_dir = os.path.join(result_root, result_id)
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

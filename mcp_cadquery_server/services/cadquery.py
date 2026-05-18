from __future__ import annotations

import ast
import os
import uuid
from typing import Any

import cadquery as cq

from ..context import AppContext
from ..domain.cad_export import export_shape_to_file, export_shape_to_svg_file
from ..domain.geometry import get_shape_description, get_shape_properties
from ..domain.stl_analysis import analyze_cad_file
from ..schemas.cadquery import (
    BuildAndExportStlArgs,
    ExecuteCadqueryScriptArgs,
    ExportShapeArgs,
    ExportShapeToSvgArgs,
    GetShapeDescriptionArgs,
    GetShapePropertiesArgs,
)
from ..state import DEFAULT_OUTPUT_DIR_NAME, DEFAULT_RENDER_DIR_NAME, log
from .workspace_env import get_workspace_results_dir, prepare_workspace_env, workspace_env_signature_cache


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


def handle_execute_cadquery_script(app_context: AppContext, args: ExecuteCadqueryScriptArgs, request_id: str) -> dict:
    """
    Run CadQuery Python to create or edit a CAD model when a script is already available.
    Ensures workspace environment exists and executes the script
    within that environment using a persistent CadQuery worker.
    """
    log.info(f"Handling execute_cadquery_script request (ID: {request_id})")
    try:
        workspace_path = os.path.abspath(args.workspace_path)
        script_content = args.script

        if args.parameter_sets is not None:
            parameter_sets = args.parameter_sets
        elif args.parameters is not None:
            parameter_sets = [args.parameters]
        else:
            parameter_sets = [{}]

        log.info(f"Target workspace: {workspace_path}")
        log.info(f"Script content received (first 100 chars): {script_content[:100]}...")
        log.info(f"Processing {len(parameter_sets)} parameter set(s).")
        results_dir = get_workspace_results_dir(workspace_path)

        previous_env_signature = workspace_env_signature_cache.get(workspace_path)
        workspace_python_exe = prepare_workspace_env(workspace_path)
        current_env_signature = workspace_env_signature_cache.get(workspace_path)
        if previous_env_signature is not None and current_env_signature != previous_env_signature:
            app_context.worker_pool.close_workspace(workspace_path)

        results_summary = []

        for i, params in enumerate(parameter_sets):
            result_id = f"{request_id}_{i}"
            log_prefix = f"Exec({os.path.basename(workspace_path)}/{result_id})"
            log.info(f"[{log_prefix}] Preparing execution for parameter set {i} with params: {params}")

            try:
                runner_result = app_context.worker_pool.execute(
                    workspace_path,
                    workspace_python_exe,
                    {
                        "workspace_path": workspace_path,
                        "results_dir": results_dir,
                        "script_content": script_content,
                        "parameters": params,
                        "result_id": result_id,
                    },
                )

                app_context.shape_results[result_id] = runner_result

                results_summary.append(
                    {
                        "result_id": result_id,
                        "success": runner_result.get("success", False),
                        "shapes_count": len(runner_result.get("results", [])),
                        "error": runner_result.get("exception_str"),
                    }
                )
                log.info(f"[{log_prefix}] Stored execution result for set {i}. Success: {runner_result.get('success', False)}")

            except Exception as exec_err:
                log.error(
                    f"[{log_prefix}] Subprocess execution/processing failed for parameter set {i}: {exec_err}",
                    exc_info=True,
                )
                results_summary.append(
                    {
                        "result_id": result_id,
                        "success": False,
                        "shapes_count": 0,
                        "error": f"Handler error during execution: {exec_err}",
                    }
                )
                if result_id in app_context.shape_results:
                    del app_context.shape_results[result_id]

        total_sets = len(parameter_sets)
        successful_sets = sum(1 for r in results_summary if r["success"])
        message = (
            f"Script execution processed for {total_sets} parameter set(s). "
            f"Successful: {successful_sets}, Failed: {total_sets - successful_sets}."
        )
        return {"success": True, "message": message, "results": results_summary}

    except Exception as e:
        error_msg = f"Error during script execution handling: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_build_and_export_stl(app_context: AppContext, args: BuildAndExportStlArgs, request_id: str) -> dict:
    """
    Create a 3D-printer-ready STL through MCP/CadQuery; use real boolean union/cut solids, not STL mesh concatenation.
    """
    log.info(f"Handling build_and_export_stl request (ID: {request_id})")
    try:
        if args.shape_index < 0:
            raise ValueError("'shape_index' must be a non-negative integer.")

        execution_result = handle_execute_cadquery_script(
            app_context,
            ExecuteCadqueryScriptArgs(
                workspace_path=args.workspace_path,
                script=_ensure_exportable_script(args.script),
                parameters=args.parameters,
            ),
            request_id=request_id,
        )

        execution_summaries = execution_result.get("results", [])
        if not execution_summaries or not execution_summaries[0].get("success"):
            error = execution_summaries[0].get("error") if execution_summaries else "Script produced no result."
            raise RuntimeError(f"CadQuery build failed: {error}")
        if execution_summaries[0].get("shapes_count", 0) <= args.shape_index:
            raise RuntimeError(f"CadQuery build produced no shape at index {args.shape_index}.")

        result_id = f"{request_id}_0"
        export_result = handle_export_shape(
            app_context,
            ExportShapeArgs(
                workspace_path=args.workspace_path,
                result_id=result_id,
                shape_index=args.shape_index,
                filename=args.filename,
                format="STL",
                options=args.export_options or {},
            ),
            request_id=request_id,
        )

        analysis = None
        try:
            analysis = analyze_cad_file(export_result["filename"], "stl")
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


def handle_create_printable_stl(app_context: AppContext, args: BuildAndExportStlArgs, request_id: str) -> dict:
    """Use this MCP tool for make/print/output STL requests."""
    return handle_build_and_export_stl(app_context, args, request_id)


def _load_shape_from_result(app_context: AppContext, result_id: str, shape_index: int) -> Any:
    result_dict = app_context.shape_results.get(result_id)
    if not result_dict:
        raise ValueError(f"Result ID '{result_id}' not found.")
    if not result_dict.get("success"):
        raise ValueError(f"Result ID '{result_id}' corresponds to a failed build.")

    results_list = result_dict.get("results", [])
    if not results_list or shape_index >= len(results_list):
        raise ValueError(f"Invalid shape_index {shape_index} for result ID '{result_id}'.")

    shape_data = results_list[shape_index]
    intermediate_path = shape_data.get("intermediate_path")
    if not intermediate_path or not os.path.exists(intermediate_path):
        raise ValueError(
            f"Intermediate file path not found or file missing for shape {shape_index} "
            f"in result ID '{result_id}'. Path: {intermediate_path}"
        )

    log.info(f"Importing shape from intermediate file: {intermediate_path}")
    try:
        shape_object = cq.importers.importBrep(intermediate_path)
        log.info("Successfully imported shape.")
        return shape_object
    except Exception as import_err:
        log.error(f"Failed to import BREP file '{intermediate_path}': {import_err}", exc_info=True)
        raise RuntimeError(f"Failed to import intermediate shape file: {import_err}") from import_err


def handle_export_shape(app_context: AppContext, args: ExportShapeArgs, request_id: str) -> dict:
    """
    Export a generated CadQuery shape to STL for 3D printing or to STEP/BREP/SVG formats.
    Resolves relative target paths based on the workspace.
    """
    log.info(f"Handling export_shape request (ID: {request_id})")
    try:
        export_options = args.options or {}
        workspace_path = os.path.abspath(args.workspace_path)
        if not os.path.isdir(workspace_path):
            raise ValueError(f"Invalid workspace path: {workspace_path}")

        shape_to_export = _load_shape_from_result(app_context, args.result_id, args.shape_index)

        if os.path.isabs(args.filename) or os.path.sep in args.filename or (os.altsep and os.altsep in args.filename):
            output_path = os.path.abspath(args.filename)
            log.info(f"Using provided absolute/relative path for export: '{output_path}'")
        else:
            output_path = os.path.join(workspace_path, DEFAULT_OUTPUT_DIR_NAME, args.filename)
            log.info(f"Using workspace default output directory '{DEFAULT_OUTPUT_DIR_NAME}'. Exporting to: '{output_path}'")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        log.info(f"Attempting to export shape to '{output_path}' (Format: {args.format or 'Infer'}, Options: {export_options})")
        export_shape_to_file(shape_to_export, output_path, args.format, export_options)
        log.info(f"Shape successfully exported via export_shape_to_file to '{output_path}'.")
        return {"success": True, "message": f"Shape successfully exported to {output_path}.", "filename": output_path}
    except Exception as e:
        error_msg = f"Error during shape export handling: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_export_shape_to_svg(app_context: AppContext, args: ExportShapeToSvgArgs, request_id: str) -> dict:
    """Export a generated CadQuery shape to SVG in the workspace render directory."""
    log.info(f"Handling export_shape_to_svg request (ID: {request_id})")
    try:
        export_options = args.options or {}
        workspace_path = os.path.abspath(args.workspace_path)
        if not os.path.isdir(workspace_path):
            raise ValueError(f"Invalid workspace path: {workspace_path}")

        shape_to_render = _load_shape_from_result(app_context, args.result_id, args.shape_index)

        render_dir_path = os.path.join(workspace_path, DEFAULT_OUTPUT_DIR_NAME, DEFAULT_RENDER_DIR_NAME)
        os.makedirs(render_dir_path, exist_ok=True)

        default_svg_name = f"render_{uuid.uuid4()}.svg"
        base_filename = os.path.basename(args.filename or default_svg_name)
        if not base_filename.lower().endswith(".svg"):
            base_filename += ".svg"
            log.warning(f"Appended .svg to filename. New base filename: {base_filename}")

        output_path = os.path.join(render_dir_path, base_filename)
        svg_opts = {
            "width": 400,
            "height": 300,
            "marginLeft": 10,
            "marginTop": 10,
            "showAxes": False,
            "projectionDir": (0.5, 0.5, 0.5),
            "strokeWidth": 0.25,
            "strokeColor": (0, 0, 0),
            "hiddenColor": (0, 0, 255, 100),
            "showHidden": False,
        }
        svg_opts.update(export_options)

        export_shape_to_svg_file(shape_to_render, output_path, svg_opts)
        return {"success": True, "message": f"Shape successfully exported to SVG: {output_path}.", "filename": output_path}
    except Exception as e:
        error_msg = f"Error during SVG export handling: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_get_shape_properties(app_context: AppContext, args: GetShapePropertiesArgs, request_id: str) -> dict:
    """Return properties for a generated CadQuery shape."""
    log.info(f"Handling get_shape_properties request (ID: {request_id})")
    try:
        shape_object = _load_shape_from_result(app_context, args.result_id, args.shape_index)
        properties = get_shape_properties(shape_object)
        log.info(f"Retrieved properties for shape {args.shape_index} from result ID '{args.result_id}'.")
        return {"success": True, "message": "Shape properties retrieved successfully.", "properties": properties}
    except Exception as e:
        error_msg = f"Error getting shape properties: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_get_shape_description(app_context: AppContext, args: GetShapeDescriptionArgs, request_id: str) -> dict:
    """Return a textual description for a generated CadQuery shape."""
    log.info(f"Handling get_shape_description request (ID: {request_id})")
    try:
        shape_object = _load_shape_from_result(app_context, args.result_id, args.shape_index)
        description = get_shape_description(shape_object)
        log.info(f"Generated description for shape {args.shape_index} from result ID '{args.result_id}'.")
        return {"success": True, "message": "Shape description generated successfully.", "description": description}
    except Exception as e:
        error_msg = f"Error getting shape description: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)

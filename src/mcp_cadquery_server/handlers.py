# This module contains all tool handler functions and the tool_handlers dict

import os
import uuid
import subprocess
import ast
from typing import Any

import cadquery as cq

from src.mcp_cadquery_server.env_setup import (
    prepare_workspace_env,
    _run_command_helper,
    workspace_env_signature_cache,
    workspace_reqs_mtime_cache,
)
from src.mcp_cadquery_server.core import (
    execute_cqgi_script,
    export_shape_to_file,
    export_shape_to_svg_file,
    parse_docstring_metadata,
    get_shape_properties as core_get_shape_properties,
    get_shape_description as core_get_shape_description,
    analyze_cad_file as core_analyze_cad_file,
    transform_stl_mesh as core_transform_stl_mesh,
    compare_stl_meshes as core_compare_stl_meshes,
)

from src.mcp_cadquery_server.models import (
    ExecuteCadqueryScriptArgs,
    BuildAndExportStlArgs,
    AnalyzeCadFileArgs,
    TransformStlMeshArgs,
    CompareStlMeshesArgs,
)
from src.mcp_cadquery_server.worker_pool import cadquery_worker_pool

from . import state
# Import shared state and config
from .state import (
    log,
    shape_results,
    part_index,
    DEFAULT_PART_LIBRARY_DIR,
    DEFAULT_OUTPUT_DIR_NAME,
    DEFAULT_RENDER_DIR_NAME,
)

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
                "script": args.script,
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
        # Generate a relative URL if static serving is enabled, otherwise just return path
        output_url_or_path = output_path # Default to path
        if state.ACTIVE_STATIC_DIR: # Check if static serving is active
            # Construct URL relative to static dir root
            try:
                rel_path = os.path.relpath(output_path, state.ACTIVE_STATIC_DIR)
                if not rel_path.startswith(".."): # Ensure it's within static dir
                    output_url_or_path = "/" + rel_path.replace(os.sep, "/")
                    log.info(f"Generated relative URL for SVG: {output_url_or_path}")
                else:
                    log.warning(f"SVG output path '{output_path}' is outside static dir '{state.ACTIVE_STATIC_DIR}'. Returning absolute path.")
            except ValueError: # Handle case where paths are on different drives (Windows)
                 log.warning(f"Could not determine relative path for SVG from '{output_path}' to '{state.ACTIVE_STATIC_DIR}'. Returning absolute path.")


        # Default SVG options (can be overridden)
        svg_opts = {"width": 400, "height": 300, "marginLeft": 10, "marginTop": 10, "showAxes": False, "projectionDir": (0.5, 0.5, 0.5), "strokeWidth": 0.25, "strokeColor": (0, 0, 0), "hiddenColor": (0, 0, 255, 100), "showHidden": False}
        svg_opts.update(export_options)

        # Call core SVG export function
        export_shape_to_svg_file(shape_to_render, output_path, svg_opts)

        return {"success": True, "message": f"Shape successfully exported to SVG: {output_url_or_path}.", "filename": output_url_or_path}
    except Exception as e: error_msg = f"Error during SVG export handling: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)

def handle_scan_part_library(request: dict) -> dict:
    """
    Handles the 'scan_part_library' tool request.
    Scans a specified directory (or the default) for CadQuery part scripts (.py),
    executes them to get metadata and generate previews, and updates the part_index.
    Uses the ACTIVE configured paths for library and previews.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling scan_part_library request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        # Use ACTIVE_PART_LIBRARY_DIR if workspace_path not provided
        workspace_path_arg = args.get("workspace_path", state.ACTIVE_PART_LIBRARY_DIR)
        if not workspace_path_arg:
            raise ValueError("Missing 'workspace_path' argument and no default library path configured.")

        library_path = os.path.abspath(workspace_path_arg)
        workspace_part_library_path = os.path.join(library_path, DEFAULT_PART_LIBRARY_DIR)
        if (
            os.path.isdir(workspace_part_library_path)
            and not any(name.endswith(".py") and not name.startswith("_") for name in os.listdir(library_path))
        ):
            library_path = workspace_part_library_path
        # Use ACTIVE_PART_PREVIEW_DIR_PATH for previews
        preview_dir_path = state.ACTIVE_PART_PREVIEW_DIR_PATH
        if not preview_dir_path:
             raise ValueError("Part preview directory path is not configured.")

        # Determine preview URL base if static serving is active
        preview_dir_url_base = None
        if state.ACTIVE_STATIC_DIR:
            try:
                rel_path = os.path.relpath(preview_dir_path, state.ACTIVE_STATIC_DIR)
                if not rel_path.startswith(".."):
                    preview_dir_url_base = "/" + rel_path.replace(os.sep, "/")
                    log.info(f"Using preview URL base: {preview_dir_url_base}")
                else:
                    log.warning(f"Preview directory '{preview_dir_path}' is outside static dir '{state.ACTIVE_STATIC_DIR}'. Previews may not be accessible via URL.")
            except ValueError:
                 log.warning(f"Could not determine relative path for preview dir '{preview_dir_path}' to static dir '{state.ACTIVE_STATIC_DIR}'. Previews may not be accessible via URL.")


        if not os.path.isdir(library_path):
            raise ValueError(f"Part library directory not found: {library_path}")
        if not os.path.isdir(preview_dir_path):
             log.warning(f"Preview directory '{preview_dir_path}' not found. Creating it.")
             os.makedirs(preview_dir_path, exist_ok=True)

        scanned_count, indexed_count, updated_count, cached_count, error_count = 0, 0, 0, 0, 0
        found_parts = set()
        default_svg_opts = {"width": 150, "height": 100, "showAxes": False}

        # Ensure the library path itself exists before listing directory
        if not os.path.isdir(library_path):
            log.warning(f"Part library directory '{library_path}' does not exist. Scan aborted.")
            return {"success": True, "message": f"Part library directory '{library_path}' not found.", "scanned": 0, "indexed": 0, "updated": 0, "cached": 0, "removed": 0, "errors": 0}


        for filename in os.listdir(library_path):
            if filename.endswith(".py") and not filename.startswith("_"):
                scanned_count += 1
                part_name = os.path.splitext(filename)[0]
                found_parts.add(part_name)
                file_path = os.path.join(library_path, filename)
                error_msg = None
                try:
                    current_mtime = os.path.getmtime(file_path)
                    cached_data = part_index.get(part_name)
                    if cached_data and cached_data.get('mtime') == current_mtime:
                        log.debug(f"Using cached data for part: {filename}")
                        cached_count += 1
                        continue

                    log.info(f"Processing part: {filename} (new or modified)")
                    with open(file_path, 'r', encoding='utf-8') as f:
                        script_content = f.read()

                    # Execute in the *current* server environment, assuming parts don't need isolated envs
                    # If isolation is needed, this would need to use script_runner via subprocess
                    build_result = execute_cqgi_script(script_content) # Using core function directly

                    if build_result.success and build_result.results:
                        shape_to_preview = build_result.results[0].shape
                        preview_filename = f"{part_name}.svg"
                        preview_output_path = os.path.join(preview_dir_path, preview_filename)

                        # Determine preview URL
                        preview_output_url = None
                        if preview_dir_url_base:
                            preview_output_url = f"{preview_dir_url_base}/{preview_filename}"
                        else:
                            preview_output_url = preview_output_path # Fallback to path if no URL base

                        export_shape_to_svg_file(shape_to_preview, preview_output_path, default_svg_opts)

                        # Parse metadata from docstring
                        tree = ast.parse(script_content)
                        docstring = ast.get_docstring(tree)
                        metadata = parse_docstring_metadata(docstring)
                        metadata['filename'] = filename # Add filename to metadata

                        part_data = {
                            "part_id": part_name,
                            "metadata": metadata,
                            "preview_url": preview_output_url, # Use URL or path
                            "script_path": file_path,
                            "mtime": current_mtime
                        }
                        if part_name in part_index: updated_count += 1
                        else: indexed_count += 1
                        part_index[part_name] = part_data
                        log.info(f"Successfully indexed/updated part: {part_name}")
                    elif not build_result.results:
                        log.warning(f"Part script {filename} executed successfully but produced no results. Skipping indexing.")
                        error_count += 1
                    else: # Build failed
                        log.error(f"Failed to execute part script {filename}: {build_result.exception}")
                        error_count += 1

                except SyntaxError as e: error_msg = f"Syntax error parsing {filename}: {e}"; error_count += 1
                except Exception as e: error_msg = f"Error processing {filename}: {e}"; error_count += 1
                if error_msg: log.error(error_msg, exc_info=True)

        # Remove parts from index that are no longer found
        removed_count = 0
        indexed_parts = set(part_index.keys())
        parts_to_remove = indexed_parts - found_parts
        for part_name_to_remove in parts_to_remove:
            log.info(f"Removing deleted part from index: {part_name_to_remove}")
            removed_data = part_index.pop(part_name_to_remove, None)
            # Attempt to remove the preview file
            if removed_data and 'preview_url' in removed_data:
                 # Try to reconstruct the path from URL or use path directly
                 preview_path_to_remove = None
                 if preview_dir_url_base and removed_data['preview_url'].startswith(preview_dir_url_base):
                      preview_filename = os.path.basename(removed_data['preview_url'])
                      preview_path_to_remove = os.path.join(preview_dir_path, preview_filename)
                 elif os.path.exists(removed_data['preview_url']): # Check if it's a path
                      preview_path_to_remove = removed_data['preview_url']

                 if preview_path_to_remove and os.path.exists(preview_path_to_remove):
                     try:
                         os.remove(preview_path_to_remove)
                         log.info(f"Removed preview file: {preview_path_to_remove}")
                     except OSError as e:
                         log.error(f"Error removing preview file {preview_path_to_remove}: {e}")
            removed_count += 1

        summary_msg = (f"Scan complete. Scanned: {scanned_count}, Newly Indexed: {indexed_count}, "
                       f"Updated: {updated_count}, Cached: {cached_count}, Removed: {removed_count}, Errors: {error_count}.")
        log.info(summary_msg)
        return { "success": True, "message": summary_msg, "scanned": scanned_count, "indexed": indexed_count, "updated": updated_count, "cached": cached_count, "removed": removed_count, "errors": error_count }
    except Exception as e: error_msg = f"Error during part library scan: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)


def handle_save_workspace_module(request: dict) -> dict:
    """Handles saving Python module content to a workspace."""
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling save_workspace_module request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        workspace_path_arg = args.get("workspace_path")
        module_filename = args.get("module_filename")
        module_content = args.get("module_content")

        if not workspace_path_arg: raise ValueError("Missing 'workspace_path' argument.")
        if not module_filename: raise ValueError("Missing 'module_filename' argument.")
        if module_content is None: raise ValueError("Missing 'module_content' argument.") # Allow empty string
        if not module_filename.endswith(".py"): raise ValueError("'module_filename' must end with .py")
        if os.path.sep in module_filename or (os.altsep and os.altsep in module_filename):
             raise ValueError("'module_filename' cannot contain path separators.")

        workspace_path = os.path.abspath(workspace_path_arg)
        if not os.path.isdir(workspace_path): raise ValueError(f"Invalid workspace path: {workspace_path}")

        # Define the 'modules' subdirectory within the workspace
        modules_dir = os.path.join(workspace_path, "modules")
        os.makedirs(modules_dir, exist_ok=True)

        # Prevent writing outside the modules directory
        target_path = os.path.abspath(os.path.join(modules_dir, module_filename))
        if not target_path.startswith(os.path.abspath(modules_dir)):
             raise ValueError("Invalid module filename, attempted path traversal.")

        log.info(f"Saving module content to: {target_path}")
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(module_content)

        cadquery_worker_pool.close_workspace(workspace_path)

        return {"success": True, "message": f"Module saved successfully to {target_path}.", "filename": target_path}
    except Exception as e: error_msg = f"Error saving workspace module: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)

def handle_install_workspace_package(request: dict) -> dict:
    """Handles installing a package into a workspace environment using uv."""
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling install_workspace_package request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        workspace_path_arg = args.get("workspace_path")
        package_name = args.get("package_name")

        if not workspace_path_arg: raise ValueError("Missing 'workspace_path' argument.")
        if not package_name: raise ValueError("Missing 'package_name' argument.")

        workspace_path = os.path.abspath(workspace_path_arg)
        log_prefix = f"InstallPkg({os.path.basename(workspace_path)})"
        log.info(f"[{log_prefix}] Request to install '{package_name}' into workspace: {workspace_path}")

        # Ensure the environment exists first (prepare_workspace_env handles creation/update)
        workspace_python_exe = prepare_workspace_env(workspace_path)

        # Construct the uv install command
        # Use the specific python from the workspace venv to ensure install goes there
        install_cmd = [
            "uv", "pip", "install", package_name,
            "--python", workspace_python_exe
        ]

        log.info(f"[{log_prefix}] Running install command: {' '.join(install_cmd)}")
        # Run the command using the helper, capturing output
        process = _run_command_helper(install_cmd, log_prefix=log_prefix, cwd=workspace_path) # Run in workspace CWD

        log.info(f"[{log_prefix}] Successfully installed '{package_name}'.")
        reqs_file = os.path.join(workspace_path, "requirements.txt")
        if os.path.exists(reqs_file):
            workspace_reqs_mtime_cache[workspace_path] = os.path.getmtime(reqs_file)
        workspace_env_signature_cache.pop(workspace_path, None)
        cadquery_worker_pool.close_workspace(workspace_path)
        output = "\n".join(part for part in [process.stdout, process.stderr] if part)
        return {"success": True, "message": f"Package '{package_name}' installed successfully.", "output": output}

    except Exception as e: error_msg = f"Error installing workspace package: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)


def handle_search_parts(request: dict) -> dict:
    """Handles searching the indexed part library."""
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling search_parts request (ID: {request_id})")
    try:
        args = request.get("arguments", {})
        query = args.get("query", "").strip().lower()

        if not query:
            log.info("Empty search query, returning all indexed parts.")
            results = list(part_index.values())
            return {"success": True, "message": f"Found {len(results)} parts.", "results": results}

        log.info(f"Searching parts with query: '{query}'")
        search_terms = set(term.strip() for term in query.split() if term.strip())
        results = []
        for part_id, part_data in part_index.items():
            match_score = 0
            metadata = part_data.get("metadata", {})

            # Score based on matches in different fields
            if query in part_id.lower(): match_score += 5
            if query in metadata.get("part", "").lower(): match_score += 3 # Check 'part' field if exists
            if query in metadata.get("description", "").lower(): match_score += 2
            tags = metadata.get("tags", [])
            if isinstance(tags, list):
                 if any(term in tag for term in search_terms for tag in tags): match_score += 5
            if query in metadata.get("filename", "").lower(): match_score += 1

            if match_score > 0:
                results.append({"score": match_score, "part": part_data})

        # Sort results by score (descending)
        results.sort(key=lambda x: x["score"], reverse=True)
        final_results = [item["part"] for item in results]

        message = f"Found {len(final_results)} parts matching query '{query}'."
        log.info(message)
        return {"success": True, "message": message, "results": final_results}
    except Exception as e: error_msg = f"Error during part search: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)

def handle_launch_cq_editor(request: dict) -> dict:
    """
    Handles launching the standalone CQ-Editor application.
    Assumes CQ-Editor is installed and accessible in the system PATH.
    """
    request_id = request.get("request_id", "unknown")
    log.info(f"Handling launch_cq_editor request (ID: {request_id})")
    try:
        # Command to launch CQ-Editor (adjust if needed based on installation)
        # Common commands: 'cq-editor', 'cqeditor'
        cq_editor_command = "cq-editor"
        log.info(f"Attempting to launch CQ-Editor using command: '{cq_editor_command}'")

        # Use subprocess.Popen for non-blocking launch
        process = subprocess.Popen([cq_editor_command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)

        # Small delay to check if process started immediately (optional)
        try:
            process.wait(timeout=0.1)
            # If wait() returns quickly, it likely failed to launch
            stderr_output = process.stderr.read().decode('utf-8', errors='ignore')
            log.error(f"CQ-Editor command '{cq_editor_command}' exited immediately. Error: {stderr_output}")
            raise RuntimeError(f"Failed to launch CQ-Editor. Command exited immediately. Is it installed and in PATH? Error: {stderr_output}")
        except subprocess.TimeoutExpired:
            # Process is running, launch successful
            log.info(f"CQ-Editor launched successfully in background (PID: {process.pid}).")
            return {"success": True, "message": "CQ-Editor launched successfully."}
        except FileNotFoundError:
             log.error(f"CQ-Editor command '{cq_editor_command}' not found. Is CQ-Editor installed and in the system PATH?")
             raise FileNotFoundError(f"Command '{cq_editor_command}' not found. Ensure CQ-Editor is installed and in PATH.")
        except Exception as e:
             log.error(f"Error launching CQ-Editor: {e}", exc_info=True)
             raise Exception(f"An unexpected error occurred while launching CQ-Editor: {e}")

    except Exception as e: error_msg = f"Error launching CQ-Editor: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg)


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
    "export_shape": handle_export_shape,
    "export_shape_to_svg": handle_export_shape_to_svg,
    "analyze_cad_file": handle_analyze_cad_file,
    "transform_stl_mesh": handle_transform_stl_mesh,
    "compare_stl_meshes": handle_compare_stl_meshes,
    "scan_part_library": handle_scan_part_library,
    "search_parts": handle_search_parts,
    "launch_cq_editor": handle_launch_cq_editor,
    "get_shape_properties": handle_get_shape_properties,
    "get_shape_description": handle_get_shape_description,
    "save_workspace_module": handle_save_workspace_module,
    "install_workspace_package": handle_install_workspace_package,
}

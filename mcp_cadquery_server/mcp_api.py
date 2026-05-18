from typing import Dict, Any, Optional

# Import necessary components from other modules
from .state import log
from .handlers import tool_handlers


def _schema_for(model_class: Any) -> Dict[str, Any]:
    schema_method = getattr(model_class, "model_json_schema", None)
    if schema_method:
        return schema_method()
    return model_class.schema()


def get_tool_schemas() -> Dict[str, Dict[str, Any]]:
    """
    Generates input schemas for each tool based on Pydantic models.
    """
    from .models import (
        ExecuteCadqueryScriptArgs,
        BuildAndExportStlArgs,
        ExportShapeArgs,
        ExportShapeToSvgArgs,
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
        GetShapePropertiesArgs,
        GetShapeDescriptionArgs,
    )

    schemas = {
        "execute_cadquery_script": _schema_for(ExecuteCadqueryScriptArgs),
        "build_and_export_stl": _schema_for(BuildAndExportStlArgs),
        "create_printable_stl": _schema_for(BuildAndExportStlArgs),
        "export_shape": _schema_for(ExportShapeArgs),
        "export_shape_to_svg": _schema_for(ExportShapeToSvgArgs),
        "analyze_cad_file": _schema_for(AnalyzeCadFileArgs),
        "transform_stl_mesh": _schema_for(TransformStlMeshArgs),
        "compare_stl_meshes": _schema_for(CompareStlMeshesArgs),
        "inspect_stl_sections": _schema_for(InspectStlSectionsArgs),
        "inspect_stl_plane_sections": _schema_for(InspectStlPlaneSectionsArgs),
        "detect_mount_features": _schema_for(DetectMountFeaturesArgs),
        "render_stl_preview": _schema_for(RenderStlPreviewArgs),
        "validate_stl_solid": _schema_for(ValidateStlSolidArgs),
        "solidify_stl_mesh": _schema_for(SolidifyStlMeshArgs),
        "probe_stl_tunnel": _schema_for(ProbeStlTunnelArgs),
        "get_shape_properties": _schema_for(GetShapePropertiesArgs),
        "get_shape_description": _schema_for(GetShapeDescriptionArgs),
    }

    # Ensure all handlers have a schema entry.
    for tool_name in tool_handlers:
        if tool_name not in schemas:
            log.warning(f"No schema defined for tool: {tool_name}. Adding empty schema.")
            schemas[tool_name] = {"type": "object", "properties": {}, "required": []}
    return schemas

def get_server_info() -> dict:
    """Constructs the server_info message."""
    server_name = "mcp-cadquery-server"  # TODO: Make configurable?
    server_version = "0.2.0-workspace"  # TODO: Get version dynamically?
    tool_schemas = get_tool_schemas() # Call local function
    tools = []

    for name, handler in tool_handlers.items():
        schema = tool_schemas.get(name, {"type": "object", "properties": {}})
        # Get docstring, strip, and take only the first line
        docstring = getattr(handler, '__doc__', f"Executes the {name} tool.")
        description = docstring.strip().split('\n')[0] if docstring else f"Executes the {name} tool."

        tools.append({
            "name": name,
            "description": description,
            "input_schema": schema
        })

    return {
        "type": "server_info",
        "server_name": server_name,
        "version": server_version,
        "tools": tools,
        "resources": [] # Define if any resources are provided
    }

def process_tool_request(request: dict) -> Optional[dict]:
    """
    Processes a tool request synchronously and returns the stdio response payload.
    Returns None if no message should be sent.
    """
    request_id = request.get("request_id", "unknown")
    tool_name = request.get("tool_name")
    result_message: Optional[dict] = None
    error_message: Optional[str] = None
    log.debug(f"Processing tool request (ID: {request_id}, Tool: {tool_name})")
    try:
        handler = tool_handlers.get(tool_name)
        if handler:
            # Execute the handler function associated with the tool_name
            result_message = handler(request)
        else:
            error_message = f"Unknown tool: {tool_name}"
            log.warning(error_message)
    except Exception as e:
        log.error(f"Error processing tool '{tool_name}' (ID: {request_id}): {e}", exc_info=True)
        # Attempt to get a more specific error detail if available (e.g., from HTTPException)
        detail = getattr(e, 'detail', str(e))
        error_message = f"Internal server error processing {tool_name}: {detail}"

    log.debug(f"Tool processing complete (ID: {request_id}). Error: {error_message}, Result: {result_message}")

    # Construct the response message
    message_to_push: Optional[dict] = None
    if error_message:
        message_to_push = {"type": "tool_error", "request_id": request_id, "error": error_message}
    elif result_message is not None: # Ensure result_message is not None before creating result message
         message_to_push = {"type": "tool_result", "request_id": request_id, "result": result_message}
    else:
        # This case might happen if a handler intentionally returns None or has no return value
        log.warning(f"No result or error message generated for request ID: {request_id}, tool: {tool_name}")
        # Optionally send a generic success/no-op message, or just return None
        # Example: message_to_push = {"type": "tool_result", "request_id": request_id, "result": {"success": True, "message": "Operation completed with no specific output."}}

    return message_to_push

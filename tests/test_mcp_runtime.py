from mcp_cadquery_server.mcp_api import get_server_info, process_tool_request
from mcp_cadquery_server.stdio_server import _handle_jsonrpc_request


EXPECTED_TOOLS = [
    "execute_cadquery_script",
    "build_and_export_stl",
    "create_printable_stl",
    "generate_model",
    "modify_model",
    "list_models",
    "export_shape",
    "export_shape_to_svg",
    "analyze_cad_file",
    "transform_stl_mesh",
    "compare_stl_meshes",
    "inspect_stl_sections",
    "inspect_stl_plane_sections",
    "detect_mount_features",
    "render_stl_preview",
    "validate_stl_solid",
    "solidify_stl_mesh",
    "probe_stl_tunnel",
    "get_shape_properties",
    "get_shape_description",
]


def test_registered_tools_are_runtime_tools_only():
    server_info = get_server_info()
    tool_names = [tool["name"] for tool in server_info["tools"]]

    assert tool_names == EXPECTED_TOOLS
    assert "input_schema" in server_info["tools"][0]
    assert "scan_part_library" not in tool_names
    assert "search_parts" not in tool_names
    assert "launch_cq_editor" not in tool_names


def test_jsonrpc_initialize_and_tools_list():
    initialize = _handle_jsonrpc_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert initialize["result"]["serverInfo"]["name"] == "mcp-cadquery-server"
    assert initialize["result"]["capabilities"] == {"tools": {}}

    tools_list = _handle_jsonrpc_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    assert [tool["name"] for tool in tools_list["result"]["tools"]] == EXPECTED_TOOLS
    assert all("inputSchema" in tool for tool in tools_list["result"]["tools"])


def test_unknown_tool_returns_tool_error():
    response = process_tool_request(
        {"request_id": "missing-tool", "tool_name": "not_a_tool", "arguments": {}}
    )
    assert response == {
        "type": "tool_error",
        "request_id": "missing-tool",
        "error": "Unknown tool: not_a_tool",
    }

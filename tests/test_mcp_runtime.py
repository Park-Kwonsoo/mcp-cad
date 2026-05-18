import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_cadquery_server.server import create_server


EXPECTED_TOOLS = [
    "execute_cadquery_script",
    "build_and_export_stl",
    "create_printable_stl",
    "export_shape",
    "export_shape_to_svg",
    "get_shape_properties",
    "get_shape_description",
    "generate_model",
    "modify_model",
    "list_models",
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
]


def test_fastmcp_registered_tools_are_runtime_tools_only():
    async def check_tools():
        tools = await create_server().list_tools()
        tool_names = [tool.name for tool in tools]
        assert tool_names == EXPECTED_TOOLS
        assert "scan_part_library" not in tool_names
        assert "search_parts" not in tool_names
        assert "launch_cq_editor" not in tool_names
        assert all(tool.inputSchema for tool in tools)

    anyio.run(check_tools)


def test_stdio_mcp_client_initialize_and_tools_list():
    async def check_stdio_server():
        env = dict(os.environ)
        env.setdefault("ANTHROPIC_API_KEY", "test-key")
        server = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / "server.py")],
            env=env,
            cwd=Path(__file__).resolve().parents[1],
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialize = await session.initialize()
                assert initialize.serverInfo.name == "mcp-cadquery-server"

                tools = await session.list_tools()
                tool_names = [tool.name for tool in tools.tools]
                assert tool_names == EXPECTED_TOOLS

    anyio.run(check_stdio_server)

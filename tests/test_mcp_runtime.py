import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_cadquery_server.schemas.ai_models import GenerateModelArgs, ListModelsArgs, ModifyModelArgs
from mcp_cadquery_server.schemas.cadquery import (
    BuildAndExportStlArgs,
    ExecuteCadqueryScriptArgs,
    ExportShapeArgs,
    ExportShapeToSvgArgs,
    GetShapeDescriptionArgs,
    GetShapePropertiesArgs,
)
from mcp_cadquery_server.schemas.stl import (
    AnalyzeCadFileArgs,
    CompareStlMeshesArgs,
    DetectMountFeaturesArgs,
    InspectStlPlaneSectionsArgs,
    InspectStlSectionsArgs,
    ProbeStlTunnelArgs,
    RenderStlPreviewArgs,
    SolidifyStlMeshArgs,
    TransformStlMeshArgs,
    ValidateStlSolidArgs,
    MoveStlHoleCentersArgs,
)
from mcp_cadquery_server.server import create_server
from mcp_cadquery_server.tools.ai_models import (
    GENERATE_MODEL_DESCRIPTION_FIELD,
    GENERATE_MODEL_TOOL_DESCRIPTION,
    MODIFY_MODEL_INSTRUCTION_FIELD,
    MODIFY_MODEL_TOOL_DESCRIPTION,
)


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
    "move_stl_hole_centers",
    "compare_stl_meshes",
    "inspect_stl_sections",
    "inspect_stl_plane_sections",
    "detect_mount_features",
    "render_stl_preview",
    "validate_stl_solid",
    "solidify_stl_mesh",
    "probe_stl_tunnel",
]

TOOL_ARG_MODELS = {
    "execute_cadquery_script": ExecuteCadqueryScriptArgs,
    "build_and_export_stl": BuildAndExportStlArgs,
    "create_printable_stl": BuildAndExportStlArgs,
    "export_shape": ExportShapeArgs,
    "export_shape_to_svg": ExportShapeToSvgArgs,
    "get_shape_properties": GetShapePropertiesArgs,
    "get_shape_description": GetShapeDescriptionArgs,
    "generate_model": GenerateModelArgs,
    "modify_model": ModifyModelArgs,
    "list_models": ListModelsArgs,
    "analyze_cad_file": AnalyzeCadFileArgs,
    "transform_stl_mesh": TransformStlMeshArgs,
    "compare_stl_meshes": CompareStlMeshesArgs,
    "inspect_stl_sections": InspectStlSectionsArgs,
    "inspect_stl_plane_sections": InspectStlPlaneSectionsArgs,
    "detect_mount_features": DetectMountFeaturesArgs,
    "render_stl_preview": RenderStlPreviewArgs,
    "validate_stl_solid": ValidateStlSolidArgs,
    "solidify_stl_mesh": SolidifyStlMeshArgs,
    "probe_stl_tunnel": ProbeStlTunnelArgs,
    "move_stl_hole_centers": MoveStlHoleCentersArgs,
}


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


def test_fastmcp_tool_signatures_match_pydantic_arg_models():
    async def check_tool_schemas():
        tools = await create_server().list_tools()
        for tool in tools:
            model = TOOL_ARG_MODELS[tool.name]
            model_schema = model.model_json_schema()
            assert set(tool.inputSchema.get("properties", {})) == set(model_schema.get("properties", {}))
            assert set(tool.inputSchema.get("required", [])) == set(model_schema.get("required", []))

    anyio.run(check_tool_schemas)


def test_ai_model_tool_descriptions_define_non_overlapping_scope():
    async def check_tool_descriptions():
        tools = {tool.name: tool for tool in await create_server().list_tools()}

        generate_model = tools["generate_model"]
        assert generate_model.description == GENERATE_MODEL_TOOL_DESCRIPTION
        assert "no CadQuery script or STL exists yet" in generate_model.description
        assert "execute_cadquery_script" in generate_model.description
        assert "STL tools" in generate_model.description
        assert (
            generate_model.inputSchema["properties"]["description"]["description"]
            == GENERATE_MODEL_DESCRIPTION_FIELD
        )

        modify_model = tools["modify_model"]
        assert modify_model.description == MODIFY_MODEL_TOOL_DESCRIPTION
        assert "model_id" in modify_model.description
        assert "source" in modify_model.description
        assert "transform_stl_mesh" in modify_model.description
        assert (
            modify_model.inputSchema["properties"]["instruction"]["description"]
            == MODIFY_MODEL_INSTRUCTION_FIELD
        )

    anyio.run(check_tool_descriptions)


def test_stl_tool_descriptions_explain_when_to_call_mesh_editing_tools():
    async def check_tool_descriptions():
        tools = {tool.name: tool for tool in await create_server().list_tools()}

        move_holes = tools["move_stl_hole_centers"]
        assert "existing STL" in move_holes.description
        assert "hole center" in move_holes.description
        assert "coordinate" in move_holes.description
        assert (
            "current measured center"
            in move_holes.inputSchema["properties"]["holes"]["description"]
        )

        analyze = tools["analyze_cad_file"]
        assert "Use before editing" in analyze.description
        assert "mounting holes" in analyze.description

    anyio.run(check_tool_descriptions)


def test_stdio_mcp_client_initialize_and_tools_list():
    async def check_stdio_server():
        env = dict(os.environ)
        env.setdefault("ANTHROPIC_API_KEY", "test-key")
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_cadquery_server.cli"],
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


def test_stdio_initialize_does_not_create_ai_runtime_dirs(tmp_path):
    async def check_stdio_server():
        models_dir = tmp_path / "models"
        workspace_dir = tmp_path / "workspace"
        env = dict(os.environ)
        env.setdefault("ANTHROPIC_API_KEY", "test-key")
        env["MCP_CAD_MODELS_DIR"] = str(models_dir)
        env["MCP_CAD_AI_WORKSPACE_DIR"] = str(workspace_dir)

        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_cadquery_server.cli"],
            env=env,
            cwd=Path(__file__).resolve().parents[1],
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                await session.list_tools()

        assert not models_dir.exists()
        assert not workspace_dir.exists()

    anyio.run(check_stdio_server)

from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from mcp_cadquery_server import handlers
from mcp_cadquery_server.models import ExecuteCadqueryScriptArgs

from ._request import tool_request


def register_cadquery_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def execute_cadquery_script(
        workspace_path: str,
        script: str,
        parameter_sets: Optional[list[dict[str, Any]]] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Run CadQuery Python to create or edit a CAD model when a script is already available."""
        args = ExecuteCadqueryScriptArgs(
            workspace_path=workspace_path,
            script=script,
            parameter_sets=parameter_sets,
            parameters=parameters,
        )
        return handlers.handle_execute_cadquery_script(args, request_id=tool_request({})["request_id"])

    @mcp.tool()
    def build_and_export_stl(
        workspace_path: str,
        script: str,
        filename: str,
        shape_index: int = 0,
        parameters: Optional[dict[str, Any]] = None,
        export_options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Create a 3D-printer-ready STL through MCP/CadQuery using real CadQuery solids."""
        return handlers.handle_build_and_export_stl(
            tool_request(
                {
                    "workspace_path": workspace_path,
                    "script": script,
                    "filename": filename,
                    "shape_index": shape_index,
                    "parameters": parameters,
                    "export_options": export_options,
                }
            )
        )

    @mcp.tool()
    def create_printable_stl(
        workspace_path: str,
        script: str,
        filename: str,
        shape_index: int = 0,
        parameters: Optional[dict[str, Any]] = None,
        export_options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Use this tool for make/print/output STL requests instead of mesh concatenation."""
        return handlers.handle_create_printable_stl(
            tool_request(
                {
                    "workspace_path": workspace_path,
                    "script": script,
                    "filename": filename,
                    "shape_index": shape_index,
                    "parameters": parameters,
                    "export_options": export_options,
                }
            )
        )

    @mcp.tool()
    def export_shape(
        workspace_path: str,
        result_id: str,
        filename: str,
        shape_index: int = 0,
        format: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Export a generated CadQuery shape to STL, STEP, BREP, or SVG."""
        return handlers.handle_export_shape(
            tool_request(
                {
                    "workspace_path": workspace_path,
                    "result_id": result_id,
                    "shape_index": shape_index,
                    "filename": filename,
                    "format": format,
                    "options": options,
                }
            )
        )

    @mcp.tool()
    def export_shape_to_svg(
        workspace_path: str,
        result_id: str,
        shape_index: int = 0,
        filename: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Export a generated CadQuery shape to SVG."""
        return handlers.handle_export_shape_to_svg(
            tool_request(
                {
                    "workspace_path": workspace_path,
                    "result_id": result_id,
                    "shape_index": shape_index,
                    "filename": filename,
                    "options": options,
                }
            )
        )

    @mcp.tool()
    def get_shape_properties(result_id: str, shape_index: int = 0) -> dict:
        """Return properties for a shape created by execute_cadquery_script."""
        return handlers.handle_get_shape_properties(
            tool_request(
                {
                    "result_id": result_id,
                    "shape_index": shape_index,
                }
            )
        )

    @mcp.tool()
    def get_shape_description(result_id: str, shape_index: int = 0) -> dict:
        """Return a textual description for a shape created by execute_cadquery_script."""
        return handlers.handle_get_shape_description(
            tool_request(
                {
                    "result_id": result_id,
                    "shape_index": shape_index,
                }
            )
        )

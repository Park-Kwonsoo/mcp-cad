from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context, FastMCP

from mcp_cadquery_server.schemas.cadquery import (
    BuildAndExportStlArgs,
    ExecuteCadqueryScriptArgs,
    ExportShapeArgs,
    ExportShapeToSvgArgs,
    GetShapeDescriptionArgs,
    GetShapePropertiesArgs,
)
from mcp_cadquery_server.services import cadquery as cadquery_service

from ._context import app_context


def register_cadquery_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def execute_cadquery_script(
        ctx: Context,
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
        return cadquery_service.handle_execute_cadquery_script(app_context(ctx), args, request_id=ctx.request_id)

    @mcp.tool()
    def build_and_export_stl(
        ctx: Context,
        workspace_path: str,
        script: str,
        filename: str,
        shape_index: int = 0,
        parameters: Optional[dict[str, Any]] = None,
        export_options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Create a 3D-printer-ready STL through MCP/CadQuery using real CadQuery solids."""
        return cadquery_service.handle_build_and_export_stl(
            app_context(ctx),
            BuildAndExportStlArgs(
                workspace_path=workspace_path,
                script=script,
                filename=filename,
                shape_index=shape_index,
                parameters=parameters,
                export_options=export_options,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def create_printable_stl(
        ctx: Context,
        workspace_path: str,
        script: str,
        filename: str,
        shape_index: int = 0,
        parameters: Optional[dict[str, Any]] = None,
        export_options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Use this tool for make/print/output STL requests instead of mesh concatenation."""
        return cadquery_service.handle_create_printable_stl(
            app_context(ctx),
            BuildAndExportStlArgs(
                workspace_path=workspace_path,
                script=script,
                filename=filename,
                shape_index=shape_index,
                parameters=parameters,
                export_options=export_options,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def export_shape(
        ctx: Context,
        workspace_path: str,
        result_id: str,
        filename: str,
        shape_index: int = 0,
        format: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Export a generated CadQuery shape to STL, STEP, BREP, or SVG."""
        return cadquery_service.handle_export_shape(
            app_context(ctx),
            ExportShapeArgs(
                workspace_path=workspace_path,
                result_id=result_id,
                shape_index=shape_index,
                filename=filename,
                format=format,
                options=options,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def export_shape_to_svg(
        ctx: Context,
        workspace_path: str,
        result_id: str,
        shape_index: int = 0,
        filename: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Export a generated CadQuery shape to SVG."""
        return cadquery_service.handle_export_shape_to_svg(
            app_context(ctx),
            ExportShapeToSvgArgs(
                workspace_path=workspace_path,
                result_id=result_id,
                shape_index=shape_index,
                filename=filename,
                options=options,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def get_shape_properties(ctx: Context, result_id: str, shape_index: int = 0) -> dict:
        """Return properties for a shape created by execute_cadquery_script."""
        return cadquery_service.handle_get_shape_properties(
            app_context(ctx),
            GetShapePropertiesArgs(result_id=result_id, shape_index=shape_index),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def get_shape_description(ctx: Context, result_id: str, shape_index: int = 0) -> dict:
        """Return a textual description for a shape created by execute_cadquery_script."""
        return cadquery_service.handle_get_shape_description(
            app_context(ctx),
            GetShapeDescriptionArgs(result_id=result_id, shape_index=shape_index),
            request_id=ctx.request_id,
        )

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> None:
    from .ai_models import register_ai_model_tools
    from .cadquery import register_cadquery_tools
    from .stl import register_stl_tools

    register_cadquery_tools(mcp)
    register_ai_model_tools(mcp)
    register_stl_tools(mcp)

from __future__ import annotations

from mcp.server.fastmcp import Context

from mcp_cadquery_server.context import AppContext


def app_context(ctx: Context) -> AppContext:
    return ctx.request_context.lifespan_context


from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from .config import ServerConfig
from .context import AppContext
from .services.worker_pool import CadQueryWorkerPool
from .tools import register_tools


def create_server(config: ServerConfig | None = None) -> FastMCP[AppContext]:
    server_config = config or ServerConfig.from_env()

    @asynccontextmanager
    async def lifespan(_: FastMCP[AppContext]) -> AsyncIterator[AppContext]:
        worker_pool = CadQueryWorkerPool()
        try:
            yield AppContext(
                config=server_config,
                shape_results={},
                worker_pool=worker_pool,
            )
        finally:
            worker_pool.close()

    mcp = FastMCP(
        "mcp-cadquery-server",
        instructions="CadQuery MCP server for generating, exporting, and inspecting 3D-printable CAD models.",
        lifespan=lifespan,
    )
    register_tools(mcp)
    return mcp


def run_stdio(config: ServerConfig | None = None) -> None:
    create_server(config).run("stdio")

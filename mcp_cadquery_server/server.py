from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from .config import ServerConfig
from .context import AppContext
from .services import ai_generator
from .services import ai_models as ai_model_service
from .services import model_store
from .services.worker_pool import cadquery_worker_pool
from .state import shape_results
from .tools import register_tools


def _apply_config(config: ServerConfig) -> None:
    os.makedirs(config.models_dir, exist_ok=True)
    os.makedirs(config.ai_workspace_dir, exist_ok=True)
    model_store.MODELS_DIR = config.models_dir
    ai_model_service.MODELS_DIR = config.models_dir
    ai_model_service.AI_WORKSPACE_DIR = config.ai_workspace_dir
    ai_generator.MODEL = config.anthropic_model


def create_server(config: ServerConfig | None = None) -> FastMCP[AppContext]:
    server_config = config or ServerConfig.from_env()

    @asynccontextmanager
    async def lifespan(_: FastMCP[AppContext]) -> AsyncIterator[AppContext]:
        _apply_config(server_config)
        try:
            yield AppContext(
                config=server_config,
                shape_results=shape_results,
                worker_pool=cadquery_worker_pool,
            )
        finally:
            cadquery_worker_pool.close()

    mcp = FastMCP(
        "mcp-cadquery-server",
        instructions="CadQuery MCP server for generating, exporting, and inspecting 3D-printable CAD models.",
        lifespan=lifespan,
    )
    register_tools(mcp)
    return mcp


def run_stdio(config: ServerConfig | None = None) -> None:
    create_server(config).run("stdio")

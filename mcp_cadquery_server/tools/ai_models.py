from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import Context, FastMCP

from mcp_cadquery_server.schemas.ai_models import GenerateModelArgs, ListModelsArgs, ModifyModelArgs
from mcp_cadquery_server.services import ai_models as ai_model_service

from ._context import app_context


def register_ai_model_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def generate_model(
        ctx: Context,
        description: str,
        image_path: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> dict:
        """Generate a CadQuery model from text or image input, export it to STL, and store model metadata."""
        return ai_model_service.handle_generate_model(
            app_context(ctx),
            GenerateModelArgs(description=description, image_path=image_path, model_id=model_id),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def modify_model(ctx: Context, model_id: str, instruction: str) -> dict:
        """Modify a stored model by regenerating its CadQuery code and appending a new STL version."""
        return ai_model_service.handle_modify_model(
            app_context(ctx),
            ModifyModelArgs(model_id=model_id, instruction=instruction),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def list_models(ctx: Context) -> dict:
        """List stored AI-generated CadQuery models and their latest STL metadata."""
        return ai_model_service.handle_list_models(app_context(ctx), ListModelsArgs())

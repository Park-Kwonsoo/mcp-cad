from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from mcp_cadquery_server import handlers

from ._request import tool_request


def register_ai_model_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def generate_model(description: str, image_path: Optional[str] = None, model_id: Optional[str] = None) -> dict:
        """Generate a CadQuery model from text or image input, export it to STL, and store model metadata."""
        return handlers.handle_generate_model(
            tool_request(
                {
                    "description": description,
                    "image_path": image_path,
                    "model_id": model_id,
                }
            )
        )

    @mcp.tool()
    def modify_model(model_id: str, instruction: str) -> dict:
        """Modify a stored model by regenerating its CadQuery code and appending a new STL version."""
        return handlers.handle_modify_model(
            tool_request(
                {
                    "model_id": model_id,
                    "instruction": instruction,
                }
            )
        )

    @mcp.tool()
    def list_models() -> dict:
        """List stored AI-generated CadQuery models and their latest STL metadata."""
        return handlers.handle_list_models(tool_request({}))

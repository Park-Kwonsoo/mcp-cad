from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Annotated, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from mcp_cadquery_server.schemas.ai_models import GenerateModelArgs, ListModelsArgs, ModifyModelArgs
from mcp_cadquery_server.services import ai_models as ai_model_service

from ._context import app_context


@lru_cache(maxsize=None)
def _load_prompt_sections(filename: str) -> dict[str, str]:
    prompt_path = files(__package__).joinpath("prompts", filename)
    sections: dict[str, list[str]] = {}
    current_key: str | None = None

    for line in prompt_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current_key = line[3:].strip()
            sections[current_key] = []
            continue
        if current_key is None:
            continue
        sections[current_key].append(line)

    return {
        key: " ".join(part.strip() for part in parts).strip()
        for key, parts in sections.items()
    }


def _prompt_section(filename: str, key: str) -> str:
    try:
        return _load_prompt_sections(filename)[key]
    except KeyError as exc:
        raise RuntimeError(f"Missing prompt section {key!r} in {filename}") from exc


GENERATE_MODEL_TOOL_DESCRIPTION = _prompt_section("generate_models.md", "tool_description")
GENERATE_MODEL_DESCRIPTION_FIELD = _prompt_section("generate_models.md", "description_field")
GENERATE_MODEL_IMAGE_PATH_FIELD = _prompt_section("generate_models.md", "image_path_field")
GENERATE_MODEL_ID_FIELD = _prompt_section("generate_models.md", "model_id_field")

MODIFY_MODEL_TOOL_DESCRIPTION = _prompt_section("modify_models.md", "tool_description")
MODIFY_MODEL_ID_FIELD = _prompt_section("modify_models.md", "model_id_field")
MODIFY_MODEL_INSTRUCTION_FIELD = _prompt_section("modify_models.md", "instruction_field")

GenerateDescription = Annotated[str, Field(description=GENERATE_MODEL_DESCRIPTION_FIELD)]
ReferenceImagePath = Annotated[Optional[str], Field(description=GENERATE_MODEL_IMAGE_PATH_FIELD)]
NewModelId = Annotated[Optional[str], Field(description=GENERATE_MODEL_ID_FIELD)]
ExistingModelId = Annotated[str, Field(description=MODIFY_MODEL_ID_FIELD)]
ModificationInstruction = Annotated[str, Field(description=MODIFY_MODEL_INSTRUCTION_FIELD)]


def register_ai_model_tools(mcp: FastMCP) -> None:
    @mcp.tool(description=GENERATE_MODEL_TOOL_DESCRIPTION)
    def generate_model(
        ctx: Context,
        description: GenerateDescription,
        image_path: ReferenceImagePath = None,
        model_id: NewModelId = None,
    ) -> dict:
        return ai_model_service.handle_generate_model(
            app_context(ctx),
            GenerateModelArgs(description=description, image_path=image_path, model_id=model_id),
            request_id=ctx.request_id,
        )

    @mcp.tool(description=MODIFY_MODEL_TOOL_DESCRIPTION)
    def modify_model(ctx: Context, model_id: ExistingModelId, instruction: ModificationInstruction) -> dict:
        return ai_model_service.handle_modify_model(
            app_context(ctx),
            ModifyModelArgs(model_id=model_id, instruction=instruction),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def list_models(ctx: Context) -> dict:
        """List stored AI-generated CadQuery models and their latest STL metadata."""
        return ai_model_service.handle_list_models(app_context(ctx), ListModelsArgs())

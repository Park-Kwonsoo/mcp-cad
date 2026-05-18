from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GenerateModelArgs(BaseModel):
    description: str = Field(
        ...,
        description="Natural-language requirements for a new AI-generated CadQuery model.",
    )
    image_path: Optional[str] = Field(
        None,
        description="Optional local image path to use as a visual reference.",
    )
    model_id: Optional[str] = Field(
        None,
        description="Optional stable model identifier; generated when omitted.",
    )


class ModifyModelArgs(BaseModel):
    model_id: str = Field(
        ...,
        description="Model identifier returned by generate_model or list_models.",
    )
    instruction: str = Field(
        ...,
        description="Text instruction describing how to revise the latest model version.",
    )


class ListModelsArgs(BaseModel):
    pass

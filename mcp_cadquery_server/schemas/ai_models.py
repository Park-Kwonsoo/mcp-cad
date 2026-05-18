from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GenerateModelArgs(BaseModel):
    description: str = Field(..., description="Text prompt describing the 3D model to generate")
    image_path: Optional[str] = Field(None, description="Optional local image path to use as visual reference")
    model_id: Optional[str] = Field(None, description="Optional stable model identifier; generated when omitted")


class ModifyModelArgs(BaseModel):
    model_id: str = Field(..., description="Model identifier returned by generate_model")
    instruction: str = Field(..., description="Text instruction describing how to modify the latest model version")


class ListModelsArgs(BaseModel):
    pass

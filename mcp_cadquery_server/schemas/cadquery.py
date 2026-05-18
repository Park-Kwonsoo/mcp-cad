from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExecuteCadqueryScriptArgs(BaseModel):
    workspace_path: str = Field(..., description="Path to the CadQuery workspace directory")
    script: str = Field(..., description="CadQuery Python script content to execute for creating or editing a CAD model")
    parameter_sets: Optional[List[Dict[str, Any]]] = Field(
        None, description="List of parameter dictionaries for multiple executions"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None, description="Single parameter dictionary (converted to parameter_sets internally)"
    )


class ExportShapeArgs(BaseModel):
    workspace_path: str = Field(..., description="Path to the CadQuery workspace directory")
    result_id: str = Field(..., description="Result ID from script execution")
    shape_index: int = Field(0, description="Index of the shape in the result list")
    filename: str = Field(..., description="Target filename or path for the exported CAD/3D-print file")
    format: Optional[str] = Field(None, description="Export format such as STL for 3D printing, STEP, BREP, or SVG")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="CadQuery export options dictionary")


class ExportShapeToSvgArgs(BaseModel):
    workspace_path: str = Field(..., description="Path to the workspace directory")
    result_id: str = Field(..., description="Result ID from script execution")
    shape_index: int = Field(0, description="Index of the shape in the result list")
    filename: Optional[str] = Field(None, description="Optional target filename for SVG export")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="SVG export options dictionary")


class BuildAndExportStlArgs(BaseModel):
    workspace_path: str = Field(..., description="Path to the CadQuery workspace directory")
    script: str = Field(
        ...,
        description="CadQuery Python script generated from a text or image+text design request; must create one printable model with real CadQuery boolean unions/cuts instead of STL mesh concatenation; either call show_object(model) or assign the final object to result",
    )
    filename: str = Field(..., description="Target .stl filename or path for the 3D-printer-ready output")
    shape_index: int = Field(0, description="Index of the generated shape to export as STL")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Optional dimensions or design parameters for the script")
    export_options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="STL export options dictionary")


class GetShapePropertiesArgs(BaseModel):
    result_id: str = Field(..., description="Result ID from script execution")
    shape_index: int = Field(0, description="Index of the shape in the result list")


class GetShapeDescriptionArgs(BaseModel):
    result_id: str = Field(..., description="Result ID from script execution")
    shape_index: int = Field(0, description="Index of the shape in the result list")

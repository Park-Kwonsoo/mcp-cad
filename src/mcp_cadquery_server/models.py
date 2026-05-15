from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, root_validator


class ExecuteCadqueryScriptArgs(BaseModel):
    workspace_path: str = Field(..., description="Path to the CadQuery workspace directory")
    script: str = Field(..., description="CadQuery Python script content to execute for creating or editing a CAD model")
    parameter_sets: Optional[List[Dict[str, Any]]] = Field(
        None, description="List of parameter dictionaries for multiple executions"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None, description="Single parameter dictionary (converted to parameter_sets internally)"
    )

    @root_validator(skip_on_failure=True)
    def check_params(cls, values):
        param_sets, params = values.get('parameter_sets'), values.get('parameters')
        if param_sets is not None:
            if not isinstance(param_sets, list):
                raise ValueError("'parameter_sets' must be a list of dictionaries")
            if not all(isinstance(p, dict) for p in param_sets):
                raise ValueError("Each item in 'parameter_sets' must be a dictionary")
        if params is not None and not isinstance(params, dict):
            raise ValueError("'parameters' must be a dictionary")
        return values


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
        description="CadQuery Python script generated from a text or image+text design request; must create one printable model with real CadQuery boolean unions/cuts instead of STL mesh concatenation",
    )
    filename: str = Field(..., description="Target .stl filename or path for the 3D-printer-ready output")
    shape_index: int = Field(0, description="Index of the generated shape to export as STL")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Optional dimensions or design parameters for the script")
    export_options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="STL export options dictionary")


class AnalyzeCadFileArgs(BaseModel):
    file_path: str = Field(..., description="Path to an existing STL, STEP/STP, BREP, BIN, or DXF file to inspect before redesign, resizing, or 3D printing; STL analysis reports watertightness, non-manifold edges, and disconnected shell counts")
    file_format: Optional[str] = Field(None, description="Optional file format override")


class TransformStlMeshArgs(BaseModel):
    file_path: str = Field(..., description="Path to the source STL file to resize or reposition")
    output_path: str = Field(..., description="Path where the resized or transformed 3D-printer STL file will be written")
    scale: Optional[Dict[str, float]] = Field(None, description="Per-axis STL scale factors, e.g. {'x': 2.0}")
    target_size: Optional[Dict[str, float]] = Field(None, description="Target STL bounding-box dimensions by axis for dimension changes")
    translate: Optional[Dict[str, float]] = Field(None, description="Per-axis STL translation after scaling/rotation")
    rotate_degrees: Optional[Dict[str, float]] = Field(None, description="STL Euler rotations in degrees by x/y/z")
    center_at_origin: bool = Field(False, description="Whether to move the transformed STL mesh center to the origin")


class CompareStlMeshesArgs(BaseModel):
    source_file_path: str = Field(..., description="Path to the original/source STL mesh; use this MCP tool instead of ad hoc local Python STL parsing")
    target_file_path: str = Field(..., description="Path to the generated, redesigned, or transformed STL mesh to compare against the source")
    source_translate: Optional[Dict[str, float]] = Field(None, description="Optional x/y/z translation applied to the source STL before comparison")
    target_translate: Optional[Dict[str, float]] = Field(None, description="Optional x/y/z translation applied to the target STL before comparison")
    round_decimals: int = Field(5, description="Decimal places used when matching STL triangles")
    z_thresholds: Optional[List[float]] = Field(None, description="Optional z-height thresholds for per-region retained/added/removed triangle counts")
    target_only_z_ranges: Optional[List[Dict[str, float]]] = Field(None, description="Optional ranges like {'min_z': 8, 'max_z': 22.1} for bounds of target-only geometry")


class ScanPartLibraryArgs(BaseModel):
    workspace_path: Optional[str] = Field(None, description="Path to the part library directory (defaults to active library)")


class SaveWorkspaceModuleArgs(BaseModel):
    workspace_path: str = Field(..., description="Path to the workspace directory")
    module_filename: str = Field(..., description="Module filename (must end with .py)")
    module_content: str = Field(..., description="Python module content (can be empty string)")


class InstallWorkspacePackageArgs(BaseModel):
    workspace_path: str = Field(..., description="Path to the workspace directory")
    package_name: str = Field(..., description="Name of the package to install")


class SearchPartsArgs(BaseModel):
    query: Optional[str] = Field("", description="Search query string (empty returns all parts)")


class GetShapePropertiesArgs(BaseModel):
    result_id: str = Field(..., description="Result ID from script execution")
    shape_index: int = Field(0, description="Index of the shape in the result list")


class GetShapeDescriptionArgs(BaseModel):
    result_id: str = Field(..., description="Result ID from script execution")
    shape_index: int = Field(0, description="Index of the shape in the result list")

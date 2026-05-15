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
        description="CadQuery Python script generated from a text or image+text design request; must create one printable model with real CadQuery boolean unions/cuts instead of STL mesh concatenation; either call show_object(model) or assign the final object to result",
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


class InspectStlSectionsArgs(BaseModel):
    file_path: str = Field(..., description="Path to an STL file to slice through MCP instead of ad hoc local Python")
    axis: str = Field("z", description="Section axis: x, y, or z")
    positions: Optional[List[float]] = Field(None, description="Exact section plane positions along axis; use this for known heights")
    interval: Optional[float] = Field(None, description="Optional spacing between section planes when positions are omitted")
    position_count: int = Field(5, description="Number of evenly spaced internal section planes when positions and interval are omitted")
    round_decimals: int = Field(5, description="Decimal places used when connecting section segments into loops")
    include_points: bool = Field(False, description="Whether to include loop point coordinates in the response")
    max_sections: int = Field(50, description="Safety cap for generated section count")


class InspectStlPlaneSectionsArgs(BaseModel):
    file_path: str = Field(..., description="Path to an STL file to slice with arbitrary or tilted planes through MCP")
    origin: Dict[str, float] = Field(..., description="Plane origin as {'x': ..., 'y': ..., 'z': ...}")
    normal: Dict[str, float] = Field(..., description="Plane normal direction as {'x': ..., 'y': ..., 'z': ...}")
    x_direction: Optional[Dict[str, float]] = Field(None, description="Optional in-plane u/x direction for stable mount-face coordinates")
    offsets: Optional[List[float]] = Field(None, description="Offsets along the plane normal from origin; defaults to [0]")
    round_decimals: int = Field(5, description="Decimal places used when connecting section segments into loops")
    include_points: bool = Field(False, description="Whether to include loop point coordinates in the response")
    max_sections: int = Field(25, description="Safety cap for requested plane sections")


class DetectMountFeaturesArgs(BaseModel):
    file_path: str = Field(..., description="Path to an STL file whose mounting holes or slots should be inferred through MCP")
    axis: str = Field("z", description="Axis to scan with section planes, usually z for height-based mount analysis")
    positions: Optional[List[float]] = Field(None, description="Exact section positions to scan")
    interval: Optional[float] = Field(None, description="Optional spacing between scanned sections")
    position_count: int = Field(9, description="Number of evenly spaced internal sections when positions and interval are omitted")
    min_loop_area: float = Field(1.0, description="Minimum closed-loop area to consider as a mount hole/slot candidate")
    max_loop_area: Optional[float] = Field(None, description="Optional maximum closed-loop area to consider")
    min_circularity: float = Field(0.2, description="Minimum loop circularity; lower values keep slot-like holes")
    center_tolerance: float = Field(1.5, description="Distance tolerance for clustering the same mount feature across sections")
    round_decimals: int = Field(5, description="Decimal places used when connecting section segments into loops")


class ValidateStlSolidArgs(BaseModel):
    file_path: str = Field(..., description="Path to an STL file to validate as a printable solid through MCP")
    allow_multiple_components: bool = Field(False, description="Allow disconnected shells when the design intentionally has multiple printable components")
    expected_component_count: Optional[int] = Field(None, description="Optional exact/maximum expected disconnected component count")


class ProbeStlTunnelArgs(BaseModel):
    file_path: str = Field(..., description="Path to an STL file whose cable tunnel or passage should be probed through MCP")
    start: Dict[str, float] = Field(..., description="Tunnel centerline start point as {'x': ..., 'y': ..., 'z': ...}")
    end: Dict[str, float] = Field(..., description="Tunnel centerline end point as {'x': ..., 'y': ..., 'z': ...}")
    width: float = Field(..., description="Required clear tunnel width in model units")
    height: float = Field(..., description="Required clear tunnel height in model units")
    up_direction: Optional[Dict[str, float]] = Field(None, description="Optional up direction for the rectangular probe cross-section")
    length_samples: int = Field(15, description="Number of stations to sample along the tunnel centerline")
    width_samples: int = Field(3, description="Number of samples across the required tunnel width")
    height_samples: int = Field(3, description="Number of samples across the required tunnel height")
    max_blocked_samples: int = Field(25, description="Maximum blocked sample points to return in the response")


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

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


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


class StlHoleCenterMove(BaseModel):
    current_center: Dict[str, float] = Field(
        ...,
        description="Current measured center of the existing STL hole as {'x': ..., 'y': ..., 'z': ...}",
    )
    new_center: Optional[Dict[str, float]] = Field(
        None,
        description="Target center coordinate for the same STL hole; provide this or offset",
    )
    offset: Optional[Dict[str, float]] = Field(
        None,
        description="Optional x/y/z movement vector for the hole center; provide this or new_center",
    )
    radius: float = Field(
        ...,
        description="Measured hole radius used to select cylindrical hole-wall and rim vertices",
    )
    axis: str = Field("z", description="Hole axis: x, y, or z; z means the hole is vertical through XY")
    radial_tolerance: float = Field(
        0.25,
        description="Selection tolerance around radius in model units; increase for chamfered or faceted STL holes",
    )
    axial_min: Optional[float] = Field(
        None,
        description="Optional minimum coordinate along the hole axis to limit vertex selection",
    )
    axial_max: Optional[float] = Field(
        None,
        description="Optional maximum coordinate along the hole axis to limit vertex selection",
    )


class MoveStlHoleCentersArgs(BaseModel):
    file_path: str = Field(
        ...,
        description="Path to the existing STL whose hole center coordinates need direct mesh editing",
    )
    output_path: str = Field(
        ...,
        description="Path where the edited STL with moved hole center coordinates will be written",
    )
    holes: List[StlHoleCenterMove] = Field(
        ...,
        description="One or more existing STL hole moves; each needs the current measured center, target new_center or offset, hole radius, and optional axis/range limits",
    )
    allow_empty_selection: bool = Field(
        False,
        description="Allow writing an STL when a requested hole selects no vertices; keep false for coordinate-edit safety",
    )


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


class RenderStlPreviewArgs(BaseModel):
    file_path: str = Field(..., description="Path to an STL file to render into a visual preview image through MCP")
    output_path: str = Field(..., description="Target .svg path for the rendered STL visual preview")
    views: Optional[List[str]] = Field(None, description="Preview views to include: top, front, right, iso. Defaults to all four.")
    width: int = Field(1200, description="SVG preview width in pixels")
    height: int = Field(900, description="SVG preview height in pixels")
    margin: int = Field(24, description="Panel margin in pixels")
    show_edges: bool = Field(True, description="Draw triangle edges over shaded faces")


class ValidateStlSolidArgs(BaseModel):
    file_path: str = Field(..., description="Path to an STL file to validate as a printable solid through MCP")
    allow_multiple_components: bool = Field(False, description="Allow disconnected shells when the design intentionally has multiple printable components")
    expected_component_count: Optional[int] = Field(None, description="Optional exact/maximum expected disconnected component count")


class SolidifyStlMeshArgs(BaseModel):
    file_path: str = Field(..., description="Path to a watertight STL mesh to convert through MCP; do not use CadQuery importers.importShape for STL")
    output_path: str = Field(..., description="Target BREP or STEP/STP output path for the tessellated solid reference")
    output_format: Optional[str] = Field(None, description="Optional output format override: brep, step, or stp")
    max_triangles: int = Field(20000, description="Safety cap for STL triangle count before tessellated BREP conversion")
    allow_multiple_components: bool = Field(False, description="Allow a compound output when the STL contains disconnected watertight components")
    require_watertight: bool = Field(True, description="Require watertight/manifold STL topology before creating a solid")


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

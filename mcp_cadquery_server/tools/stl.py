from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import Context, FastMCP

from mcp_cadquery_server.schemas.stl import (
    AnalyzeCadFileArgs,
    CompareStlMeshesArgs,
    DetectMountFeaturesArgs,
    InspectStlPlaneSectionsArgs,
    InspectStlSectionsArgs,
    ProbeStlTunnelArgs,
    RenderStlPreviewArgs,
    SolidifyStlMeshArgs,
    TransformStlMeshArgs,
    ValidateStlSolidArgs,
)
from mcp_cadquery_server.services import stl as stl_service


NumberMap = dict[str, float]


def register_stl_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def analyze_cad_file(ctx: Context, file_path: str, file_format: Optional[str] = None) -> dict:
        """Inspect STL/CAD files for dimensions, watertightness, and mesh topology."""
        return stl_service.handle_analyze_cad_file(
            AnalyzeCadFileArgs(file_path=file_path, file_format=file_format),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def transform_stl_mesh(
        ctx: Context,
        file_path: str,
        output_path: str,
        scale: Optional[NumberMap] = None,
        target_size: Optional[NumberMap] = None,
        translate: Optional[NumberMap] = None,
        rotate_degrees: Optional[NumberMap] = None,
        center_at_origin: bool = False,
    ) -> dict:
        """Resize or reposition an STL and write the transformed mesh."""
        return stl_service.handle_transform_stl_mesh(
            TransformStlMeshArgs(
                file_path=file_path,
                output_path=output_path,
                scale=scale,
                target_size=target_size,
                translate=translate,
                rotate_degrees=rotate_degrees,
                center_at_origin=center_at_origin,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def compare_stl_meshes(
        ctx: Context,
        source_file_path: str,
        target_file_path: str,
        source_translate: Optional[NumberMap] = None,
        target_translate: Optional[NumberMap] = None,
        round_decimals: int = 5,
        z_thresholds: Optional[list[float]] = None,
        target_only_z_ranges: Optional[list[NumberMap]] = None,
    ) -> dict:
        """Compare two STL files to verify redesigns and retained or changed mesh regions."""
        return stl_service.handle_compare_stl_meshes(
            CompareStlMeshesArgs(
                source_file_path=source_file_path,
                target_file_path=target_file_path,
                source_translate=source_translate,
                target_translate=target_translate,
                round_decimals=round_decimals,
                z_thresholds=z_thresholds,
                target_only_z_ranges=target_only_z_ranges,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def inspect_stl_sections(
        ctx: Context,
        file_path: str,
        axis: str = "z",
        positions: Optional[list[float]] = None,
        interval: Optional[float] = None,
        position_count: int = 5,
        round_decimals: int = 5,
        include_points: bool = False,
        max_sections: int = 50,
    ) -> dict:
        """Slice an STL along an axis to inspect section loops and bounds."""
        return stl_service.handle_inspect_stl_sections(
            InspectStlSectionsArgs(
                file_path=file_path,
                axis=axis,
                positions=positions,
                interval=interval,
                position_count=position_count,
                round_decimals=round_decimals,
                include_points=include_points,
                max_sections=max_sections,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def inspect_stl_plane_sections(
        ctx: Context,
        file_path: str,
        origin: NumberMap,
        normal: NumberMap,
        x_direction: Optional[NumberMap] = None,
        offsets: Optional[list[float]] = None,
        round_decimals: int = 5,
        include_points: bool = False,
        max_sections: int = 25,
    ) -> dict:
        """Slice an STL with arbitrary or tilted planes to inspect loops and clearances."""
        return stl_service.handle_inspect_stl_plane_sections(
            InspectStlPlaneSectionsArgs(
                file_path=file_path,
                origin=origin,
                normal=normal,
                x_direction=x_direction,
                offsets=offsets,
                round_decimals=round_decimals,
                include_points=include_points,
                max_sections=max_sections,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def detect_mount_features(
        ctx: Context,
        file_path: str,
        axis: str = "z",
        positions: Optional[list[float]] = None,
        interval: Optional[float] = None,
        position_count: int = 9,
        min_loop_area: float = 1.0,
        max_loop_area: Optional[float] = None,
        min_circularity: float = 0.2,
        center_tolerance: float = 1.5,
        round_decimals: int = 5,
    ) -> dict:
        """Detect mounting hole and slot candidates from STL section loops."""
        return stl_service.handle_detect_mount_features(
            DetectMountFeaturesArgs(
                file_path=file_path,
                axis=axis,
                positions=positions,
                interval=interval,
                position_count=position_count,
                min_loop_area=min_loop_area,
                max_loop_area=max_loop_area,
                min_circularity=min_circularity,
                center_tolerance=center_tolerance,
                round_decimals=round_decimals,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def render_stl_preview(
        ctx: Context,
        file_path: str,
        output_path: str,
        views: Optional[list[str]] = None,
        width: int = 1200,
        height: int = 900,
        margin: int = 24,
        show_edges: bool = True,
    ) -> dict:
        """Render an STL visual preview as SVG."""
        return stl_service.handle_render_stl_preview(
            RenderStlPreviewArgs(
                file_path=file_path,
                output_path=output_path,
                views=views,
                width=width,
                height=height,
                margin=margin,
                show_edges=show_edges,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def validate_stl_solid(
        ctx: Context,
        file_path: str,
        allow_multiple_components: bool = False,
        expected_component_count: Optional[int] = None,
    ) -> dict:
        """Validate STL printability, including watertightness and manifold edges."""
        return stl_service.handle_validate_stl_solid(
            ValidateStlSolidArgs(
                file_path=file_path,
                allow_multiple_components=allow_multiple_components,
                expected_component_count=expected_component_count,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def solidify_stl_mesh(
        ctx: Context,
        file_path: str,
        output_path: str,
        output_format: Optional[str] = None,
        max_triangles: int = 20000,
        allow_multiple_components: bool = False,
        require_watertight: bool = True,
    ) -> dict:
        """Convert a watertight STL mesh to tessellated BREP or STEP."""
        return stl_service.handle_solidify_stl_mesh(
            SolidifyStlMeshArgs(
                file_path=file_path,
                output_path=output_path,
                output_format=output_format,
                max_triangles=max_triangles,
                allow_multiple_components=allow_multiple_components,
                require_watertight=require_watertight,
            ),
            request_id=ctx.request_id,
        )

    @mcp.tool()
    def probe_stl_tunnel(
        ctx: Context,
        file_path: str,
        start: NumberMap,
        end: NumberMap,
        width: float,
        height: float,
        up_direction: Optional[NumberMap] = None,
        length_samples: int = 15,
        width_samples: int = 3,
        height_samples: int = 3,
        max_blocked_samples: int = 25,
    ) -> dict:
        """Probe an STL tunnel or cable channel to verify a rectangular passage is clear."""
        return stl_service.handle_probe_stl_tunnel(
            ProbeStlTunnelArgs(
                file_path=file_path,
                start=start,
                end=end,
                width=width,
                height=height,
                up_direction=up_direction,
                length_samples=length_samples,
                width_samples=width_samples,
                height_samples=height_samples,
                max_blocked_samples=max_blocked_samples,
            ),
            request_id=ctx.request_id,
        )

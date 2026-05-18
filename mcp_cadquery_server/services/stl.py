from __future__ import annotations

from ..domain.rendering import render_stl_preview
from ..domain.stl_analysis import (
    analyze_cad_file,
    compare_stl_meshes,
    probe_stl_tunnel,
    solidify_stl_mesh,
    transform_stl_mesh,
    validate_stl_solid,
)
from ..domain.stl_sections import detect_mount_features, inspect_stl_plane_sections, inspect_stl_sections
from ..schemas.stl import (
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
from ..state import log


def handle_analyze_cad_file(args: AnalyzeCadFileArgs, request_id: str) -> dict:
    """Inspect STL/CAD files for dimensions, watertightness, topology, and shell counts."""
    log.info(f"Handling analyze_cad_file request (ID: {request_id})")
    try:
        analysis = analyze_cad_file(args.file_path, args.file_format)
        return {
            "success": True,
            "message": f"CAD file analyzed successfully: {analysis['file']['path']}",
            "analysis": analysis,
        }
    except Exception as e:
        error_msg = f"Error during CAD file analysis: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_transform_stl_mesh(args: TransformStlMeshArgs, request_id: str) -> dict:
    """Resize or reposition an STL through domain mesh logic."""
    log.info(f"Handling transform_stl_mesh request (ID: {request_id})")
    try:
        transform_result = transform_stl_mesh(
            file_path=args.file_path,
            output_path=args.output_path,
            scale=args.scale,
            target_size=args.target_size,
            translate=args.translate,
            rotate_degrees=args.rotate_degrees,
            center_at_origin=args.center_at_origin,
        )
        return {
            "success": True,
            "message": f"STL mesh transformed successfully: {transform_result['output_file']}",
            "result": transform_result,
        }
    except Exception as e:
        error_msg = f"Error during STL mesh transform: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_compare_stl_meshes(args: CompareStlMeshesArgs, request_id: str) -> dict:
    """Compare two STL files to verify retained, added, and removed geometry."""
    log.info(f"Handling compare_stl_meshes request (ID: {request_id})")
    try:
        comparison = compare_stl_meshes(
            source_file_path=args.source_file_path,
            target_file_path=args.target_file_path,
            source_translate=args.source_translate,
            target_translate=args.target_translate,
            round_decimals=args.round_decimals,
            z_thresholds=args.z_thresholds,
            target_only_z_ranges=args.target_only_z_ranges,
        )
        return {"success": True, "message": "STL meshes compared successfully.", "comparison": comparison}
    except Exception as e:
        error_msg = f"Error during STL mesh comparison: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_inspect_stl_sections(args: InspectStlSectionsArgs, request_id: str) -> dict:
    """Slice an STL along an axis to inspect section loops and bounds."""
    log.info(f"Handling inspect_stl_sections request (ID: {request_id})")
    try:
        section_result = inspect_stl_sections(
            file_path=args.file_path,
            axis=args.axis,
            positions=args.positions,
            interval=args.interval,
            position_count=args.position_count,
            round_decimals=args.round_decimals,
            include_points=args.include_points,
            max_sections=args.max_sections,
        )
        return {"success": True, "message": "STL sections inspected successfully.", "sections": section_result}
    except Exception as e:
        error_msg = f"Error during STL section inspection: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_inspect_stl_plane_sections(args: InspectStlPlaneSectionsArgs, request_id: str) -> dict:
    """Slice an STL with arbitrary or tilted planes."""
    log.info(f"Handling inspect_stl_plane_sections request (ID: {request_id})")
    try:
        section_result = inspect_stl_plane_sections(
            file_path=args.file_path,
            origin=args.origin,
            normal=args.normal,
            x_direction=args.x_direction,
            offsets=args.offsets,
            round_decimals=args.round_decimals,
            include_points=args.include_points,
            max_sections=args.max_sections,
        )
        return {
            "success": True,
            "message": "STL tilted plane sections inspected successfully.",
            "sections": section_result,
        }
    except Exception as e:
        error_msg = f"Error during STL tilted plane section inspection: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_detect_mount_features(args: DetectMountFeaturesArgs, request_id: str) -> dict:
    """Detect mounting hole and slot candidates from STL section loops."""
    log.info(f"Handling detect_mount_features request (ID: {request_id})")
    try:
        features = detect_mount_features(
            file_path=args.file_path,
            axis=args.axis,
            positions=args.positions,
            interval=args.interval,
            position_count=args.position_count,
            min_loop_area=args.min_loop_area,
            max_loop_area=args.max_loop_area,
            min_circularity=args.min_circularity,
            center_tolerance=args.center_tolerance,
            round_decimals=args.round_decimals,
        )
        return {"success": True, "message": "STL mount features detected successfully.", "features": features}
    except Exception as e:
        error_msg = f"Error during STL mount feature detection: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_render_stl_preview(args: RenderStlPreviewArgs, request_id: str) -> dict:
    """Render an STL visual preview as SVG."""
    log.info(f"Handling render_stl_preview request (ID: {request_id})")
    try:
        preview = render_stl_preview(
            file_path=args.file_path,
            output_path=args.output_path,
            views=args.views,
            width=args.width,
            height=args.height,
            margin=args.margin,
            show_edges=args.show_edges,
        )
        return {"success": True, "message": f"STL preview rendered successfully: {preview['output_file']}", "preview": preview}
    except Exception as e:
        error_msg = f"Error during STL preview rendering: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_validate_stl_solid(args: ValidateStlSolidArgs, request_id: str) -> dict:
    """Validate STL printability."""
    log.info(f"Handling validate_stl_solid request (ID: {request_id})")
    try:
        validation = validate_stl_solid(
            file_path=args.file_path,
            allow_multiple_components=args.allow_multiple_components,
            expected_component_count=args.expected_component_count,
        )
        return {"success": True, "message": "STL solid validation completed.", "validation": validation}
    except Exception as e:
        error_msg = f"Error during STL solid validation: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_solidify_stl_mesh(args: SolidifyStlMeshArgs, request_id: str) -> dict:
    """Convert a watertight STL mesh to tessellated BREP or STEP."""
    log.info(f"Handling solidify_stl_mesh request (ID: {request_id})")
    try:
        result = solidify_stl_mesh(
            file_path=args.file_path,
            output_path=args.output_path,
            output_format=args.output_format,
            max_triangles=args.max_triangles,
            allow_multiple_components=args.allow_multiple_components,
            require_watertight=args.require_watertight,
        )
        return {
            "success": True,
            "message": f"STL mesh converted to tessellated solid reference: {result['output_file']}",
            "result": result,
        }
    except Exception as e:
        error_msg = f"Error during STL mesh solidification: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def handle_probe_stl_tunnel(args: ProbeStlTunnelArgs, request_id: str) -> dict:
    """Probe an STL tunnel or cable channel."""
    log.info(f"Handling probe_stl_tunnel request (ID: {request_id})")
    try:
        tunnel = probe_stl_tunnel(
            file_path=args.file_path,
            start=args.start,
            end=args.end,
            width=args.width,
            height=args.height,
            up_direction=args.up_direction,
            length_samples=args.length_samples,
            width_samples=args.width_samples,
            height_samples=args.height_samples,
            max_blocked_samples=args.max_blocked_samples,
        )
        return {"success": True, "message": "STL tunnel probe completed.", "tunnel": tunnel}
    except Exception as e:
        error_msg = f"Error during STL tunnel probe: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg)

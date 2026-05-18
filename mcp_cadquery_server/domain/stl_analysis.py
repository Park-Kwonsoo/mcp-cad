from __future__ import annotations

import math
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import cadquery as cq

from .geometry import get_shape_description, get_shape_properties
from .mesh_primitives import (
    Triangle,
    Vertex,
    add,
    analyze_stl_triangles,
    bounds_for_vertices,
    coerce_vector,
    cross,
    dot,
    finite_number,
    length,
    normalize_file_format,
    normalize_vector,
    read_stl_triangles,
    resolve_existing_file,
    scale,
    stl_triangle_components,
    subtract,
    triangle_area,
    vector_to_dict,
)


def _import_cad_file(file_path: str, file_format: str) -> Any:
    if file_format == "step":
        return cq.importers.importStep(file_path)
    if file_format == "brep":
        return cq.importers.importBrep(file_path)
    if file_format == "bin":
        return cq.importers.importBin(file_path)
    if file_format == "dxf":
        return cq.importers.importDXF(file_path)
    raise ValueError(f"Unsupported CAD file format: {file_format}")

def analyze_cad_file(file_path: str, file_format: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyzes an arbitrary CAD file. STL files are parsed as meshes directly;
    STEP/BREP/BIN/DXF files are imported through CadQuery where supported.
    """
    resolved_path = resolve_existing_file(file_path)
    normalized_format = normalize_file_format(resolved_path, file_format)

    if normalized_format == "stl":
        triangles, stl_encoding = read_stl_triangles(resolved_path)
        return analyze_stl_triangles(triangles, stl_encoding, resolved_path)

    shape = _import_cad_file(resolved_path, normalized_format)
    description = None
    warnings = []
    try:
        description = get_shape_description(shape)
    except Exception as exc:
        warnings.append(f"Shape description failed: {exc}")

    return {
        "analysis_type": "cadquery_shape",
        "file": {
            "path": resolved_path,
            "format": normalized_format,
            "size_bytes": os.path.getsize(resolved_path),
        },
        "properties": get_shape_properties(shape),
        "description": description,
        "warnings": warnings,
    }

def _translated_triangle(triangle: Triangle, translate: Dict[str, float]) -> Triangle:
    return tuple(_translate_vertex(vertex, translate) for vertex in triangle)

def _triangle_compare_key(triangle: Triangle, round_decimals: int) -> Tuple[Vertex, Vertex, Vertex]:
    return tuple(sorted(
        (
            round(vertex[0], round_decimals),
            round(vertex[1], round_decimals),
            round(vertex[2], round_decimals),
        )
        for vertex in triangle
    ))

def _stl_compare_items(
    triangles: List[Triangle],
    translate: Dict[str, float],
    round_decimals: int,
) -> List[Dict[str, Any]]:
    return [
        {
            "key": _triangle_compare_key(translated_triangle, round_decimals),
            "triangle": translated_triangle,
        }
        for translated_triangle in (
            _translated_triangle(triangle, translate)
            for triangle in triangles
        )
    ]

def _counter_for_items(items: List[Dict[str, Any]]) -> Counter:
    return Counter(item["key"] for item in items)

def _triangle_counter_difference_vertices(
    items: List[Dict[str, Any]],
    difference_counter: Counter,
) -> List[Vertex]:
    remaining = difference_counter.copy()
    vertices: List[Vertex] = []
    for item in items:
        key = item["key"]
        if remaining[key] <= 0:
            continue
        vertices.extend(item["triangle"])
        remaining[key] -= 1
    return vertices

def _threshold_compare_summary(
    source_items: List[Dict[str, Any]],
    target_items: List[Dict[str, Any]],
    threshold: float,
) -> Dict[str, Any]:
    source_counter = _counter_for_items([
        item for item in source_items
        if max(vertex[2] for vertex in item["triangle"]) > threshold
    ])
    target_counter = _counter_for_items([
        item for item in target_items
        if max(vertex[2] for vertex in item["triangle"]) > threshold
    ])
    source_only = source_counter - target_counter
    target_only = target_counter - source_counter
    shared_count = sum((source_counter & target_counter).values())
    return {
        "max_z_greater_than": threshold,
        "source_triangles": sum(source_counter.values()),
        "target_triangles": sum(target_counter.values()),
        "shared_triangles": shared_count,
        "source_only_triangles": sum(source_only.values()),
        "target_only_triangles": sum(target_only.values()),
    }

def compare_stl_meshes(
    source_file_path: str,
    target_file_path: str,
    source_translate: Optional[Dict[str, float]] = None,
    target_translate: Optional[Dict[str, float]] = None,
    round_decimals: int = 5,
    z_thresholds: Optional[List[float]] = None,
    target_only_z_ranges: Optional[List[Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """
    Compares two STL meshes by rounded triangle geometry, with optional translations.
    Useful for validating redesigns, dimension edits, retained source geometry,
    and new/removed triangle regions without writing ad hoc Python scripts.
    """
    if not isinstance(round_decimals, int) or round_decimals < 0 or round_decimals > 12:
        raise ValueError("round_decimals must be an integer from 0 to 12.")

    source_path = resolve_existing_file(source_file_path)
    target_path = resolve_existing_file(target_file_path)
    source_triangles, source_encoding = read_stl_triangles(source_path)
    target_triangles, target_encoding = read_stl_triangles(target_path)

    source_translate_values = _axis_mapping(source_translate, 0.0, "source_translate")
    target_translate_values = _axis_mapping(target_translate, 0.0, "target_translate")
    source_items = _stl_compare_items(source_triangles, source_translate_values, round_decimals)
    target_items = _stl_compare_items(target_triangles, target_translate_values, round_decimals)

    source_counter = _counter_for_items(source_items)
    target_counter = _counter_for_items(target_items)
    shared_counter = source_counter & target_counter
    source_only_counter = source_counter - target_counter
    target_only_counter = target_counter - source_counter

    source_count = len(source_triangles)
    target_count = len(target_triangles)
    shared_count = sum(shared_counter.values())
    source_only_count = sum(source_only_counter.values())
    target_only_count = sum(target_only_counter.values())
    target_only_vertices = _triangle_counter_difference_vertices(target_items, target_only_counter)
    source_only_vertices = _triangle_counter_difference_vertices(source_items, source_only_counter)

    threshold_summaries = [
        _threshold_compare_summary(source_items, target_items, finite_number(threshold, "z_thresholds[]"))
        for threshold in (z_thresholds or [])
    ]

    range_summaries = []
    for index, z_range in enumerate(target_only_z_ranges or []):
        if not isinstance(z_range, dict):
            raise ValueError("target_only_z_ranges entries must be objects with min_z and max_z.")
        min_z = finite_number(z_range.get("min_z"), f"target_only_z_ranges[{index}].min_z")
        max_z = finite_number(z_range.get("max_z"), f"target_only_z_ranges[{index}].max_z")
        if min_z > max_z:
            raise ValueError(f"target_only_z_ranges[{index}].min_z must be <= max_z.")
        vertices_in_range = [
            vertex for vertex in target_only_vertices
            if min_z <= vertex[2] <= max_z
        ]
        range_summaries.append({
            "min_z": min_z,
            "max_z": max_z,
            "vertex_count": len(vertices_in_range),
            "bounds": bounds_for_vertices(vertices_in_range),
        })

    return {
        "source": {
            "file": source_path,
            "stl_encoding": source_encoding,
            "triangle_count": source_count,
        },
        "target": {
            "file": target_path,
            "stl_encoding": target_encoding,
            "triangle_count": target_count,
        },
        "comparison": {
            "round_decimals": round_decimals,
            "source_translate": source_translate_values,
            "target_translate": target_translate_values,
            "shared_triangles": shared_count,
            "source_only_triangles": source_only_count,
            "target_only_triangles": target_only_count,
            "source_retained_ratio": shared_count / source_count if source_count else None,
            "target_reused_ratio": shared_count / target_count if target_count else None,
        },
        "source_only_vertex_bounds": bounds_for_vertices(source_only_vertices),
        "target_only_vertex_bounds": bounds_for_vertices(target_only_vertices),
        "z_thresholds": threshold_summaries,
        "target_only_z_ranges": range_summaries,
    }

def validate_stl_solid(
    file_path: str,
    allow_multiple_components: bool = False,
    expected_component_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Runs printable-solid checks for STL files and summarizes failure reasons.
    """
    analysis = analyze_cad_file(file_path, "stl")
    topology = analysis["topology"]
    measurements = analysis["measurements"]
    component_count = topology["connected_component_count"]
    allowed_components = (
        expected_component_count
        if expected_component_count is not None
        else (component_count if allow_multiple_components else 1)
    )

    checks = {
        "watertight": topology["watertight"],
        "no_boundary_edges": topology["boundary_edge_count"] == 0,
        "no_non_manifold_edges": topology["non_manifold_edge_count"] == 0,
        "component_count_allowed": component_count <= allowed_components,
        "positive_volume_estimate": measurements["volume_estimate"] > 0,
    }

    risks = []
    if not checks["watertight"]:
        risks.append("Mesh is not watertight; slicers may produce broken toolpaths.")
    if not checks["no_non_manifold_edges"]:
        risks.append("Mesh contains non-manifold edges.")
    if not checks["component_count_allowed"]:
        risks.append(
            f"Mesh has {component_count} disconnected components; allowed component count is {allowed_components}."
        )
    if not checks["positive_volume_estimate"]:
        risks.append("Mesh volume estimate is not positive.")
    risks.extend(analysis.get("warnings", []))

    return {
        "success": all(checks.values()),
        "verdict": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "risks": risks,
        "analysis": analysis,
    }

def _triangle_to_cq_face(triangle: Triangle) -> cq.Face:
    if triangle_area(triangle) <= 1e-12:
        raise ValueError(f"Cannot create a face from a degenerate STL triangle: {triangle}")
    points = [cq.Vector(*vertex) for vertex in triangle]
    points.append(points[0])
    wire = cq.Wire.makePolygon(points)
    return cq.Face.makeFromWires(wire)

def _stl_component_to_solid(triangles: List[Triangle], component_indices: List[int]) -> cq.Solid:
    faces = [_triangle_to_cq_face(triangles[index]) for index in component_indices]
    shell = cq.Shell.makeShell(faces)
    if shell.ShapeType() != "Shell":
        raise ValueError("STL component did not produce a single shell; check for disconnected or invalid mesh topology.")
    solid = cq.Solid.makeSolid(shell)
    if not solid.isValid():
        raise ValueError("STL component produced an invalid CadQuery solid.")
    return solid

def solidify_stl_mesh(
    file_path: str,
    output_path: str,
    output_format: Optional[str] = None,
    max_triangles: int = 20000,
    allow_multiple_components: bool = False,
    require_watertight: bool = True,
) -> Dict[str, Any]:
    """
    Converts a watertight STL triangle mesh into a tessellated BREP/STEP shape.

    This is intentionally a mesh-to-BRep bridge for reference or boolean work.
    It does not reconstruct clean parametric CadQuery features.
    """
    if max_triangles <= 0:
        raise ValueError("max_triangles must be greater than zero.")
    if not output_path:
        raise ValueError("output_path is required.")

    resolved_path = resolve_existing_file(file_path)
    triangles, stl_encoding = read_stl_triangles(resolved_path)
    if len(triangles) > max_triangles:
        raise ValueError(
            f"STL has {len(triangles)} triangles, which exceeds max_triangles={max_triangles}. "
            "Increase the limit only for small, intentional conversions."
        )

    analysis = analyze_stl_triangles(triangles, stl_encoding, resolved_path)
    topology = analysis["topology"]
    if require_watertight and not topology["watertight"]:
        raise ValueError(
            "STL mesh is not watertight/manifold, so it cannot be safely converted to a solid. "
            "Use analyze_cad_file, inspect_stl_sections, or probe_stl_tunnel first to locate the mesh issue."
        )

    component_count = topology["connected_component_count"]
    if component_count > 1 and not allow_multiple_components:
        raise ValueError(
            f"STL has {component_count} disconnected components. Pass allow_multiple_components=true "
            "to export a compound, or rebuild a single boolean-unioned CadQuery model instead."
        )

    components = stl_triangle_components(triangles)
    solids = [_stl_component_to_solid(triangles, component) for component in components]
    shape_to_export: Any = solids[0] if len(solids) == 1 else cq.Compound.makeCompound(solids)

    normalized_output_format = output_format or os.path.splitext(output_path)[1].lstrip(".") or "brep"
    normalized_output_format = normalized_output_format.strip().lower()
    export_type_by_format = {
        "brep": "BREP",
        "brp": "BREP",
        "step": "STEP",
        "stp": "STEP",
    }
    if normalized_output_format not in export_type_by_format:
        raise ValueError("solidify_stl_mesh output_format must be BREP or STEP/STP.")

    target_path = os.path.abspath(output_path)
    export_shape_to_file(
        shape_to_export,
        target_path,
        export_type_by_format[normalized_output_format],
        {},
    )

    properties = None
    try:
        properties = get_shape_properties(shape_to_export)
    except Exception as exc:
        log.warning(f"Could not calculate properties for solidified STL shape: {exc}")

    warnings = [
        "CadQuery importers.importShape/importStep do not import STL directly; this MCP tool parsed STL triangles instead.",
        "Output is a tessellated BREP/STEP made from triangle faces, not a clean parametric reconstruction.",
    ]
    if len(solids) > 1:
        warnings.append("Output is a compound with multiple disconnected solids.")

    return {
        "success": True,
        "source_file": {
            "path": resolved_path,
            "format": "stl",
            "stl_encoding": stl_encoding,
        },
        "output_file": target_path,
        "output_format": export_type_by_format[normalized_output_format].lower(),
        "conversion": {
            "type": "tessellated_brep_from_stl_mesh",
            "triangle_count": len(triangles),
            "component_count": len(solids),
            "shape_type": shape_to_export.ShapeType(),
            "allow_multiple_components": allow_multiple_components,
            "require_watertight": require_watertight,
        },
        "analysis": analysis,
        "properties": properties,
        "warnings": warnings,
    }

def _ray_triangle_intersection(origin: Vertex, direction: Vertex, triangle: Triangle, epsilon: float = 1e-9) -> Optional[float]:
    v0, v1, v2 = triangle
    edge1 = subtract(v1, v0)
    edge2 = subtract(v2, v0)
    h = cross(direction, edge2)
    determinant = dot(edge1, h)
    if -epsilon < determinant < epsilon:
        return None
    inverse_determinant = 1.0 / determinant
    s = subtract(origin, v0)
    u = inverse_determinant * dot(s, h)
    if u < -epsilon or u > 1.0 + epsilon:
        return None
    q = cross(s, edge1)
    v = inverse_determinant * dot(direction, q)
    if v < -epsilon or u + v > 1.0 + epsilon:
        return None
    t = inverse_determinant * dot(edge2, q)
    if t <= epsilon:
        return None
    return t

def _point_inside_mesh(point: Vertex, triangles: List[Triangle]) -> bool:
    direction = normalize_vector((1.0, 0.3713906763541037, 0.2179280434782609), "ray direction")
    intersections = []
    for triangle in triangles:
        distance = _ray_triangle_intersection(point, direction, triangle)
        if distance is not None:
            intersections.append(round(distance, 8))
    unique_distances = sorted(set(intersections))
    return len(unique_distances) % 2 == 1

def _sample_offsets(width: float, height: float, width_samples: int, height_samples: int) -> List[Tuple[float, float]]:
    if width_samples <= 0 or height_samples <= 0:
        raise ValueError("width_samples and height_samples must be greater than zero.")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be greater than zero.")
    us = [0.0] if width_samples == 1 else [
        -width / 2.0 + width * index / (width_samples - 1)
        for index in range(width_samples)
    ]
    vs = [0.0] if height_samples == 1 else [
        -height / 2.0 + height * index / (height_samples - 1)
        for index in range(height_samples)
    ]
    return [(u, v) for u in us for v in vs]

def probe_stl_tunnel(
    file_path: str,
    start: Any,
    end: Any,
    width: float,
    height: float,
    up_direction: Optional[Any] = None,
    length_samples: int = 15,
    width_samples: int = 3,
    height_samples: int = 3,
    max_blocked_samples: int = 25,
) -> Dict[str, Any]:
    """
    Samples a rectangular corridor through an STL and reports whether material blocks it.
    """
    if length_samples <= 1:
        raise ValueError("length_samples must be greater than one.")
    if max_blocked_samples < 0:
        raise ValueError("max_blocked_samples must be non-negative.")

    resolved_path = resolve_existing_file(file_path)
    triangles, stl_encoding = read_stl_triangles(resolved_path)
    start_point = coerce_vector(start, "start")
    end_point = coerce_vector(end, "end")
    probe_width = finite_number(width, "width")
    probe_height = finite_number(height, "height")
    path_vector = subtract(end_point, start_point)
    path_length = length(path_vector)
    if path_length <= 1e-12:
        raise ValueError("start and end must be different points.")
    path_axis = normalize_vector(path_vector, "path")
    up_seed = coerce_vector(up_direction, "up_direction") if up_direction is not None else (0.0, 0.0, 1.0)
    if abs(dot(normalize_vector(up_seed, "up_direction"), path_axis)) > 0.98:
        up_seed = (1.0, 0.0, 0.0)
    side_axis = normalize_vector(cross(path_axis, up_seed), "side direction")
    up_axis = normalize_vector(cross(side_axis, path_axis), "up direction")
    sample_offsets = _sample_offsets(
        probe_width,
        probe_height,
        width_samples,
        height_samples,
    )

    station_summaries = []
    blocked_samples = []
    total_samples = 0
    blocked_count = 0
    for station_index in range(length_samples):
        t = station_index / (length_samples - 1)
        center = add(start_point, scale(path_vector, t))
        station_blocked = 0
        for side_offset, up_offset in sample_offsets:
            sample_point = add(center, add(scale(side_axis, side_offset), scale(up_axis, up_offset)))
            total_samples += 1
            inside_material = _point_inside_mesh(sample_point, triangles)
            if inside_material:
                blocked_count += 1
                station_blocked += 1
                if len(blocked_samples) < max_blocked_samples:
                    blocked_samples.append({
                        "station_index": station_index,
                        "t": t,
                        "point": vector_to_dict(sample_point),
                        "side_offset": side_offset,
                        "up_offset": up_offset,
                    })
        station_summaries.append({
            "station_index": station_index,
            "t": t,
            "center": vector_to_dict(center),
            "blocked_samples": station_blocked,
            "sample_count": len(sample_offsets),
            "clear": station_blocked == 0,
        })

    return {
        "file": {"path": resolved_path, "format": "stl", "stl_encoding": stl_encoding},
        "path": {
            "start": vector_to_dict(start_point),
            "end": vector_to_dict(end_point),
            "length": path_length,
            "axis": vector_to_dict(path_axis),
            "side_direction": vector_to_dict(side_axis),
            "up_direction": vector_to_dict(up_axis),
            "width": probe_width,
            "height": probe_height,
        },
        "sample_count": total_samples,
        "blocked_sample_count": blocked_count,
        "clear_sample_count": total_samples - blocked_count,
        "clear": blocked_count == 0,
        "start_clear": station_summaries[0]["clear"],
        "end_clear": station_summaries[-1]["clear"],
        "blocked_samples": blocked_samples,
        "stations": station_summaries,
    }

def _axis_mapping(mapping: Optional[Dict[str, float]], default: float, name: str) -> Dict[str, float]:
    values = {"x": default, "y": default, "z": default}
    if not mapping:
        return values
    for axis, value in mapping.items():
        axis_name = axis.lower()
        if axis_name not in values:
            raise ValueError(f"{name} contains unsupported axis '{axis}'. Use x, y, or z.")
        values[axis_name] = finite_number(value, f"{name}.{axis_name}")
    return values

def _scale_vertex(vertex: Vertex, scale: Dict[str, float]) -> Vertex:
    return (vertex[0] * scale["x"], vertex[1] * scale["y"], vertex[2] * scale["z"])

def _rotate_vertex(vertex: Vertex, rotate_degrees: Dict[str, float]) -> Vertex:
    x, y, z = vertex
    rx, ry, rz = (
        math.radians(rotate_degrees["x"]),
        math.radians(rotate_degrees["y"]),
        math.radians(rotate_degrees["z"]),
    )

    cos_x, sin_x = math.cos(rx), math.sin(rx)
    y, z = y * cos_x - z * sin_x, y * sin_x + z * cos_x

    cos_y, sin_y = math.cos(ry), math.sin(ry)
    x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y

    cos_z, sin_z = math.cos(rz), math.sin(rz)
    x, y = x * cos_z - y * sin_z, x * sin_z + y * cos_z
    return (x, y, z)

def _translate_vertex(vertex: Vertex, translate: Dict[str, float]) -> Vertex:
    return (vertex[0] + translate["x"], vertex[1] + translate["y"], vertex[2] + translate["z"])

def _transform_triangles(
    triangles: List[Triangle],
    scale: Dict[str, float],
    rotate_degrees: Dict[str, float],
    center_at_origin: bool,
    translate: Dict[str, float],
) -> List[Triangle]:
    transformed = [
        tuple(_rotate_vertex(_scale_vertex(vertex, scale), rotate_degrees) for vertex in triangle)
        for triangle in triangles
    ]

    if center_at_origin:
        analysis = analyze_stl_triangles(transformed, "ascii")
        center = analysis["bounding_box"]["center"]
        center_offset = {"x": -center["x"], "y": -center["y"], "z": -center["z"]}
        transformed = [
            tuple(_translate_vertex(vertex, center_offset) for vertex in triangle)
            for triangle in transformed
        ]

    if any(value != 0.0 for value in translate.values()):
        transformed = [
            tuple(_translate_vertex(vertex, translate) for vertex in triangle)
            for triangle in transformed
        ]

    return transformed

def _write_ascii_stl(file_path: str, triangles: List[Triangle], solid_name: str = "transformed_mesh") -> None:
    output_dir = os.path.dirname(file_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as stl_file:
        stl_file.write(f"solid {solid_name}\n")
        for triangle in triangles:
            stl_file.write("  facet normal 0 0 0\n")
            stl_file.write("    outer loop\n")
            for vertex in triangle:
                stl_file.write(f"      vertex {vertex[0]:.9g} {vertex[1]:.9g} {vertex[2]:.9g}\n")
            stl_file.write("    endloop\n")
            stl_file.write("  endfacet\n")
        stl_file.write(f"endsolid {solid_name}\n")

def transform_stl_mesh(
    file_path: str,
    output_path: str,
    scale: Optional[Dict[str, float]] = None,
    target_size: Optional[Dict[str, float]] = None,
    translate: Optional[Dict[str, float]] = None,
    rotate_degrees: Optional[Dict[str, float]] = None,
    center_at_origin: bool = False,
) -> Dict[str, Any]:
    """
    Applies deterministic mesh transforms to an STL and writes a new STL.
    Supports direct scale factors, target bounding-box dimensions, rotation,
    translation, and optional recentering.
    """
    source_path = resolve_existing_file(file_path)
    target_path = os.path.abspath(os.path.expanduser(output_path))
    source_format = normalize_file_format(source_path, "stl")
    if source_format != "stl":
        raise ValueError("transform_stl_mesh only supports STL input.")

    triangles, stl_encoding = read_stl_triangles(source_path)
    before = analyze_stl_triangles(triangles, stl_encoding, source_path)
    scale_values = _axis_mapping(scale, 1.0, "scale")

    if target_size:
        dimensions = before["bounding_box"]
        for axis, target_value in target_size.items():
            axis_name = axis.lower()
            if axis_name not in scale_values:
                raise ValueError(f"target_size contains unsupported axis '{axis}'. Use x, y, or z.")
            target_number = finite_number(target_value, f"target_size.{axis_name}")
            if target_number <= 0:
                raise ValueError(f"target_size.{axis_name} must be greater than zero.")
            current_dimension = dimensions[f"{axis_name}len"]
            if current_dimension == 0:
                raise ValueError(f"Cannot set target_size.{axis_name}: source {axis_name} dimension is zero.")
            scale_values[axis_name] = target_number / current_dimension

    if any(value == 0.0 for value in scale_values.values()):
        raise ValueError("Scale values must be non-zero.")

    rotate_values = _axis_mapping(rotate_degrees, 0.0, "rotate_degrees")
    translate_values = _axis_mapping(translate, 0.0, "translate")
    transformed_triangles = _transform_triangles(
        triangles,
        scale_values,
        rotate_values,
        center_at_origin,
        translate_values,
    )
    _write_ascii_stl(target_path, transformed_triangles)

    after = analyze_stl_triangles(transformed_triangles, "ascii", target_path)
    return {
        "source_file": source_path,
        "output_file": target_path,
        "applied_transform": {
            "scale": scale_values,
            "rotate_degrees": rotate_values,
            "translate": translate_values,
            "center_at_origin": center_at_origin,
        },
        "before": before,
        "after": after,
    }

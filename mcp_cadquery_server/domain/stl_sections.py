from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .stl_io import (
    PLANE_AXES,
    Triangle,
    Vertex,
    _add,
    _analyze_stl_triangles,
    _axis_value,
    _bounds_for_vertices,
    _coerce_vector,
    _cross,
    _dot,
    _finite_number,
    _interpolate_vertex,
    _length,
    _normalize_axis,
    _normalize_vector,
    _plane_basis,
    _point_key,
    _read_stl_triangles,
    _resolve_existing_file,
    _scale,
    _subtract,
    _vector_to_dict,
)


def _section_segments_for_triangles(
    triangles: List[Triangle],
    axis: str,
    position: float,
    round_decimals: int,
    epsilon: float = 1e-7,
) -> List[Tuple[Vertex, Vertex]]:
    segments: List[Tuple[Vertex, Vertex]] = []
    for triangle in triangles:
        candidates: List[Vertex] = []
        edges = ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0]))
        for a, b in edges:
            da = _axis_value(a, axis) - position
            db = _axis_value(b, axis) - position

            if abs(da) <= epsilon and abs(db) <= epsilon:
                candidates.extend([a, b])
            elif abs(da) <= epsilon:
                candidates.append(a)
            elif abs(db) <= epsilon:
                candidates.append(b)
            elif da * db < 0:
                candidates.append(_interpolate_vertex(a, b, da, db))

        unique: Dict[Vertex, Vertex] = {}
        for point in candidates:
            unique[_point_key(point, round_decimals)] = point
        points = list(unique.values())
        if len(points) < 2:
            continue
        if len(points) > 2:
            farthest_pair = (points[0], points[1])
            farthest_distance = -1.0
            for i, point_a in enumerate(points):
                for point_b in points[i + 1:]:
                    distance = (
                        (point_a[0] - point_b[0]) ** 2
                        + (point_a[1] - point_b[1]) ** 2
                        + (point_a[2] - point_b[2]) ** 2
                    )
                    if distance > farthest_distance:
                        farthest_distance = distance
                        farthest_pair = (point_a, point_b)
            segments.append(farthest_pair)
        else:
            segments.append((points[0], points[1]))
    return segments

def _project_point(vertex: Vertex, axis: str) -> Tuple[float, float]:
    first_axis, second_axis = PLANE_AXES[axis]
    return (vertex[AXIS_INDICES[first_axis]], vertex[AXIS_INDICES[second_axis]])

def _polygon_signed_area(points: List[Vertex], axis: str) -> float:
    if len(points) < 3:
        return 0.0
    projected = [_project_point(point, axis) for point in points]
    area = 0.0
    for index, (x1, y1) in enumerate(projected):
        x2, y2 = projected[(index + 1) % len(projected)]
        area += x1 * y2 - x2 * y1
    return area / 2.0

def _polyline_perimeter(points: List[Vertex], closed: bool) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    pairs = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    for a, b in pairs:
        total += math.sqrt(
            (a[0] - b[0]) ** 2
            + (a[1] - b[1]) ** 2
            + (a[2] - b[2]) ** 2
        )
    return total

def _polygon_centroid(points: List[Vertex], axis: str, position: float) -> Dict[str, float]:
    first_axis, second_axis = PLANE_AXES[axis]
    projected = [_project_point(point, axis) for point in points]
    signed_area = _polygon_signed_area(points, axis)
    centroid_values = {"x": 0.0, "y": 0.0, "z": 0.0}
    centroid_values[axis] = position

    if len(projected) < 3 or abs(signed_area) <= 1e-12:
        centroid_values[first_axis] = sum(point[0] for point in projected) / len(projected)
        centroid_values[second_axis] = sum(point[1] for point in projected) / len(projected)
        return centroid_values

    cx = 0.0
    cy = 0.0
    factor_sum = 0.0
    for index, (x1, y1) in enumerate(projected):
        x2, y2 = projected[(index + 1) % len(projected)]
        factor = x1 * y2 - x2 * y1
        factor_sum += factor
        cx += (x1 + x2) * factor
        cy += (y1 + y2) * factor
    if abs(factor_sum) <= 1e-12:
        centroid_values[first_axis] = sum(point[0] for point in projected) / len(projected)
        centroid_values[second_axis] = sum(point[1] for point in projected) / len(projected)
        return centroid_values

    centroid_values[first_axis] = cx / (3.0 * factor_sum)
    centroid_values[second_axis] = cy / (3.0 * factor_sum)
    return centroid_values

def _ordered_cycle(
    component_keys: List[Vertex],
    adjacency: Dict[Vertex, List[Vertex]],
) -> Optional[List[Vertex]]:
    if len(component_keys) < 3 or any(len(adjacency[key]) != 2 for key in component_keys):
        return None

    start = min(component_keys)
    ordered = [start]
    previous = None
    current = start
    while True:
        neighbors = sorted(adjacency[current])
        next_key = neighbors[0] if neighbors[0] != previous else neighbors[1]
        if next_key == start:
            return ordered
        if next_key in ordered:
            return None
        ordered.append(next_key)
        previous = current
        current = next_key

def _section_loops(
    segments: List[Tuple[Vertex, Vertex]],
    axis: str,
    position: float,
    round_decimals: int,
    include_points: bool = False,
) -> List[Dict[str, Any]]:
    point_by_key: Dict[Vertex, Vertex] = {}
    adjacency_sets: Dict[Vertex, set[Vertex]] = defaultdict(set)
    for a, b in segments:
        key_a = _point_key(a, round_decimals)
        key_b = _point_key(b, round_decimals)
        if key_a == key_b:
            continue
        point_by_key[key_a] = a
        point_by_key[key_b] = b
        adjacency_sets[key_a].add(key_b)
        adjacency_sets[key_b].add(key_a)

    adjacency = {key: sorted(neighbors) for key, neighbors in adjacency_sets.items()}
    visited: set[Vertex] = set()
    loops: List[Dict[str, Any]] = []
    for start in sorted(adjacency):
        if start in visited:
            continue
        stack = [start]
        component_keys: List[Vertex] = []
        visited.add(start)
        while stack:
            key = stack.pop()
            component_keys.append(key)
            for neighbor in adjacency[key]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        ordered_keys = _ordered_cycle(component_keys, adjacency)
        closed = ordered_keys is not None
        keys_for_geometry = ordered_keys or sorted(component_keys)
        points = [point_by_key[key] for key in keys_for_geometry]
        signed_area = _polygon_signed_area(points, axis) if closed else None
        area = abs(signed_area) if signed_area is not None else None
        perimeter = _polyline_perimeter(points, closed)
        loop_info: Dict[str, Any] = {
            "closed": closed,
            "point_count": len(points),
            "segment_count": sum(len(adjacency[key]) for key in component_keys) // 2,
            "area": area,
            "signed_area": signed_area,
            "perimeter": perimeter,
            "centroid": _polygon_centroid(points, axis, position),
            "bounds": _bounds_for_vertices(points),
        }
        if area is not None and perimeter > 0:
            loop_info["equivalent_radius"] = math.sqrt(area / math.pi)
            loop_info["circularity"] = min(1.0, 4.0 * math.pi * area / (perimeter ** 2))
        else:
            loop_info["equivalent_radius"] = None
            loop_info["circularity"] = None
        if include_points:
            loop_info["points"] = [
                {"x": point[0], "y": point[1], "z": point[2]}
                for point in points
            ]
        loops.append(loop_info)

    return sorted(loops, key=lambda item: item["area"] or 0.0, reverse=True)

def _section_positions(
    bounds: Dict[str, Any],
    axis: str,
    positions: Optional[List[float]],
    interval: Optional[float],
    position_count: int,
) -> List[float]:
    min_value = bounds[f"{axis}min"]
    max_value = bounds[f"{axis}max"]
    if positions:
        return [_finite_number(position, "positions[]") for position in positions]
    if interval is not None:
        step = _finite_number(interval, "interval")
        if step <= 0:
            raise ValueError("interval must be greater than zero.")
        generated = []
        value = min_value + step
        while value < max_value:
            generated.append(value)
            value += step
        return generated
    if position_count <= 0:
        raise ValueError("position_count must be greater than zero.")
    if position_count == 1:
        return [(min_value + max_value) / 2.0]
    return [
        min_value + (max_value - min_value) * (index + 1) / (position_count + 1)
        for index in range(position_count)
    ]

def inspect_stl_sections(
    file_path: str,
    axis: str = "z",
    positions: Optional[List[float]] = None,
    interval: Optional[float] = None,
    position_count: int = 5,
    round_decimals: int = 5,
    include_points: bool = False,
    max_sections: int = 50,
) -> Dict[str, Any]:
    """
    Slices an STL mesh with x/y/z planes and reports section loops and bounds.
    This covers the "read height-by-height cross sections" workflow through MCP.
    """
    if not isinstance(round_decimals, int) or round_decimals < 0 or round_decimals > 12:
        raise ValueError("round_decimals must be an integer from 0 to 12.")
    if max_sections <= 0:
        raise ValueError("max_sections must be greater than zero.")

    normalized_axis = _normalize_axis(axis)
    resolved_path = _resolve_existing_file(file_path)
    triangles, stl_encoding = _read_stl_triangles(resolved_path)
    analysis = _analyze_stl_triangles(triangles, stl_encoding, resolved_path)
    section_positions = _section_positions(
        analysis["bounding_box"],
        normalized_axis,
        positions,
        interval,
        position_count,
    )
    if len(section_positions) > max_sections:
        raise ValueError(f"Requested {len(section_positions)} sections; max_sections is {max_sections}.")

    sections = []
    for position in section_positions:
        segments = _section_segments_for_triangles(triangles, normalized_axis, position, round_decimals)
        loops = _section_loops(segments, normalized_axis, position, round_decimals, include_points)
        points = [point for segment in segments for point in segment]
        sections.append({
            "axis": normalized_axis,
            "position": position,
            "segment_count": len(segments),
            "point_count": len({_point_key(point, round_decimals) for point in points}),
            "bounds": _bounds_for_vertices(points),
            "closed_loop_count": sum(1 for loop in loops if loop["closed"]),
            "open_loop_count": sum(1 for loop in loops if not loop["closed"]),
            "loops": loops,
        })

    return {
        "file": {
            "path": resolved_path,
            "format": "stl",
            "stl_encoding": stl_encoding,
        },
        "axis": normalized_axis,
        "plane_axes": PLANE_AXES[normalized_axis],
        "bounding_box": analysis["bounding_box"],
        "sections": sections,
    }

def detect_mount_features(
    file_path: str,
    axis: str = "z",
    positions: Optional[List[float]] = None,
    interval: Optional[float] = None,
    position_count: int = 9,
    min_loop_area: float = 1.0,
    max_loop_area: Optional[float] = None,
    min_circularity: float = 0.2,
    center_tolerance: float = 1.5,
    round_decimals: int = 5,
) -> Dict[str, Any]:
    """
    Finds likely mounting holes or slots by scanning closed section loops.
    The largest loop in each section is treated as the outer profile; smaller
    loops are returned as hole/slot candidates and clustered by center.
    """
    normalized_axis = _normalize_axis(axis)
    min_area = _finite_number(min_loop_area, "min_loop_area")
    if min_area < 0:
        raise ValueError("min_loop_area must be non-negative.")
    max_area = _finite_number(max_loop_area, "max_loop_area") if max_loop_area is not None else None
    if max_area is not None and max_area < min_area:
        raise ValueError("max_loop_area must be greater than or equal to min_loop_area.")
    min_circularity_value = _finite_number(min_circularity, "min_circularity")
    if min_circularity_value < 0 or min_circularity_value > 1:
        raise ValueError("min_circularity must be between 0 and 1.")
    tolerance = _finite_number(center_tolerance, "center_tolerance")
    if tolerance <= 0:
        raise ValueError("center_tolerance must be greater than zero.")

    sections_result = inspect_stl_sections(
        file_path=file_path,
        axis=normalized_axis,
        positions=positions,
        interval=interval,
        position_count=position_count,
        round_decimals=round_decimals,
        include_points=False,
    )
    plane_axes = PLANE_AXES[normalized_axis]
    candidates: List[Dict[str, Any]] = []
    for section in sections_result["sections"]:
        closed_loops = [loop for loop in section["loops"] if loop["closed"] and loop["area"] is not None]
        if len(closed_loops) < 2:
            continue
        outer_loop = max(closed_loops, key=lambda loop: loop["area"] or 0.0)
        for loop in closed_loops:
            if loop is outer_loop:
                continue
            area = loop["area"] or 0.0
            circularity = loop["circularity"] or 0.0
            if area < min_area:
                continue
            if max_area is not None and area > max_area:
                continue
            if circularity < min_circularity_value:
                continue
            candidates.append({
                "axis": normalized_axis,
                "position": section["position"],
                "area": area,
                "perimeter": loop["perimeter"],
                "equivalent_radius": loop["equivalent_radius"],
                "circularity": circularity,
                "centroid": loop["centroid"],
                "bounds": loop["bounds"],
            })

    clusters: List[Dict[str, Any]] = []
    for candidate in candidates:
        candidate_center = candidate["centroid"]
        assigned_cluster = None
        for cluster in clusters:
            center = cluster["center"]
            distance = math.sqrt(
                (candidate_center[plane_axes[0]] - center[plane_axes[0]]) ** 2
                + (candidate_center[plane_axes[1]] - center[plane_axes[1]]) ** 2
            )
            if distance <= tolerance:
                assigned_cluster = cluster
                break
        if assigned_cluster is None:
            assigned_cluster = {
                "sample_count": 0,
                "samples": [],
                "center": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
            clusters.append(assigned_cluster)
        assigned_cluster["samples"].append(candidate)
        assigned_cluster["sample_count"] += 1
        for coordinate in ("x", "y", "z"):
            assigned_cluster["center"][coordinate] = (
                sum(sample["centroid"][coordinate] for sample in assigned_cluster["samples"])
                / assigned_cluster["sample_count"]
            )

    features = []
    for cluster_index, cluster in enumerate(clusters):
        samples = cluster["samples"]
        axis_positions = [sample["position"] for sample in samples]
        equivalent_radii = [
            sample["equivalent_radius"] for sample in samples
            if sample["equivalent_radius"] is not None
        ]
        circularities = [sample["circularity"] for sample in samples]
        sample_vertices = []
        for sample in samples:
            bounds = sample["bounds"]
            if bounds:
                sample_vertices.extend([
                    (bounds["xmin"], bounds["ymin"], bounds["zmin"]),
                    (bounds["xmax"], bounds["ymax"], bounds["zmax"]),
                ])
        features.append({
            "feature_id": f"mount_feature_{cluster_index}",
            "kind": "hole_or_slot_candidate",
            "axis": normalized_axis,
            "sample_count": cluster["sample_count"],
            "center": cluster["center"],
            "axis_min": min(axis_positions),
            "axis_max": max(axis_positions),
            "axis_span": max(axis_positions) - min(axis_positions),
            "average_equivalent_radius": (
                sum(equivalent_radii) / len(equivalent_radii)
                if equivalent_radii else None
            ),
            "average_circularity": sum(circularities) / len(circularities),
            "bounds": _bounds_for_vertices(sample_vertices),
            "samples": samples,
        })

    return {
        "file": sections_result["file"],
        "axis": normalized_axis,
        "plane_axes": plane_axes,
        "candidate_count": len(candidates),
        "feature_count": len(features),
        "features": sorted(features, key=lambda feature: feature["sample_count"], reverse=True),
        "sections_scanned": len(sections_result["sections"]),
    }

def _plane_signed_distance(point: Vertex, origin: Vertex, normal: Vertex) -> float:
    return _dot(_subtract(point, origin), normal)

def _plane_section_segments_for_triangles(
    triangles: List[Triangle],
    origin: Vertex,
    normal: Vertex,
    round_decimals: int,
    epsilon: float = 1e-7,
) -> List[Tuple[Vertex, Vertex]]:
    segments: List[Tuple[Vertex, Vertex]] = []
    for triangle in triangles:
        candidates: List[Vertex] = []
        edges = ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0]))
        for a, b in edges:
            da = _plane_signed_distance(a, origin, normal)
            db = _plane_signed_distance(b, origin, normal)
            if abs(da) <= epsilon and abs(db) <= epsilon:
                candidates.extend([a, b])
            elif abs(da) <= epsilon:
                candidates.append(a)
            elif abs(db) <= epsilon:
                candidates.append(b)
            elif da * db < 0:
                candidates.append(_interpolate_vertex(a, b, da, db))

        unique: Dict[Vertex, Vertex] = {}
        for point in candidates:
            unique[_point_key(point, round_decimals)] = point
        points = list(unique.values())
        if len(points) < 2:
            continue
        if len(points) > 2:
            farthest_pair = (points[0], points[1])
            farthest_distance = -1.0
            for i, point_a in enumerate(points):
                for point_b in points[i + 1:]:
                    distance = _length(_subtract(point_a, point_b))
                    if distance > farthest_distance:
                        farthest_distance = distance
                        farthest_pair = (point_a, point_b)
            segments.append(farthest_pair)
        else:
            segments.append((points[0], points[1]))
    return segments

def _plane_coordinates(point: Vertex, origin: Vertex, x_axis: Vertex, y_axis: Vertex) -> Tuple[float, float]:
    relative = _subtract(point, origin)
    return (_dot(relative, x_axis), _dot(relative, y_axis))

def _plane_polygon_signed_area(points: List[Vertex], origin: Vertex, x_axis: Vertex, y_axis: Vertex) -> float:
    if len(points) < 3:
        return 0.0
    projected = [_plane_coordinates(point, origin, x_axis, y_axis) for point in points]
    area = 0.0
    for index, (u1, v1) in enumerate(projected):
        u2, v2 = projected[(index + 1) % len(projected)]
        area += u1 * v2 - u2 * v1
    return area / 2.0

def _plane_bounds(points: List[Vertex], origin: Vertex, x_axis: Vertex, y_axis: Vertex) -> Optional[Dict[str, Any]]:
    if not points:
        return None
    projected = [_plane_coordinates(point, origin, x_axis, y_axis) for point in points]
    us = [point[0] for point in projected]
    vs = [point[1] for point in projected]
    umin, umax = min(us), max(us)
    vmin, vmax = min(vs), max(vs)
    return {
        "umin": umin,
        "umax": umax,
        "vmin": vmin,
        "vmax": vmax,
        "ulen": umax - umin,
        "vlen": vmax - vmin,
        "center": {
            "u": umin + (umax - umin) / 2.0,
            "v": vmin + (vmax - vmin) / 2.0,
        },
    }

def _plane_polygon_centroid(
    points: List[Vertex],
    origin: Vertex,
    x_axis: Vertex,
    y_axis: Vertex,
) -> Dict[str, Any]:
    projected = [_plane_coordinates(point, origin, x_axis, y_axis) for point in points]
    signed_area = _plane_polygon_signed_area(points, origin, x_axis, y_axis)
    if len(projected) < 3 or abs(signed_area) <= 1e-12:
        u = sum(point[0] for point in projected) / len(projected)
        v = sum(point[1] for point in projected) / len(projected)
    else:
        cu = 0.0
        cv = 0.0
        factor_sum = 0.0
        for index, (u1, v1) in enumerate(projected):
            u2, v2 = projected[(index + 1) % len(projected)]
            factor = u1 * v2 - u2 * v1
            factor_sum += factor
            cu += (u1 + u2) * factor
            cv += (v1 + v2) * factor
        if abs(factor_sum) <= 1e-12:
            u = sum(point[0] for point in projected) / len(projected)
            v = sum(point[1] for point in projected) / len(projected)
        else:
            u = cu / (3.0 * factor_sum)
            v = cv / (3.0 * factor_sum)
    global_point = _add(origin, _add(_scale(x_axis, u), _scale(y_axis, v)))
    return {"plane": {"u": u, "v": v}, "global": _vector_to_dict(global_point)}

def _plane_section_loops(
    segments: List[Tuple[Vertex, Vertex]],
    origin: Vertex,
    x_axis: Vertex,
    y_axis: Vertex,
    round_decimals: int,
    include_points: bool = False,
) -> List[Dict[str, Any]]:
    point_by_key: Dict[Vertex, Vertex] = {}
    adjacency_sets: Dict[Vertex, set[Vertex]] = defaultdict(set)
    for a, b in segments:
        key_a = _point_key(a, round_decimals)
        key_b = _point_key(b, round_decimals)
        if key_a == key_b:
            continue
        point_by_key[key_a] = a
        point_by_key[key_b] = b
        adjacency_sets[key_a].add(key_b)
        adjacency_sets[key_b].add(key_a)

    adjacency = {key: sorted(neighbors) for key, neighbors in adjacency_sets.items()}
    visited: set[Vertex] = set()
    loops: List[Dict[str, Any]] = []
    for start in sorted(adjacency):
        if start in visited:
            continue
        stack = [start]
        component_keys: List[Vertex] = []
        visited.add(start)
        while stack:
            key = stack.pop()
            component_keys.append(key)
            for neighbor in adjacency[key]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        ordered_keys = _ordered_cycle(component_keys, adjacency)
        closed = ordered_keys is not None
        keys_for_geometry = ordered_keys or sorted(component_keys)
        points = [point_by_key[key] for key in keys_for_geometry]
        signed_area = _plane_polygon_signed_area(points, origin, x_axis, y_axis) if closed else None
        area = abs(signed_area) if signed_area is not None else None
        perimeter = _polyline_perimeter(points, closed)
        loop_info: Dict[str, Any] = {
            "closed": closed,
            "point_count": len(points),
            "segment_count": sum(len(adjacency[key]) for key in component_keys) // 2,
            "area": area,
            "signed_area": signed_area,
            "perimeter": perimeter,
            "centroid": _plane_polygon_centroid(points, origin, x_axis, y_axis),
            "global_bounds": _bounds_for_vertices(points),
            "plane_bounds": _plane_bounds(points, origin, x_axis, y_axis),
        }
        if area is not None and perimeter > 0:
            loop_info["equivalent_radius"] = math.sqrt(area / math.pi)
            loop_info["circularity"] = min(1.0, 4.0 * math.pi * area / (perimeter ** 2))
        else:
            loop_info["equivalent_radius"] = None
            loop_info["circularity"] = None
        if include_points:
            loop_info["points"] = [
                {
                    "global": _vector_to_dict(point),
                    "plane": {
                        "u": _plane_coordinates(point, origin, x_axis, y_axis)[0],
                        "v": _plane_coordinates(point, origin, x_axis, y_axis)[1],
                    },
                }
                for point in points
            ]
        loops.append(loop_info)
    return sorted(loops, key=lambda item: item["area"] or 0.0, reverse=True)

def inspect_stl_plane_sections(
    file_path: str,
    origin: Any,
    normal: Any,
    x_direction: Optional[Any] = None,
    offsets: Optional[List[float]] = None,
    round_decimals: int = 5,
    include_points: bool = False,
    max_sections: int = 25,
) -> Dict[str, Any]:
    """
    Slices an STL with arbitrary planes, e.g. a tilted front mounting plane.
    """
    if not isinstance(round_decimals, int) or round_decimals < 0 or round_decimals > 12:
        raise ValueError("round_decimals must be an integer from 0 to 12.")
    if max_sections <= 0:
        raise ValueError("max_sections must be greater than zero.")

    resolved_path = _resolve_existing_file(file_path)
    triangles, stl_encoding = _read_stl_triangles(resolved_path)
    base_origin = _coerce_vector(origin, "origin")
    normal_unit, x_axis, y_axis = _plane_basis(
        _coerce_vector(normal, "normal"),
        _coerce_vector(x_direction, "x_direction") if x_direction is not None else None,
    )
    section_offsets = [_finite_number(offset, "offsets[]") for offset in (offsets or [0.0])]
    if len(section_offsets) > max_sections:
        raise ValueError(f"Requested {len(section_offsets)} plane sections; max_sections is {max_sections}.")

    sections = []
    for offset in section_offsets:
        section_origin = _add(base_origin, _scale(normal_unit, offset))
        segments = _plane_section_segments_for_triangles(
            triangles,
            section_origin,
            normal_unit,
            round_decimals,
        )
        loops = _plane_section_loops(segments, section_origin, x_axis, y_axis, round_decimals, include_points)
        points = [point for segment in segments for point in segment]
        sections.append({
            "offset": offset,
            "origin": _vector_to_dict(section_origin),
            "segment_count": len(segments),
            "point_count": len({_point_key(point, round_decimals) for point in points}),
            "global_bounds": _bounds_for_vertices(points),
            "plane_bounds": _plane_bounds(points, section_origin, x_axis, y_axis),
            "closed_loop_count": sum(1 for loop in loops if loop["closed"]),
            "open_loop_count": sum(1 for loop in loops if not loop["closed"]),
            "loops": loops,
        })

    return {
        "file": {"path": resolved_path, "format": "stl", "stl_encoding": stl_encoding},
        "plane": {
            "origin": _vector_to_dict(base_origin),
            "normal": _vector_to_dict(normal_unit),
            "x_direction": _vector_to_dict(x_axis),
            "y_direction": _vector_to_dict(y_axis),
        },
        "sections": sections,
    }

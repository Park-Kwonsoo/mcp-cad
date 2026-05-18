from __future__ import annotations

import math
import os
import struct
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

Vertex = Tuple[float, float, float]

Triangle = Tuple[Vertex, Vertex, Vertex]

def _resolve_existing_file(file_path: str) -> str:
    if not file_path:
        raise ValueError("Missing file path.")
    resolved_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(resolved_path):
        raise ValueError(f"File not found: {resolved_path}")
    return resolved_path

def _normalize_file_format(file_path: str, file_format: Optional[str]) -> str:
    raw_format = file_format or os.path.splitext(file_path)[1].lstrip(".")
    normalized = raw_format.strip().lower()
    aliases = {
        "stp": "step",
        "stl": "stl",
        "step": "step",
        "brep": "brep",
        "brp": "brep",
        "bin": "bin",
        "dxf": "dxf",
    }
    if normalized not in aliases:
        raise ValueError(f"Unsupported CAD file format: {raw_format or 'unknown'}")
    return aliases[normalized]

def _read_binary_stl(data: bytes, triangle_count: int) -> List[Triangle]:
    triangles: List[Triangle] = []
    offset = 84
    for _ in range(triangle_count):
        offset += 12  # normal vector
        coords = struct.unpack("<9f", data[offset:offset + 36])
        offset += 38  # vertices plus attribute byte count
        triangles.append((
            (float(coords[0]), float(coords[1]), float(coords[2])),
            (float(coords[3]), float(coords[4]), float(coords[5])),
            (float(coords[6]), float(coords[7]), float(coords[8])),
        ))
    return triangles

def _read_ascii_stl(text: str) -> List[Triangle]:
    vertices: List[Vertex] = []
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0].lower() == "vertex":
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError as exc:
                raise ValueError(f"Invalid STL vertex line: {line}") from exc

    if len(vertices) % 3 != 0:
        raise ValueError("Invalid ASCII STL: vertex count is not divisible by 3.")

    return [
        (vertices[index], vertices[index + 1], vertices[index + 2])
        for index in range(0, len(vertices), 3)
    ]

def _read_stl_triangles(file_path: str) -> Tuple[List[Triangle], str]:
    with open(file_path, "rb") as stl_file:
        data = stl_file.read()

    if len(data) >= 84:
        triangle_count = struct.unpack("<I", data[80:84])[0]
        expected_size = 84 + triangle_count * 50
        if expected_size == len(data):
            triangles = _read_binary_stl(data, triangle_count)
            if triangles:
                return triangles, "binary"

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Invalid STL: binary header size does not match and file is not UTF-8 ASCII STL.") from exc

    triangles = _read_ascii_stl(text)
    if not triangles:
        raise ValueError("Invalid STL: no triangles found.")
    return triangles, "ascii"

def _triangle_area(triangle: Triangle) -> float:
    a, b, c = triangle
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)

def _triangle_signed_volume(triangle: Triangle) -> float:
    a, b, c = triangle
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    ) / 6.0

def _triangle_component_indices(
    triangle_count: int,
    triangle_edges: List[List[Tuple[Vertex, Vertex]]],
    edge_to_triangles: Dict[Tuple[Vertex, Vertex], List[int]],
) -> List[List[int]]:
    visited = [False] * triangle_count
    components: List[List[int]] = []

    for start_index in range(triangle_count):
        if visited[start_index]:
            continue

        stack = [start_index]
        visited[start_index] = True
        component = []
        while stack:
            triangle_index = stack.pop()
            component.append(triangle_index)
            for edge in triangle_edges[triangle_index]:
                for neighbor_index in edge_to_triangles[edge]:
                    if not visited[neighbor_index]:
                        visited[neighbor_index] = True
                        stack.append(neighbor_index)
        components.append(sorted(component))

    return sorted(components, key=len, reverse=True)

def _triangle_component_summaries(triangles: List[Triangle], components: List[List[int]]) -> List[Dict[str, Any]]:
    summaries = []
    for component_index, triangle_indices in enumerate(components):
        component_triangles = [triangles[index] for index in triangle_indices]
        vertices = [vertex for triangle in component_triangles for vertex in triangle]
        summaries.append({
            "component_index": component_index,
            "triangle_count": len(component_triangles),
            "vertex_count": len(vertices),
            "unique_vertex_count": len({_rounded_vertex(vertex) for vertex in vertices}),
            "bounding_box": _bounds_for_vertices(vertices),
            "surface_area": sum(_triangle_area(triangle) for triangle in component_triangles),
            "volume_estimate": abs(sum(_triangle_signed_volume(triangle) for triangle in component_triangles)),
        })
    return summaries

def _stl_triangle_components(triangles: List[Triangle]) -> List[List[int]]:
    edge_to_triangles: Dict[Tuple[Vertex, Vertex], List[int]] = defaultdict(list)
    triangle_edges: List[List[Tuple[Vertex, Vertex]]] = []
    for triangle_index, triangle in enumerate(triangles):
        rounded = [_rounded_vertex(vertex) for vertex in triangle]
        edges = [
            tuple(sorted((rounded[0], rounded[1]))),
            tuple(sorted((rounded[1], rounded[2]))),
            tuple(sorted((rounded[2], rounded[0]))),
        ]
        triangle_edges.append(edges)
        for edge in edges:
            edge_to_triangles[edge].append(triangle_index)

    return _triangle_component_indices(len(triangles), triangle_edges, edge_to_triangles)

def _rounded_vertex(vertex: Vertex) -> Vertex:
    return (round(vertex[0], 8), round(vertex[1], 8), round(vertex[2], 8))

def _bounds_for_vertices(vertices: List[Vertex]) -> Optional[Dict[str, Any]]:
    if not vertices:
        return None

    xs = [vertex[0] for vertex in vertices]
    ys = [vertex[1] for vertex in vertices]
    zs = [vertex[2] for vertex in vertices]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    return {
        "xmin": xmin,
        "ymin": ymin,
        "zmin": zmin,
        "xmax": xmax,
        "ymax": ymax,
        "zmax": zmax,
        "xlen": xmax - xmin,
        "ylen": ymax - ymin,
        "zlen": zmax - zmin,
        "center": {
            "x": xmin + (xmax - xmin) / 2,
            "y": ymin + (ymax - ymin) / 2,
            "z": zmin + (zmax - zmin) / 2,
        },
    }

def _analyze_stl_triangles(triangles: List[Triangle], stl_encoding: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    if not triangles:
        raise ValueError("Cannot analyze an STL mesh with no triangles.")

    vertices = [vertex for triangle in triangles for vertex in triangle]
    bounds = _bounds_for_vertices(vertices)
    if bounds is None:
        raise ValueError("Cannot analyze an STL mesh with no vertices.")

    edge_counts: Counter[Tuple[Vertex, Vertex]] = Counter()
    edge_to_triangles: Dict[Tuple[Vertex, Vertex], List[int]] = defaultdict(list)
    triangle_edges: List[List[Tuple[Vertex, Vertex]]] = []
    for triangle_index, triangle in enumerate(triangles):
        rounded = [_rounded_vertex(vertex) for vertex in triangle]
        edges = [
            tuple(sorted((rounded[0], rounded[1]))),
            tuple(sorted((rounded[1], rounded[2]))),
            tuple(sorted((rounded[2], rounded[0]))),
        ]
        triangle_edges.append(edges)
        for edge in edges:
            edge_counts[edge] += 1
            edge_to_triangles[edge].append(triangle_index)

    boundary_edges = sum(1 for count in edge_counts.values() if count == 1)
    non_manifold_edges = sum(1 for count in edge_counts.values() if count > 2)
    watertight = boundary_edges == 0 and non_manifold_edges == 0
    components = _triangle_component_indices(len(triangles), triangle_edges, edge_to_triangles)
    component_summaries = _triangle_component_summaries(triangles, components)
    component_sizes = [component["triangle_count"] for component in component_summaries]
    signed_volume = sum(_triangle_signed_volume(triangle) for triangle in triangles)
    absolute_tetra_volume = sum(abs(_triangle_signed_volume(triangle)) for triangle in triangles)

    warnings = []
    if not watertight:
        warnings.append("Volume is only reliable for closed, consistently oriented STL meshes.")
    if len(component_sizes) > 1:
        warnings.append("STL contains multiple disconnected mesh components; this can indicate concatenated solids instead of a boolean union.")

    result: Dict[str, Any] = {
        "analysis_type": "stl_mesh",
        "file": {
            "path": file_path,
            "format": "stl",
            "stl_encoding": stl_encoding,
            "size_bytes": os.path.getsize(file_path) if file_path else None,
        },
        "mesh": {
            "triangle_count": len(triangles),
            "vertex_count": len(vertices),
            "unique_vertex_count": len({_rounded_vertex(vertex) for vertex in vertices}),
        },
        "bounding_box": bounds,
        "measurements": {
            "surface_area": sum(_triangle_area(triangle) for triangle in triangles),
            "signed_volume": signed_volume,
            "volume": abs(signed_volume) if watertight else None,
            "volume_estimate": abs(signed_volume),
            "absolute_tetra_volume_sum": absolute_tetra_volume,
        },
        "topology": {
            "edge_count": len(edge_counts),
            "boundary_edge_count": boundary_edges,
            "non_manifold_edge_count": non_manifold_edges,
            "watertight": watertight,
            "connected_component_count": len(component_sizes),
            "largest_component_triangle_count": component_sizes[0],
            "smallest_component_triangle_count": component_sizes[-1],
            "component_triangle_counts_sample": component_sizes[:20],
        },
        "components": component_summaries[:20],
        "warnings": warnings,
    }
    return result

AXIS_INDICES = {"x": 0, "y": 1, "z": 2}

PLANE_AXES = {
    "x": ("y", "z"),
    "y": ("x", "z"),
    "z": ("x", "y"),
}

def _finite_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number

def _coerce_vector(value: Any, name: str) -> Vertex:
    if isinstance(value, dict):
        return (
            _finite_number(value.get("x"), f"{name}.x"),
            _finite_number(value.get("y"), f"{name}.y"),
            _finite_number(value.get("z"), f"{name}.z"),
        )
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return (
            _finite_number(value[0], f"{name}[0]"),
            _finite_number(value[1], f"{name}[1]"),
            _finite_number(value[2], f"{name}[2]"),
        )
    raise ValueError(f"{name} must be an object with x/y/z or a 3-item list.")

def _vector_to_dict(vector: Vertex) -> Dict[str, float]:
    return {"x": vector[0], "y": vector[1], "z": vector[2]}

def _dot(a: Vertex, b: Vertex) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def _subtract(a: Vertex, b: Vertex) -> Vertex:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def _add(a: Vertex, b: Vertex) -> Vertex:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def _scale(vector: Vertex, factor: float) -> Vertex:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)

def _cross(a: Vertex, b: Vertex) -> Vertex:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )

def _length(vector: Vertex) -> float:
    return math.sqrt(_dot(vector, vector))

def _normalize_vector(vector: Vertex, name: str) -> Vertex:
    length = _length(vector)
    if length <= 1e-12:
        raise ValueError(f"{name} must be a non-zero vector.")
    return _scale(vector, 1.0 / length)

def _plane_basis(normal: Vertex, x_direction: Optional[Vertex] = None) -> Tuple[Vertex, Vertex, Vertex]:
    normal_unit = _normalize_vector(normal, "normal")
    if x_direction is None:
        reference = (1.0, 0.0, 0.0) if abs(normal_unit[0]) < 0.9 else (0.0, 1.0, 0.0)
        x_axis = _normalize_vector(_cross(reference, normal_unit), "derived x_direction")
    else:
        projected = _subtract(x_direction, _scale(normal_unit, _dot(x_direction, normal_unit)))
        x_axis = _normalize_vector(projected, "x_direction")
    y_axis = _normalize_vector(_cross(normal_unit, x_axis), "plane y_direction")
    return normal_unit, x_axis, y_axis

def _normalize_axis(axis: str) -> str:
    normalized = axis.strip().lower()
    if normalized not in AXIS_INDICES:
        raise ValueError(f"Unsupported axis '{axis}'. Use x, y, or z.")
    return normalized

def _axis_value(vertex: Vertex, axis: str) -> float:
    return vertex[AXIS_INDICES[axis]]

def _point_key(vertex: Vertex, round_decimals: int) -> Vertex:
    return (
        round(vertex[0], round_decimals),
        round(vertex[1], round_decimals),
        round(vertex[2], round_decimals),
    )

def _interpolate_vertex(a: Vertex, b: Vertex, da: float, db: float) -> Vertex:
    t = da / (da - db)
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


resolve_existing_file = _resolve_existing_file
normalize_file_format = _normalize_file_format
read_stl_triangles = _read_stl_triangles
triangle_area = _triangle_area
analyze_stl_triangles = _analyze_stl_triangles
stl_triangle_components = _stl_triangle_components
bounds_for_vertices = _bounds_for_vertices
finite_number = _finite_number
coerce_vector = _coerce_vector
vector_to_dict = _vector_to_dict
dot = _dot
subtract = _subtract
add = _add
scale = _scale
cross = _cross
length = _length
normalize_vector = _normalize_vector
plane_basis = _plane_basis
normalize_axis = _normalize_axis
axis_value = _axis_value
point_key = _point_key
interpolate_vertex = _interpolate_vertex

__all__ = [
    "AXIS_INDICES",
    "PLANE_AXES",
    "Triangle",
    "Vertex",
    "add",
    "analyze_stl_triangles",
    "axis_value",
    "bounds_for_vertices",
    "coerce_vector",
    "cross",
    "dot",
    "finite_number",
    "interpolate_vertex",
    "length",
    "normalize_axis",
    "normalize_file_format",
    "normalize_vector",
    "plane_basis",
    "point_key",
    "read_stl_triangles",
    "resolve_existing_file",
    "scale",
    "stl_triangle_components",
    "subtract",
    "triangle_area",
    "vector_to_dict",
]

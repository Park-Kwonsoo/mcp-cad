import os
import math
import struct
import logging
from collections import Counter, defaultdict
from html import escape
from typing import Dict, Any, List, Optional, Tuple

# Import CadQuery-related libraries directly needed by core functions
import cadquery as cq
from cadquery import exporters

log = logging.getLogger(__name__) # Use standard logging

def export_shape_to_file(shape_to_export: Any, output_path: str, export_format: Optional[str] = None, export_options: Optional[dict] = None):
     """Exports a CadQuery shape/workplane to a specified file."""
     shape = shape_to_export.val() if isinstance(shape_to_export, cq.Workplane) else shape_to_export
     if not isinstance(shape, cq.Shape): raise TypeError(f"Object to export is not a cq.Shape or cq.Workplane, but {type(shape)}")
     if export_options is None: export_options = {}
     log.info(f"Exporting shape to file '{output_path}' (Format: {export_format or 'Infer'}, Options: {export_options})")
     try:
         output_dir = os.path.dirname(output_path)
         if output_dir: os.makedirs(output_dir, exist_ok=True)
         exporters.export(shape, output_path, exportType=export_format, opt=export_options)
         log.info(f"Shape successfully exported to file '{output_path}'.")
     except Exception as e:
         error_msg = f"Core shape export to file '{output_path}' failed: {e}"
         log.error(error_msg, exc_info=True)
         raise Exception(error_msg) from e

def export_shape_to_svg_file(shape_to_render: Any, output_path: str, svg_opts: dict) -> None:
    """
    Exports a CadQuery shape or Workplane to an SVG file.

    Args:
        shape_to_render: The CadQuery object (Shape or Workplane) to export.
        output_path: The full path to save the SVG file.
        svg_opts: A dictionary of options for cq.exporters.export (SVG specific).

    Raises:
        TypeError: If the object is not a cq.Shape or cq.Workplane.
        Exception: If the export process fails.
    """
    shape = shape_to_render.val() if isinstance(shape_to_render, cq.Workplane) else shape_to_render
    if not isinstance(shape, cq.Shape): raise TypeError(f"Object to export is not a cq.Shape or cq.Workplane, but {type(shape)}")
    log.info(f"Exporting shape to SVG '{output_path}' with options: {svg_opts}")
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        exporters.export(shape, output_path, exportType='SVG', opt=svg_opts)
        log.info(f"Shape successfully exported to SVG '{output_path}'.")
    except Exception as e: error_msg = f"Core SVG export failed: {e}"; log.error(error_msg, exc_info=True); raise Exception(error_msg) from e

def get_shape_properties(shape_to_analyze: Any) -> Dict[str, Any]:
    """
    Calculates various geometric properties of a CadQuery Shape or Workplane.

    Args:
        shape_to_analyze: The CadQuery object (Shape or Workplane) to analyze.

    Returns:
        A dictionary containing properties like 'bounding_box', 'volume',
        'area', 'center_of_mass'. Returns None for properties that cannot
        be calculated.

    Raises:
        TypeError: If the object is not a cq.Shape or cq.Workplane.
        Exception: For errors during property calculation.
    """
    shape = shape_to_analyze.val() if isinstance(shape_to_analyze, cq.Workplane) else shape_to_analyze
    if not isinstance(shape, cq.Shape):
        raise TypeError(f"Object to analyze is not a cq.Shape or cq.Workplane, but {type(shape)}")

    log.info(f"Calculating properties for shape of type {type(shape)}")
    properties = {}
    try:
        # Bounding Box
        try:
            bb = shape.BoundingBox()
            properties['bounding_box'] = {
                'xmin': bb.xmin, 'ymin': bb.ymin, 'zmin': bb.zmin,
                'xmax': bb.xmax, 'ymax': bb.ymax, 'zmax': bb.zmax,
                'xlen': bb.xlen, 'ylen': bb.ylen, 'zlen': bb.zlen,
                'center': {'x': bb.center.x, 'y': bb.center.y, 'z': bb.center.z}
            }
            log.debug(f"Calculated bounding box: {properties['bounding_box']}")
        except Exception as bb_err:
            log.warning(f"Could not calculate bounding box: {bb_err}", exc_info=True)
            properties['bounding_box'] = None

        # Volume
        try:
            properties['volume'] = shape.Volume()
            log.debug(f"Calculated volume: {properties['volume']}")
        except Exception as vol_err:
            # Volume calculation can fail for non-solids (wires, faces, shells)
            log.warning(f"Could not calculate volume (may be expected for non-solids): {vol_err}")
            properties['volume'] = None

        # Area
        try:
            properties['area'] = shape.Area()
            log.debug(f"Calculated area: {properties['area']}")
        except Exception as area_err:
            log.warning(f"Could not calculate area: {area_err}", exc_info=True)
            properties['area'] = None

        # Center of Mass
        try:
            com = shape.Center() # Use Center() which works for more types than CenterOfMass()
            properties['center_of_mass'] = {'x': com.x, 'y': com.y, 'z': com.z}
            log.debug(f"Calculated center of mass: {properties['center_of_mass']}")
        except Exception as com_err:
            log.warning(f"Could not calculate center of mass: {com_err}", exc_info=True)
            properties['center_of_mass'] = None

        # TODO: Add more properties as needed (e.g., inertia, specific checks)

        log.info("Finished calculating shape properties.")
        return properties

    except Exception as e:
        error_msg = f"Core property calculation failed: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg) from e

def get_shape_description(shape_to_describe: Any) -> str:
    """
    Generates a textual description of a CadQuery Shape or Workplane based on
    its geometric properties and type.

    Args:
        shape_to_describe: The CadQuery object (Shape or Workplane) to describe.

    Returns:
        A string describing the shape.

    Raises:
        TypeError: If the object is not a cq.Shape or cq.Workplane.
        Exception: For errors during analysis.
    """
    shape = shape_to_describe.val() if isinstance(shape_to_describe, cq.Workplane) else shape_to_describe
    if not isinstance(shape, cq.Shape):
        raise TypeError(f"Object to describe is not a cq.Shape or cq.Workplane, but {type(shape)}")

    log.info(f"Generating description for shape of type {type(shape)}")
    description_parts = []

    try:
        # 1. Identify Shape Type
        shape_type = shape.ShapeType()
        description_parts.append(f"The object is a {shape_type}.")

        # 2. Get Properties (reuse existing function for consistency)
        properties = get_shape_properties(shape) # Call the existing properties function

        # 3. Add Bounding Box Info
        bb = properties.get('bounding_box')
        if bb:
            description_parts.append(
                f"It occupies a bounding box of size "
                f"{bb['xlen']:.3f} x {bb['ylen']:.3f} x {bb['zlen']:.3f} units."
            )
            description_parts.append(
                f"The geometric center is at ({bb['center']['x']:.3f}, {bb['center']['y']:.3f}, {bb['center']['z']:.3f})."
            )
        else:
            description_parts.append("Bounding box could not be determined.")

        # 4. Add Volume Info (if applicable)
        volume = properties.get('volume')
        if volume is not None: # Check for None, as 0 is a valid volume
             description_parts.append(f"It has a volume of {volume:.3f} cubic units.")
        elif shape_type == "Solid": # Only mention lack of volume if it was expected
             description_parts.append("Volume calculation failed, though it appears to be a solid.")

        # 5. Add Area Info
        area = properties.get('area')
        if area is not None:
            description_parts.append(f"The total surface area is {area:.3f} square units.")
        else:
            description_parts.append("Surface area could not be determined.")

        # 6. Add Center of Mass Info
        com = properties.get('center_of_mass')
        if com:
            # Check if it's significantly different from the geometric center
            if bb and (abs(com['x'] - bb['center']['x']) > 1e-6 or \
                       abs(com['y'] - bb['center']['y']) > 1e-6 or \
                       abs(com['z'] - bb['center']['z']) > 1e-6):
                description_parts.append(
                    f"Its center of mass is located at ({com['x']:.3f}, {com['y']:.3f}, {com['z']:.3f})."
                )
            # Otherwise, it's likely the same as the geometric center already mentioned
        else:
             description_parts.append("Center of mass could not be determined.")

        # 7. Add Counts (Faces, Edges, Vertices)
        try:
            num_faces = len(shape.Faces())
            num_edges = len(shape.Edges())
            num_vertices = len(shape.Vertices())
            description_parts.append(f"It consists of {num_faces} faces, {num_edges} edges, and {num_vertices} vertices.")
        except Exception as count_err:
            log.warning(f"Could not count faces/edges/vertices: {count_err}")
            description_parts.append("Could not determine the count of faces, edges, or vertices.")

        # TODO: Add more sophisticated analysis later if needed (e.g., feature recognition)

        log.info("Finished generating shape description.")
        return " ".join(description_parts)

    except Exception as e:
        error_msg = f"Core description generation failed: {e}"
        log.error(error_msg, exc_info=True)
        raise Exception(error_msg) from e


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
    resolved_path = _resolve_existing_file(file_path)
    normalized_format = _normalize_file_format(resolved_path, file_format)

    if normalized_format == "stl":
        triangles, stl_encoding = _read_stl_triangles(resolved_path)
        return _analyze_stl_triangles(triangles, stl_encoding, resolved_path)

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


def _normalize_preview_views(views: Optional[List[str]]) -> List[str]:
    normalized = [view.strip().lower() for view in (views or ["top", "front", "right", "iso"]) if view.strip()]
    supported = {"top", "front", "right", "iso"}
    unsupported = [view for view in normalized if view not in supported]
    if unsupported:
        raise ValueError(f"Unsupported STL preview view(s): {', '.join(unsupported)}")
    if not normalized:
        raise ValueError("At least one preview view is required.")
    return normalized


def _preview_view_basis(view: str) -> Tuple[Vertex, Vertex, Vertex]:
    if view == "top":
        return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    if view == "front":
        return (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)
    if view == "right":
        return (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)
    if view == "iso":
        inv_sqrt_2 = 1.0 / math.sqrt(2.0)
        inv_sqrt_3 = 1.0 / math.sqrt(3.0)
        inv_sqrt_6 = 1.0 / math.sqrt(6.0)
        return (
            (inv_sqrt_2, -inv_sqrt_2, 0.0),
            (inv_sqrt_6, inv_sqrt_6, 2.0 * inv_sqrt_6),
            (inv_sqrt_3, inv_sqrt_3, -inv_sqrt_3),
        )
    raise ValueError(f"Unsupported STL preview view: {view}")


def _dot_vertex(vertex: Vertex, basis: Vertex) -> float:
    return vertex[0] * basis[0] + vertex[1] * basis[1] + vertex[2] * basis[2]


def _project_preview_vertex(vertex: Vertex, u_basis: Vertex, v_basis: Vertex, depth_basis: Vertex) -> Tuple[float, float, float]:
    return (
        _dot_vertex(vertex, u_basis),
        _dot_vertex(vertex, v_basis),
        _dot_vertex(vertex, depth_basis),
    )


def _triangle_normal(triangle: Triangle) -> Vertex:
    a, b, c = triangle
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    normal = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    length = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return (normal[0] / length, normal[1] / length, normal[2] / length)


def _preview_fill_color(triangle: Triangle, depth_basis: Vertex) -> str:
    normal = _triangle_normal(triangle)
    facing = abs(_dot_vertex(normal, depth_basis))
    shade = int(188 + min(1.0, facing) * 42)
    return f"#{shade:02x}{shade + 5:02x}{min(255, shade + 14):02x}"


def _render_stl_preview_panel(
    triangles: List[Triangle],
    view: str,
    panel_x: float,
    panel_y: float,
    panel_width: float,
    panel_height: float,
    margin: float,
    show_edges: bool,
) -> Tuple[str, Dict[str, Any]]:
    u_basis, v_basis, depth_basis = _preview_view_basis(view)
    projected_triangles = [
        tuple(_project_preview_vertex(vertex, u_basis, v_basis, depth_basis) for vertex in triangle)
        for triangle in triangles
    ]
    projected_vertices = [vertex for triangle in projected_triangles for vertex in triangle]
    us = [vertex[0] for vertex in projected_vertices]
    vs = [vertex[1] for vertex in projected_vertices]
    umin, umax = min(us), max(us)
    vmin, vmax = min(vs), max(vs)
    ulen = max(umax - umin, 1e-9)
    vlen = max(vmax - vmin, 1e-9)
    drawing_width = max(panel_width - margin * 2.0, 1.0)
    drawing_height = max(panel_height - margin * 2.0 - 22.0, 1.0)
    scale = min(drawing_width / ulen, drawing_height / vlen)
    x_offset = panel_x + margin + (drawing_width - ulen * scale) / 2.0
    y_offset = panel_y + margin + 22.0 + (drawing_height - vlen * scale) / 2.0

    def to_svg_point(projected: Tuple[float, float, float]) -> Tuple[float, float]:
        x = x_offset + (projected[0] - umin) * scale
        y = y_offset + (vmax - projected[1]) * scale
        return x, y

    sorted_items = sorted(
        zip(triangles, projected_triangles),
        key=lambda item: sum(vertex[2] for vertex in item[1]) / 3.0,
    )
    stroke_attrs = ' stroke="#344052" stroke-width="0.7" stroke-opacity="0.72"' if show_edges else ""
    elements = [
        f'<g class="stl-preview-panel stl-preview-{escape(view)}">',
        f'<rect x="{panel_x:.2f}" y="{panel_y:.2f}" width="{panel_width:.2f}" height="{panel_height:.2f}" fill="#ffffff" stroke="#ccd4df" stroke-width="1"/>',
        f'<text x="{panel_x + margin:.2f}" y="{panel_y + margin + 4:.2f}" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1f2937">{escape(view.upper())}</text>',
    ]
    for original_triangle, projected_triangle in sorted_items:
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in (to_svg_point(vertex) for vertex in projected_triangle))
        elements.append(
            f'<polygon points="{points}" fill="{_preview_fill_color(original_triangle, depth_basis)}" fill-opacity="0.88"{stroke_attrs}/>'
        )
    elements.append("</g>")
    metadata = {
        "view": view,
        "triangle_count": len(triangles),
        "projected_bounds": {
            "umin": umin,
            "vmin": vmin,
            "umax": umax,
            "vmax": vmax,
            "ulen": umax - umin,
            "vlen": vmax - vmin,
        },
        "panel": {
            "x": panel_x,
            "y": panel_y,
            "width": panel_width,
            "height": panel_height,
            "scale": scale,
        },
    }
    return "\n".join(elements), metadata


def render_stl_preview(
    file_path: str,
    output_path: str,
    views: Optional[List[str]] = None,
    width: int = 1200,
    height: int = 900,
    margin: int = 24,
    show_edges: bool = True,
) -> Dict[str, Any]:
    """
    Renders an STL mesh to a dependency-free SVG contact sheet for visual review.
    """
    if not output_path:
        raise ValueError("output_path is required.")
    if width < 200 or height < 160:
        raise ValueError("Preview width and height must be at least 200x160.")
    if margin < 0:
        raise ValueError("Preview margin cannot be negative.")

    resolved_path = _resolve_existing_file(file_path)
    triangles, stl_encoding = _read_stl_triangles(resolved_path)
    normalized_views = _normalize_preview_views(views)
    analysis = _analyze_stl_triangles(triangles, stl_encoding, resolved_path)

    columns = 2 if len(normalized_views) > 1 else 1
    rows = math.ceil(len(normalized_views) / columns)
    panel_width = width / columns
    panel_height = height / rows
    panels = []
    panel_metadata = []
    for index, view in enumerate(normalized_views):
        column = index % columns
        row = index // columns
        panel_svg, metadata = _render_stl_preview_panel(
            triangles,
            view,
            column * panel_width,
            row * panel_height,
            panel_width,
            panel_height,
            float(margin),
            show_edges,
        )
        panels.append(panel_svg)
        panel_metadata.append(metadata)

    target_path = os.path.abspath(os.path.expanduser(output_path))
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    title = f"STL preview: {os.path.basename(resolved_path)}"
    svg = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        "<metadata>",
        escape(f"{title}; views={','.join(normalized_views)}; triangles={len(triangles)}"),
        "</metadata>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f6f8fb"/>',
        *panels,
        "</svg>",
        "",
    ])
    with open(target_path, "w", encoding="utf-8") as preview_file:
        preview_file.write(svg)

    return {
        "success": True,
        "message": f"STL preview rendered: {target_path}",
        "source_file": {
            "path": resolved_path,
            "format": "stl",
            "stl_encoding": stl_encoding,
        },
        "output_file": target_path,
        "output_format": "svg",
        "view_count": len(normalized_views),
        "views": panel_metadata,
        "preview": {
            "width": width,
            "height": height,
            "margin": margin,
            "show_edges": show_edges,
        },
        "analysis": analysis,
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

    source_path = _resolve_existing_file(source_file_path)
    target_path = _resolve_existing_file(target_file_path)
    source_triangles, source_encoding = _read_stl_triangles(source_path)
    target_triangles, target_encoding = _read_stl_triangles(target_path)

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
        _threshold_compare_summary(source_items, target_items, _finite_number(threshold, "z_thresholds[]"))
        for threshold in (z_thresholds or [])
    ]

    range_summaries = []
    for index, z_range in enumerate(target_only_z_ranges or []):
        if not isinstance(z_range, dict):
            raise ValueError("target_only_z_ranges entries must be objects with min_z and max_z.")
        min_z = _finite_number(z_range.get("min_z"), f"target_only_z_ranges[{index}].min_z")
        max_z = _finite_number(z_range.get("max_z"), f"target_only_z_ranges[{index}].max_z")
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
            "bounds": _bounds_for_vertices(vertices_in_range),
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
        "source_only_vertex_bounds": _bounds_for_vertices(source_only_vertices),
        "target_only_vertex_bounds": _bounds_for_vertices(target_only_vertices),
        "z_thresholds": threshold_summaries,
        "target_only_z_ranges": range_summaries,
    }


AXIS_INDICES = {"x": 0, "y": 1, "z": 2}
PLANE_AXES = {
    "x": ("y", "z"),
    "y": ("x", "z"),
    "z": ("x", "y"),
}


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
    if _triangle_area(triangle) <= 1e-12:
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

    resolved_path = _resolve_existing_file(file_path)
    triangles, stl_encoding = _read_stl_triangles(resolved_path)
    if len(triangles) > max_triangles:
        raise ValueError(
            f"STL has {len(triangles)} triangles, which exceeds max_triangles={max_triangles}. "
            "Increase the limit only for small, intentional conversions."
        )

    analysis = _analyze_stl_triangles(triangles, stl_encoding, resolved_path)
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

    components = _stl_triangle_components(triangles)
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


def _ray_triangle_intersection(origin: Vertex, direction: Vertex, triangle: Triangle, epsilon: float = 1e-9) -> Optional[float]:
    v0, v1, v2 = triangle
    edge1 = _subtract(v1, v0)
    edge2 = _subtract(v2, v0)
    h = _cross(direction, edge2)
    determinant = _dot(edge1, h)
    if -epsilon < determinant < epsilon:
        return None
    inverse_determinant = 1.0 / determinant
    s = _subtract(origin, v0)
    u = inverse_determinant * _dot(s, h)
    if u < -epsilon or u > 1.0 + epsilon:
        return None
    q = _cross(s, edge1)
    v = inverse_determinant * _dot(direction, q)
    if v < -epsilon or u + v > 1.0 + epsilon:
        return None
    t = inverse_determinant * _dot(edge2, q)
    if t <= epsilon:
        return None
    return t


def _point_inside_mesh(point: Vertex, triangles: List[Triangle]) -> bool:
    direction = _normalize_vector((1.0, 0.3713906763541037, 0.2179280434782609), "ray direction")
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

    resolved_path = _resolve_existing_file(file_path)
    triangles, stl_encoding = _read_stl_triangles(resolved_path)
    start_point = _coerce_vector(start, "start")
    end_point = _coerce_vector(end, "end")
    probe_width = _finite_number(width, "width")
    probe_height = _finite_number(height, "height")
    path_vector = _subtract(end_point, start_point)
    path_length = _length(path_vector)
    if path_length <= 1e-12:
        raise ValueError("start and end must be different points.")
    path_axis = _normalize_vector(path_vector, "path")
    up_seed = _coerce_vector(up_direction, "up_direction") if up_direction is not None else (0.0, 0.0, 1.0)
    if abs(_dot(_normalize_vector(up_seed, "up_direction"), path_axis)) > 0.98:
        up_seed = (1.0, 0.0, 0.0)
    side_axis = _normalize_vector(_cross(path_axis, up_seed), "side direction")
    up_axis = _normalize_vector(_cross(side_axis, path_axis), "up direction")
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
        center = _add(start_point, _scale(path_vector, t))
        station_blocked = 0
        for side_offset, up_offset in sample_offsets:
            sample_point = _add(center, _add(_scale(side_axis, side_offset), _scale(up_axis, up_offset)))
            total_samples += 1
            inside_material = _point_inside_mesh(sample_point, triangles)
            if inside_material:
                blocked_count += 1
                station_blocked += 1
                if len(blocked_samples) < max_blocked_samples:
                    blocked_samples.append({
                        "station_index": station_index,
                        "t": t,
                        "point": _vector_to_dict(sample_point),
                        "side_offset": side_offset,
                        "up_offset": up_offset,
                    })
        station_summaries.append({
            "station_index": station_index,
            "t": t,
            "center": _vector_to_dict(center),
            "blocked_samples": station_blocked,
            "sample_count": len(sample_offsets),
            "clear": station_blocked == 0,
        })

    return {
        "file": {"path": resolved_path, "format": "stl", "stl_encoding": stl_encoding},
        "path": {
            "start": _vector_to_dict(start_point),
            "end": _vector_to_dict(end_point),
            "length": path_length,
            "axis": _vector_to_dict(path_axis),
            "side_direction": _vector_to_dict(side_axis),
            "up_direction": _vector_to_dict(up_axis),
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


def _finite_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def _axis_mapping(mapping: Optional[Dict[str, float]], default: float, name: str) -> Dict[str, float]:
    values = {"x": default, "y": default, "z": default}
    if not mapping:
        return values
    for axis, value in mapping.items():
        axis_name = axis.lower()
        if axis_name not in values:
            raise ValueError(f"{name} contains unsupported axis '{axis}'. Use x, y, or z.")
        values[axis_name] = _finite_number(value, f"{name}.{axis_name}")
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
        analysis = _analyze_stl_triangles(transformed, "ascii")
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
    source_path = _resolve_existing_file(file_path)
    target_path = os.path.abspath(os.path.expanduser(output_path))
    source_format = _normalize_file_format(source_path, "stl")
    if source_format != "stl":
        raise ValueError("transform_stl_mesh only supports STL input.")

    triangles, stl_encoding = _read_stl_triangles(source_path)
    before = _analyze_stl_triangles(triangles, stl_encoding, source_path)
    scale_values = _axis_mapping(scale, 1.0, "scale")

    if target_size:
        dimensions = before["bounding_box"]
        for axis, target_value in target_size.items():
            axis_name = axis.lower()
            if axis_name not in scale_values:
                raise ValueError(f"target_size contains unsupported axis '{axis}'. Use x, y, or z.")
            target_number = _finite_number(target_value, f"target_size.{axis_name}")
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

    after = _analyze_stl_triangles(transformed_triangles, "ascii", target_path)
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

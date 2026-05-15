import os
import re
import math
import struct
import logging
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple

# Import CadQuery-related libraries directly needed by core functions
import cadquery as cq
from cadquery import cqgi
from cadquery import exporters

log = logging.getLogger(__name__) # Use standard logging

# --- Core Logic Functions (Moved from server.py) ---

def parse_docstring_metadata(docstring: Optional[str]) -> Dict[str, Any]:
    """
    Parses metadata key-value pairs from a Python docstring.

    Looks for lines formatted as 'Key: Value'. Converts keys to lowercase
    snake_case. Handles 'Tags' key specially, splitting by comma.

    Args:
        docstring: The docstring to parse.

    Returns:
        A dictionary containing the parsed metadata.
    """
    metadata = {}
    if not docstring: return metadata
    lines = docstring.strip().split('\n')
    for line in lines:
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            key_part = parts[0].strip()
            value = parts[1].strip()
            # Check if value is non-empty and original key_part doesn't contain spaces
            # before converting to snake_case and checking isidentifier()
            if value and ' ' not in key_part:
                 key = key_part.lower() # No need for replace if no spaces
                 if key.isidentifier():
                     if key == 'tags':
                         metadata[key] = [tag.strip().lower() for tag in value.split(',') if tag.strip()]
                     else:
                         metadata[key] = value
            # Handle known multi-word keys explicitly (like 'Part Name')
            elif value and key_part.lower() == "part name":
                 metadata["part_name"] = value
            # Add other known multi-word keys here if needed
    return metadata

def execute_cqgi_script(script_content: str) -> cqgi.BuildResult:
    """Parses and executes a CQGI script."""
    log.info("Parsing script with CQGI..."); model = cqgi.parse(script_content)
    log.info("Script parsed."); log.info(f"Building model...")
    # Build without attempting parameter injection via arguments
    build_result = model.build(); log.info(f"Model build finished. Success: {build_result.success}")
    if not build_result.success:
        log.error(f"Script execution failed: {build_result.exception}")
        # Don't raise here, let the caller handle the BuildResult
        # raise Exception(f"Script execution failed: {build_result.exception}")
    return build_result

def _substitute_parameters(script_lines: List[str], params: Dict[str, Any]) -> List[str]:
    """Substitutes parameters into script lines marked with # PARAM."""
    modified_lines = []
    param_pattern = re.compile(r"^\s*(\w+)\s*=\s*.*#\s*PARAM\s*$")
    for line in script_lines:
        match = param_pattern.match(line)
        if match:
            param_name = match.group(1)
            if param_name in params:
                value = params[param_name]
                # Format value as Python literal (basic handling)
                if isinstance(value, str): formatted_value = repr(value)
                elif isinstance(value, (int, float, bool, list, dict, tuple)) or value is None: formatted_value = repr(value)
                else: formatted_value = str(value) # Fallback for other types
                indent = line[:match.start(1)] # Preserve original indentation
                modified_lines.append(f"{indent}{param_name} = {formatted_value} # PARAM (Substituted)")
                log.debug(f"Substituted parameter '{param_name}' with value: {formatted_value}")
                continue # Skip original line
        modified_lines.append(line)
    return modified_lines

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


def _rounded_vertex(vertex: Vertex) -> Vertex:
    return (round(vertex[0], 8), round(vertex[1], 8), round(vertex[2], 8))


def _analyze_stl_triangles(triangles: List[Triangle], stl_encoding: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    if not triangles:
        raise ValueError("Cannot analyze an STL mesh with no triangles.")

    vertices = [vertex for triangle in triangles for vertex in triangle]
    xs = [vertex[0] for vertex in vertices]
    ys = [vertex[1] for vertex in vertices]
    zs = [vertex[2] for vertex in vertices]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    xlen, ylen, zlen = xmax - xmin, ymax - ymin, zmax - zmin

    edge_counts: Counter[Tuple[Vertex, Vertex]] = Counter()
    for triangle in triangles:
        rounded = [_rounded_vertex(vertex) for vertex in triangle]
        edge_counts[tuple(sorted((rounded[0], rounded[1])))] += 1
        edge_counts[tuple(sorted((rounded[1], rounded[2])))] += 1
        edge_counts[tuple(sorted((rounded[2], rounded[0])))] += 1

    boundary_edges = sum(1 for count in edge_counts.values() if count == 1)
    non_manifold_edges = sum(1 for count in edge_counts.values() if count > 2)
    watertight = boundary_edges == 0 and non_manifold_edges == 0
    signed_volume = sum(_triangle_signed_volume(triangle) for triangle in triangles)
    absolute_tetra_volume = sum(abs(_triangle_signed_volume(triangle)) for triangle in triangles)

    warnings = []
    if not watertight:
        warnings.append("Volume is only reliable for closed, consistently oriented STL meshes.")

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
        "bounding_box": {
            "xmin": xmin,
            "ymin": ymin,
            "zmin": zmin,
            "xmax": xmax,
            "ymax": ymax,
            "zmax": zmax,
            "xlen": xlen,
            "ylen": ylen,
            "zlen": zlen,
            "center": {
                "x": xmin + xlen / 2,
                "y": ymin + ylen / 2,
                "z": zmin + zlen / 2,
            },
        },
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
        },
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

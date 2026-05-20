from __future__ import annotations

import math
import os
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from .mesh_primitives import Triangle, Vertex, analyze_stl_triangles, read_stl_triangles, resolve_existing_file


_VIEW_ALIASES: Dict[str, str] = {
    "isometric": "iso",
    "perspective": "iso",
}

def _normalize_preview_views(views: Optional[List[str]]) -> List[str]:
    raw = [view.strip().lower() for view in (views or ["top", "front", "right", "iso"]) if view.strip()]
    normalized = [_VIEW_ALIASES.get(v, v) for v in raw]
    supported = {"top", "front", "right", "iso", "left", "back", "bottom"}
    unsupported = [view for view in normalized if view not in supported]
    if unsupported:
        raise ValueError(
            f"Unsupported STL preview view(s): {', '.join(unsupported)}. "
            f"Supported: {', '.join(sorted(supported))} (aliases: isometric→iso)"
        )
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
    if view == "left":
        # Camera at -X looking toward +X; flip horizontal to avoid mirror image
        return (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)
    if view == "back":
        # Camera at +Y looking toward -Y; flip horizontal to avoid mirror image
        return (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)
    if view == "bottom":
        # Camera below (-Z) looking up; flip v to avoid mirror image of top
        return (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)
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

    resolved_path = resolve_existing_file(file_path)
    triangles, stl_encoding = read_stl_triangles(resolved_path)
    normalized_views = _normalize_preview_views(views)
    analysis = analyze_stl_triangles(triangles, stl_encoding, resolved_path)

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

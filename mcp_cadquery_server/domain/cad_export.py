from __future__ import annotations

import logging
import os
from typing import Any, Optional

import cadquery as cq
from cadquery import exporters

log = logging.getLogger(__name__)


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

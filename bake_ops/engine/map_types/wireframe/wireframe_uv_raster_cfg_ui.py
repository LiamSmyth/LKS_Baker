"""UI for the ``wireframe_uv_raster`` bake method."""
from __future__ import annotations

from typing import Any


def draw_wireframe_uv_raster_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Wireframe raster method settings."""
    _ = project
    box = layout.box()
    box.label(text='Wireframe UV Raster', icon='MESH_GRID')
    box.prop(entry, 'lks_wireframe_color', text='Line Color')
    box.prop(entry, 'lks_wireframe_aa_quality', text='AA Quality')
    box.prop(entry, 'lks_wireframe_line_thickness', text='Line Thickness (px)')
    box.label(text='Stroke width is in atlas texels', icon='INFO')

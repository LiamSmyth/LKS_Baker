"""UI for the ``emit_raster`` specular bake method."""
from __future__ import annotations

from typing import Any


def draw_emit_raster_settings(layout: Any, entry: Any, project: Any) -> None:
    """Emit raster H→L raycast settings (project-level cage props)."""
    _ = entry
    box = layout.box()
    box.label(text="Emit Raster (H→L)", icon="EXPORT")
    if project is not None:
        box.prop(project, "cage_extrusion", text="Cage Extrusion")
        box.prop(project, "max_ray_distance", text="Max Ray Distance")
    else:
        box.label(text="Uses project cage / ray distance", icon="INFO")

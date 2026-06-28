"""UI for Cycles COMBINED lighting bakes (``blender`` method)."""
from __future__ import annotations

from typing import Any


def draw_blender_settings(layout: Any, entry: Any, project: Any) -> None:
    """Draw lighting-specific Cycles settings below the Method row."""
    _ = project
    settings = entry.lks_lighting
    box = layout.box()
    box.label(text='Lighting Bake', icon='LIGHT')
    col = box.column(align=True)
    col.prop(settings, 'max_bounce_override')
    col.prop(settings, 'clamp_direct')
    col.prop(settings, 'clamp_indirect')

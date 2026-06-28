"""UI for the ``soft_curvature`` bake method."""
from __future__ import annotations

from typing import Any


def draw_soft_curvature_settings(
    layout: Any,
    entry: Any,
    project: Any | None = None,
) -> None:
    """Soft curvature bake-engine parameters."""
    _ = project
    soft = entry.lks_curvature_soft
    box = layout.box()
    box.label(text='Soft Curvature', icon='MOD_MULTIRES')
    box.prop(entry, 'lks_curvature_device', text='Device')
    col = box.column(align=True)
    col.prop(soft, 'normalize_each_scale')
    col.prop(soft, 'normalize_percentile', slider=True)
    col.prop(soft, 'convex_is_white')
    col.prop(soft, 'samples_per_radius')
    col.prop(soft, 'max_radius')
    col.separator()
    col.label(text='Output pack')
    col.prop(soft, 'pack_strength', slider=True)
    col.prop(soft, 'pack_percentile', slider=True)
    col.prop(soft, 'pack_flat', slider=True)
    box.label(text='Needs normal_object + low mesh UVs', icon='INFO')

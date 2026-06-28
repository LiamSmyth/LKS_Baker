"""UI for the ``bent_normal_object`` bake method."""
from __future__ import annotations

from typing import Any


def draw_bent_normal_object_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Draw bent-normal object-space settings."""
    _ = project
    props = entry.lks_bent_normal_object
    box = layout.box()
    box.label(text='Bent Normal (Object)', icon='NORMALS_VERTEX')
    col = box.column(align=True)
    col.prop(props, 'directions')
    col.prop(props, 'steps_per_direction')
    col.prop(props, 'radius_world')
    col.prop(props, 'spread_angle_deg')
    col.prop(props, 'bias')

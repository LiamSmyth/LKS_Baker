"""UI for the ``hemisphere_trace`` bent-normal bake method."""
from __future__ import annotations

from typing import Any


def draw_hemisphere_trace_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Draw hemisphere-trace bent-normal settings."""
    _ = project
    props = entry.lks_bent_normal
    box = layout.box()
    box.label(text='Hemisphere Trace', icon='NORMALS_VERTEX')
    box.prop(props, 'sample_count', text='Sample Count')
    box.prop(props, 'steps_per_direction', text='Steps / Direction')
    box.prop(props, 'radius_world', text='Radius (world)')
    box.prop(props, 'bias', text='Bias')
    box.prop(props, 'spread', text='Hemisphere Spread')

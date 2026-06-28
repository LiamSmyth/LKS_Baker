"""UI for the ``convexity_from_curvature`` bake method."""
from __future__ import annotations

from typing import Any


def draw_convexity_from_curvature_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Convexity From Curvature', icon='MOD_BOOLEAN')
    box.label(text='Splits convex channel from curvature bake', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

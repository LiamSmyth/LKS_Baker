"""UI for the ``cavity_from_curvature`` bake method."""
from __future__ import annotations

from typing import Any


def draw_cavity_from_curvature_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Cavity From Curvature', icon='MOD_BOOLEAN')
    box.label(text='Splits concave channel from curvature bake', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

"""UI for the ``normal_cavity`` bake method."""
from __future__ import annotations

from typing import Any


def draw_normal_cavity_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Normal Cavity', icon='SHADING_SOLID')
    box.label(text='Normal-cavity multiscale AO', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

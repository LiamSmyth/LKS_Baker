"""UI for the ``normal_height_hbao`` bake method."""
from __future__ import annotations

from typing import Any


def draw_normal_height_hbao_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Normal Height HBAO', icon='MOD_SUBSURF')
    box.label(text='Normal-derived height + texture HBAO', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

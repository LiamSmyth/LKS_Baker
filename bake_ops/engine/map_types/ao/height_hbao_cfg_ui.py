"""UI for the ``height_hbao`` bake method."""
from __future__ import annotations

from typing import Any


def draw_height_hbao_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Height HBAO', icon='MOD_DISPLACE')
    box.label(text='Height integrate + texture HBAO', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

"""UI for the ``atlas_hbao`` bake method."""
from __future__ import annotations

from typing import Any


def draw_atlas_hbao_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Atlas HBAO', icon='WORLD')
    box.label(text='World-space horizon AO from position + object normal', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

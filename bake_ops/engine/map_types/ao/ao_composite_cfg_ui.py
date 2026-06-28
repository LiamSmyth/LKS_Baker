"""UI for the ``ao_composite`` bake method."""
from __future__ import annotations

from typing import Any


def draw_ao_composite_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='AO Composite', icon='NODE_COMPOSITING')
    box.label(text='Atlas macro + normal-height detail blend', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

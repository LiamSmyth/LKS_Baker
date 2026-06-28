"""UI for the ``uv_island_from_mesh`` bake method."""
from __future__ import annotations

from typing import Any


def draw_uv_island_from_mesh_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='UV Island From Mesh', icon='UV')
    box.label(text='Pseudo-random island colors from low mesh UV charts', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

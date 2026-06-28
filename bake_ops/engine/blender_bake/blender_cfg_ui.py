"""UI for the shared ``blender`` Cycles bake method."""
from __future__ import annotations

from typing import Any


def draw_blender_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Blender Bake method header — post-process lives in shared gear section."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Blender Bake', icon='RENDER_STILL')
    box.label(text='Cycles / emit mesh baking', icon='INFO')

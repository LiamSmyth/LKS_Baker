"""UI for ``normal_object_from_tangent`` derive method."""
from __future__ import annotations

from typing import Any


def draw_normal_object_from_tangent_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Informational panel — method has no RNA overrides yet."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Normal From Tangent', icon='NORMALS_VERTEX')
    box.label(text='Uses tangent normal + per-texel TBN', icon='INFO')

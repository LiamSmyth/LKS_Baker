"""UI for the ``alpha_mask_from_transparency`` bake method."""
from __future__ import annotations

from typing import Any


def draw_alpha_mask_from_transparency_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Method settings panel (scaffold — RNA tuning pending)."""
    _ = entry
    _ = project
    box = layout.box()
    box.label(text='Alpha Mask From Transparency', icon='IMAGE_ALPHA')
    box.label(text='Hard threshold on transparency bake alpha', icon='INFO')
    box.label(text='Using engine defaults', icon='BLANK1')

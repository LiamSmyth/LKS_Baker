"""UI for the ``group_id_raster`` bake method."""
from __future__ import annotations

from typing import Any


def draw_group_id_raster_settings(
    layout: Any,
    entry: Any,
    project: Any,
) -> None:
    """Draw group ID attribute targeting controls."""
    _ = project
    box = layout.box()
    box.label(text="Group ID Source")
    box.prop(entry, "lks_group_id_attr_preset", text="Preset")
    if str(entry.lks_group_id_attr_preset) == "CUSTOM":
        box.prop(entry, "lks_group_id_attribute_name", text="Attribute")
    box.prop(entry, "lks_group_id_treat_zero_as_background", text="Zero = Background")

"""Assign bpy Panel ``bl_order`` from sibling ``bl_label`` sort order."""

from __future__ import annotations

from collections.abc import Iterable

import bpy


def panel_label_sort_key(panel_cls: type[bpy.types.Panel]) -> str:
    label = getattr(panel_cls, "bl_label", None) or panel_cls.__name__
    return label.casefold()


def assign_bl_order_by_label(
    panel_classes: Iterable[type[bpy.types.Panel]],
    *,
    base: int = 0,
    step: int = 10,
) -> tuple[type[bpy.types.Panel], ...]:
    """Sort panels by ``bl_label`` (case-insensitive) and set ``bl_order``.

    Call before ``bpy.utils.register_class``. Lower ``bl_order`` appears higher.
    Returns the sorted panel classes (same objects, new order).
    """
    ordered = sorted(panel_classes, key=panel_label_sort_key)
    for index, panel_cls in enumerate(ordered):
        panel_cls.bl_order = base + index * step
    return tuple(ordered)

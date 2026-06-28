"""Capture and restore object-mode selection by object name."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import bpy

from . import object_helpers


@dataclass(frozen=True, slots=True)
class SelectionSnapshot:
    """Ordered selected object names plus active object name."""

    selected_names: tuple[str, ...]
    active_name: str | None


def capture_selection_state(context: bpy.types.Context) -> SelectionSnapshot:
    """Snapshot current selection and active object using names only."""
    selected = object_helpers.context_selected_objects(context)
    active = context.view_layer.objects.active
    active_name: str | None = None
    if active is not None:
        try:
            active_name = active.name
        except ReferenceError:
            active_name = None
    return SelectionSnapshot(
        selected_names=tuple(obj.name for obj in selected),
        active_name=active_name,
    )


def reselect_objects(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    active: bpy.types.Object | None = None,
) -> None:
    """Select ``objects`` and set the active object."""
    bpy.ops.object.select_all(action='DESELECT')
    valid = object_helpers.filter_valid_objects(objects)
    for obj in valid:
        obj.select_set(True)
    if active is not None and active.name in bpy.data.objects:
        context.view_layer.objects.active = active
    elif valid:
        context.view_layer.objects.active = valid[-1]


def select_objects_by_name(
    context: bpy.types.Context,
    names: Iterable[str],
    *,
    active: str | None = None,
) -> None:
    """Select objects by name; optional ``active`` name for the active object."""
    objects = [
        bpy.data.objects[name]
        for name in names
        if name in bpy.data.objects
    ]
    active_obj = (
        bpy.data.objects[active]
        if active is not None and active in bpy.data.objects
        else None
    )
    reselect_objects(context, objects, active_obj)


def restore_selection_by_name_map(
    context: bpy.types.Context,
    snapshot: SelectionSnapshot,
    name_map: dict[str, str],
    *,
    fallback_same_name: bool = True,
) -> None:
    """Restore selection/active from ``snapshot`` via ``name_map`` (old → new names)."""
    bpy.ops.object.select_all(action='DESELECT')

    restored: list[bpy.types.Object] = []
    for old_name in snapshot.selected_names:
        new_name = name_map.get(old_name)
        if new_name is None and fallback_same_name:
            new_name = old_name
        if new_name is None or new_name not in bpy.data.objects:
            continue
        obj = bpy.data.objects[new_name]
        obj.select_set(True)
        restored.append(obj)

    active_obj: bpy.types.Object | None = None
    if snapshot.active_name is not None:
        mapped_active = name_map.get(snapshot.active_name)
        if mapped_active is None and fallback_same_name:
            mapped_active = snapshot.active_name
        if mapped_active is not None and mapped_active in bpy.data.objects:
            active_obj = bpy.data.objects[mapped_active]

    if active_obj is None and restored:
        active_obj = restored[-1]

    if active_obj is not None:
        context.view_layer.objects.active = active_obj

"""Viewport shading snapshot/restore for bake runs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import bpy


@dataclass(frozen=True, slots=True)
class _SpaceView3DShadingState:
    space: bpy.types.SpaceView3D
    shading_type: str
    use_scene_lights: bool
    use_scene_world: bool


@dataclass(frozen=True, slots=True)
class ViewportShadingSnapshot:
    """Prior View3D shading flags to restore after bake."""

    states: tuple[_SpaceView3DShadingState, ...] = ()


def _iter_view3d_spaces_in_area(
    area: bpy.types.Area | None,
) -> list[bpy.types.SpaceView3D]:
    if area is None or area.type != 'VIEW_3D':
        return []
    return [space for space in area.spaces if space.type == 'VIEW_3D']


def snapshot_active_area_viewport_shading(
    context: bpy.types.Context,
) -> ViewportShadingSnapshot:
    """Capture shading type and scene-light/world flags for the active 3D View area."""
    states: list[_SpaceView3DShadingState] = []
    for space in _iter_view3d_spaces_in_area(context.area):
        shading = space.shading
        states.append(
            _SpaceView3DShadingState(
                space=space,
                shading_type=shading.type,
                use_scene_lights=shading.use_scene_lights,
                use_scene_world=shading.use_scene_world,
            ),
        )
    return ViewportShadingSnapshot(states=tuple(states))


def restore_active_area_viewport_shading(
    snapshot: ViewportShadingSnapshot,
) -> None:
    """Restore shading flags captured from ``snapshot_active_area_viewport_shading``."""
    for state in snapshot.states:
        try:
            if state.space.type != 'VIEW_3D':
                continue
            shading = state.space.shading
        except ReferenceError:
            continue
        shading.type = state.shading_type
        shading.use_scene_lights = state.use_scene_lights
        shading.use_scene_world = state.use_scene_world


@contextmanager
def temporary_preserve_viewport_shading(
    context: bpy.types.Context,
) -> Iterator[None]:
    """Capture viewport shading at entry; restore on exit (including errors)."""
    snapshot = snapshot_active_area_viewport_shading(context)
    try:
        yield
    finally:
        restore_active_area_viewport_shading(snapshot)

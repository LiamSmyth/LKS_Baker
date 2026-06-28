"""Low-poly render/ray visibility snapshot/restore for bake runs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import bpy

from lks_baker.shared_utilities import object_helpers
from lks_baker.shared_utilities.visibility_helpers import set_object_ray_visibility

_RAY_VISIBILITY_RNA: tuple[str, ...] = (
    'visible_diffuse',
    'visible_glossy',
    'visible_transmission',
    'visible_volume_scatter',
    'visible_shadow',
    'visible_camera',
)


@dataclass
class LowPolyVisibilitySnapshot:
    """Prior low-poly render/ray flags to restore after bake."""

    object_hide_render: dict[str, bool] = field(default_factory=dict)
    object_ray_visibility: dict[str, dict[str, bool]] = field(default_factory=dict)
    collection_hide_render: dict[str, bool] = field(default_factory=dict)


def _snapshot_object_ray_visibility(obj: bpy.types.Object) -> dict[str, bool]:
    return {
        rna: bool(getattr(obj, rna))
        for rna in _RAY_VISIBILITY_RNA
        if hasattr(obj, rna)
    }


def _disable_object_ray_visibility(obj: bpy.types.Object) -> None:
    set_object_ray_visibility(
        obj,
        diffuse=False,
        glossy=False,
        transmission=False,
        scatter=False,
        shadow=False,
        camera=False,
    )


def _unique_low_scope_objects(
    low_objects: list[bpy.types.Object],
    bake_target_low_names: set[str],
) -> list[bpy.types.Object]:
    """Low role objects plus any bake-target subtree members not already included."""
    merged = _unique_objects(low_objects)
    seen = {obj.name for obj in merged}
    for obj in object_helpers.filter_valid_objects(
        [bpy.data.objects.get(name) for name in bake_target_low_names],
    ):
        if obj is None or obj.name in seen:
            continue
        seen.add(obj.name)
        merged.append(obj)
    return merged


def _unique_objects(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    seen: set[str] = set()
    merged: list[bpy.types.Object] = []
    for obj in object_helpers.filter_valid_objects(objects):
        if obj.name in seen:
            continue
        seen.add(obj.name)
        merged.append(obj)
    return merged


def _unique_collections(
    collections: list[bpy.types.Collection],
) -> list[bpy.types.Collection]:
    seen: set[str] = set()
    merged: list[bpy.types.Collection] = []
    for coll in collections:
        if coll is None or coll.name in seen:
            continue
        seen.add(coll.name)
        merged.append(coll)
    return merged


def snapshot_lowpoly_render_influence(
    low_objects: list[bpy.types.Object],
    low_collections: list[bpy.types.Collection],
    *,
    bake_target_low_names: set[str],
) -> LowPolyVisibilitySnapshot:
    """Capture low-poly object/collection render and ray visibility without mutating."""
    snapshot = LowPolyVisibilitySnapshot()
    for obj in _unique_low_scope_objects(low_objects, bake_target_low_names):
        snapshot.object_hide_render[obj.name] = obj.hide_render
        snapshot.object_ray_visibility[obj.name] = _snapshot_object_ray_visibility(obj)
    for coll in _unique_collections(low_collections):
        snapshot.collection_hide_render[coll.name] = coll.hide_render
    return snapshot


def suppress_lowpoly_render_influence(
    low_objects: list[bpy.types.Object],
    low_collections: list[bpy.types.Collection],
    *,
    bake_target_low_names: set[str],
) -> LowPolyVisibilitySnapshot:
    """
    Snapshot then suppress low-poly influence on high shading during bake.

    Source lows are hidden from render; active bake-target lows stay render-enabled
    but all per-ray visibility is disabled so they cannot cast shadows on highs.
    """
    snapshot = snapshot_lowpoly_render_influence(
        low_objects,
        low_collections,
        bake_target_low_names=bake_target_low_names,
    )
    for obj in _unique_low_scope_objects(low_objects, bake_target_low_names):
        is_bake_target = obj.name in bake_target_low_names
        if not is_bake_target:
            obj.hide_render = True
        _disable_object_ray_visibility(obj)
    return snapshot


def restore_lowpoly_render_influence(
    snapshot: LowPolyVisibilitySnapshot,
    *,
    scene: bpy.types.Scene | None = None,
) -> None:
    """Restore low-poly render/ray flags captured by ``suppress_lowpoly_render_influence``."""
    for name, hidden in snapshot.object_hide_render.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.hide_render = hidden
    for name, flags in snapshot.object_ray_visibility.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        for rna, value in flags.items():
            if hasattr(obj, rna):
                setattr(obj, rna, value)
    for name, hidden in snapshot.collection_hide_render.items():
        coll = bpy.data.collections.get(name)
        if coll is None:
            continue
        coll.hide_render = hidden
    if scene is not None:
        for view_layer in scene.view_layers:
            view_layer.update()


@contextmanager
def temporary_suppress_lowpoly_render_influence(
    low_objects: list[bpy.types.Object],
    low_collections: list[bpy.types.Collection],
    *,
    bake_target_low_names: set[str],
    scene: bpy.types.Scene | None = None,
) -> Iterator[None]:
    """Suppress low-poly render/ray influence for bake duration; restore on exit."""
    snapshot = suppress_lowpoly_render_influence(
        low_objects,
        low_collections,
        bake_target_low_names=bake_target_low_names,
    )
    try:
        yield
    finally:
        restore_lowpoly_render_influence(snapshot, scene=scene)

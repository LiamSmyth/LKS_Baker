"""View-layer visibility for bake prep and Cycles bake (exclude / hide restore)."""

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


@dataclass(frozen=True, slots=True)
class _LayerCollectionVisibilityState:
    view_layer_name: str
    collection_name: str
    exclude: bool
    hide_viewport: bool


@dataclass
class BakeViewLayerSnapshot:
    """Prior view-layer exclude/hide flags to restore after bake."""

    layer_states: list[_LayerCollectionVisibilityState] = field(default_factory=list)
    object_hide_viewport: dict[str, bool] = field(default_factory=dict)
    object_hide_render: dict[str, bool] = field(default_factory=dict)
    collection_hide_viewport: dict[str, bool] = field(default_factory=dict)
    collection_hide_render: dict[str, bool] = field(default_factory=dict)


# Public alias for bake-run ensure/restore API.
BakeVisibilitySnapshot = BakeViewLayerSnapshot


@dataclass
class SceneObjectVisibilitySnapshot:
    """Per-object viewport/render hide flags for Cycles bake isolation restore."""

    hide_viewport: dict[str, bool] = field(default_factory=dict)
    hide_render: dict[str, bool] = field(default_factory=dict)
    ray_visibility: dict[str, dict[str, bool]] = field(default_factory=dict)


def _iter_layer_collections(
    layer_coll: bpy.types.LayerCollection,
) -> Iterator[bpy.types.LayerCollection]:
    yield layer_coll
    for child in layer_coll.children:
        yield from _iter_layer_collections(child)


def _layer_collections_for_collection(
    view_layer: bpy.types.ViewLayer,
    target: bpy.types.Collection,
) -> list[bpy.types.LayerCollection]:
    matches: list[bpy.types.LayerCollection] = []
    for layer_coll in _iter_layer_collections(view_layer.layer_collection):
        if layer_coll.collection == target:
            matches.append(layer_coll)
    return matches


def _object_names_in_view_layer(view_layer: bpy.types.ViewLayer) -> set[str]:
    return {obj.name for obj in view_layer.objects}


def iter_objects_in_collection_tree(
    root: bpy.types.Collection | None,
) -> list[bpy.types.Object]:
    """Objects linked under ``root`` plus parented descendants (nested collections)."""
    if root is None:
        return []
    seen: set[str] = set()
    objects: list[bpy.types.Object] = []
    coll_stack = [root]
    while coll_stack:
        coll = coll_stack.pop()
        obj_stack = list(coll.objects)
        while obj_stack:
            obj = obj_stack.pop()
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
            obj_stack.extend(obj.children)
        coll_stack.extend(coll.children)
    return objects


def object_names_in_collection_tree(
    root: bpy.types.Collection | None,
) -> set[str]:
    """Every object name under ``root`` (collections + parented descendants)."""
    return {obj.name for obj in iter_objects_in_collection_tree(root)}


def _unique_objects(
    *object_lists: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    seen: set[str] = set()
    merged: list[bpy.types.Object] = []
    for objects in object_lists:
        for obj in object_helpers.filter_valid_objects(objects):
            if obj.name in seen:
                continue
            seen.add(obj.name)
            merged.append(obj)
    return merged


def snapshot_view_layer_visibility(
    context: bpy.types.Context,
    collections: list[bpy.types.Collection],
    objects: list[bpy.types.Object],
) -> BakeViewLayerSnapshot:
    """Capture layer-collection exclude/hide and object viewport hide for restore."""
    scene = context.scene
    view_layer = context.view_layer
    target_collections = {coll for coll in collections if coll is not None}
    snapshot = BakeViewLayerSnapshot()

    for coll in target_collections:
        for layer_coll in _layer_collections_for_collection(view_layer, coll):
            snapshot.layer_states.append(
                _LayerCollectionVisibilityState(
                    view_layer_name=view_layer.name,
                    collection_name=coll.name,
                    exclude=layer_coll.exclude,
                    hide_viewport=layer_coll.hide_viewport,
                ),
            )

    for obj in object_helpers.filter_valid_objects(objects):
        snapshot.object_hide_viewport[obj.name] = obj.hide_viewport
        snapshot.object_hide_render[obj.name] = obj.hide_render

    for coll in target_collections:
        snapshot.collection_hide_viewport[coll.name] = coll.hide_viewport
        snapshot.collection_hide_render[coll.name] = coll.hide_render

    # Also snapshot layer states on non-active view layers when collections appear there.
    for other_vl in scene.view_layers:
        if other_vl == view_layer:
            continue
        for coll in target_collections:
            for layer_coll in _layer_collections_for_collection(other_vl, coll):
                snapshot.layer_states.append(
                    _LayerCollectionVisibilityState(
                        view_layer_name=other_vl.name,
                        collection_name=coll.name,
                        exclude=layer_coll.exclude,
                        hide_viewport=layer_coll.hide_viewport,
                    ),
                )

    return snapshot


def _resolve_view_layer(scene: bpy.types.Scene, name: str) -> bpy.types.ViewLayer | None:
    for view_layer in scene.view_layers:
        if view_layer.name == name:
            return view_layer
    return None


def restore_view_layer_visibility(
    context: bpy.types.Context,
    snapshot: BakeViewLayerSnapshot,
) -> None:
    """Restore layer-collection and object viewport hide flags from snapshot."""
    scene = context.scene
    restored_layers: set[tuple[str, str]] = set()

    for state in snapshot.layer_states:
        key = (state.view_layer_name, state.collection_name)
        if key in restored_layers:
            continue
        view_layer = _resolve_view_layer(scene, state.view_layer_name)
        coll = bpy.data.collections.get(state.collection_name)
        if view_layer is None or coll is None:
            continue
        for layer_coll in _layer_collections_for_collection(view_layer, coll):
            layer_coll.exclude = state.exclude
            layer_coll.hide_viewport = state.hide_viewport
        restored_layers.add(key)

    for name, hidden in snapshot.object_hide_viewport.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.hide_viewport = hidden

    for name, hidden in snapshot.object_hide_render.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.hide_render = hidden

    for name, hidden in snapshot.collection_hide_viewport.items():
        coll = bpy.data.collections.get(name)
        if coll is None:
            continue
        coll.hide_viewport = hidden

    for name, hidden in snapshot.collection_hide_render.items():
        coll = bpy.data.collections.get(name)
        if coll is None:
            continue
        coll.hide_render = hidden

    context.view_layer.update()


def enable_collections_in_view_layer(
    context: bpy.types.Context,
    collections: list[bpy.types.Collection],
) -> None:
    """Un-exclude and unhide layer collections so their objects join the view layer."""
    scene = context.scene
    target_collections = {coll for coll in collections if coll is not None}
    if not target_collections:
        return

    for view_layer in scene.view_layers:
        for coll in target_collections:
            for layer_coll in _layer_collections_for_collection(view_layer, coll):
                layer_coll.exclude = False
                layer_coll.hide_viewport = False

    context.view_layer.update()


def _ensure_collections_visible(collections: list[bpy.types.Collection]) -> None:
    for coll in collections:
        if coll is None:
            continue
        coll.hide_viewport = False
        coll.hide_render = False


def make_objects_visible_for_bake(objects: list[bpy.types.Object]) -> None:
    """Unhide viewport/render and clear outliner hide for bake-relevant objects."""
    for obj in object_helpers.filter_valid_objects(objects):
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False)


def ensure_bake_project_visible(
    context: bpy.types.Context,
    collections: list[bpy.types.Collection],
    project_objects: list[bpy.types.Object],
    *,
    bake_targets: list[bpy.types.Object] | None = None,
) -> BakeVisibilitySnapshot:
    """
    Snapshot visibility for bake project scope, then ensure render-ready visibility.

    Covers view-layer excludes, collection hide flags, and per-object viewport/render
    hide on project members plus optional prep/target meshes.
    """
    objects = _unique_objects(project_objects, bake_targets or [])
    if objects:
        objects = object_helpers.collect_objects_in_subtrees(
            object_helpers.filter_valid_objects(objects),
        )
    snapshot = snapshot_view_layer_visibility(context, collections, objects)
    enable_collections_in_view_layer(context, collections)
    _ensure_collections_visible(collections)
    make_objects_visible_for_bake(objects)
    ensure_objects_in_active_view_layer(context, context.scene, objects)
    return snapshot


def ensure_bake_targets_visible(
    objects: list[bpy.types.Object],
) -> None:
    """Ensure prep/target meshes are render-visible without altering the bake snapshot."""
    make_objects_visible_for_bake(objects)


def restore_bake_visibility(
    context: bpy.types.Context,
    snapshot: BakeVisibilitySnapshot,
) -> None:
    """Restore view-layer, collection, and object visibility from a bake snapshot."""
    restore_view_layer_visibility(context, snapshot)


def snapshot_scene_object_visibility(scene: bpy.types.Scene) -> SceneObjectVisibilitySnapshot:
    """Capture hide_viewport and hide_render for every scene object."""
    snapshot = SceneObjectVisibilitySnapshot()
    for obj in scene.objects:
        snapshot.hide_viewport[obj.name] = obj.hide_viewport
        snapshot.hide_render[obj.name] = obj.hide_render
    return snapshot


def _refresh_scene_view_layers(scene: bpy.types.Scene) -> None:
    """Flush view-layer state after batch hide_render / hide_viewport edits."""
    for view_layer in scene.view_layers:
        view_layer.update()


def _snapshot_object_ray_visibility(obj: bpy.types.Object) -> dict[str, bool]:
    return {
        rna: bool(getattr(obj, rna))
        for rna in _RAY_VISIBILITY_RNA
        if hasattr(obj, rna)
    }


def _exclude_object_from_ao_rays(obj: bpy.types.Object) -> None:
    """Keep render-enabled for active bake target but skip AO self-occlusion."""
    set_object_ray_visibility(
        obj,
        diffuse=False,
        glossy=False,
        transmission=False,
        scatter=False,
        shadow=False,
    )


def _isolation_target_names(target_objects: list[bpy.types.Object]) -> set[str]:
    """Bake roots plus every descendant — child meshes must stay render-visible."""
    roots = object_helpers.filter_valid_objects(target_objects)
    return {
        obj.name
        for obj in object_helpers.collect_objects_in_subtrees(roots)
    }


def restore_scene_object_visibility(
    snapshot: SceneObjectVisibilitySnapshot,
    *,
    scene: bpy.types.Scene | None = None,
) -> None:
    """Restore per-object viewport/render hide flags from snapshot."""
    for name, hidden in snapshot.hide_viewport.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.hide_viewport = hidden
    for name, hidden in snapshot.hide_render.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.hide_render = hidden
    for name, flags in snapshot.ray_visibility.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        for rna, value in flags.items():
            if hasattr(obj, rna):
                setattr(obj, rna, value)
    if scene is not None:
        _refresh_scene_view_layers(scene)


def isolate_scene_to_bake_targets(
    scene: bpy.types.Scene,
    target_objects: list[bpy.types.Object],
    *,
    always_visible_names: set[str] | None = None,
    force_hide_names: set[str] | None = None,
    ao_receiver_names: set[str] | None = None,
) -> SceneObjectVisibilitySnapshot:
    """
    Hide all scene objects except bake targets from viewport and render.

    Intended for AO mesh bakes only: AO rays hit every render-visible mesh, so
    duplicate source highs/lows left visible beside prep meshes cause leaks.
    Selected-to-active NORMAL/EMIT passes must not use global isolation.

  ``always_visible_names`` pins extra object names visible (e.g. child meshes
    under empty bake roots). Do not pass full project membership — AO rays hit
    every render-visible mesh, so duplicate source highs beside prep meshes
    over-occlude and produce black speckled AO.

    ``force_hide_names`` hides project stragglers even when parented under a
    bake-target empty (duplicate source highs linked in the project tree).

    ``ao_receiver_names`` marks active low targets: render-enabled for bake but
    per-ray visibility disabled so concave lows do not self-occlude during AO.
    """
    snapshot = snapshot_scene_object_visibility(scene)
    target_names = _isolation_target_names(target_objects)
    if always_visible_names:
        target_names |= always_visible_names
    hide_names = force_hide_names or set()
    receivers = ao_receiver_names or set()
    for obj in scene.objects:
        if obj.name in hide_names:
            visible = False
        else:
            visible = obj.name in target_names
        if obj.name in receivers and visible:
            snapshot.ray_visibility[obj.name] = _snapshot_object_ray_visibility(obj)
            obj.hide_viewport = False
            obj.hide_render = False
            obj.hide_set(False)
            _exclude_object_from_ao_rays(obj)
            continue
        obj.hide_viewport = not visible
        obj.hide_render = not visible
        if visible:
            obj.hide_set(False)
    _refresh_scene_view_layers(scene)
    return snapshot


def unhide_objects_for_bake(objects: list[bpy.types.Object]) -> dict[str, bool]:
    """Unhide viewport/render for bake targets; return prior hide_viewport by name."""
    prior: dict[str, bool] = {}
    for obj in object_helpers.filter_valid_objects(objects):
        prior[obj.name] = obj.hide_viewport
    make_objects_visible_for_bake(objects)
    return prior


def ensure_objects_in_active_view_layer(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    objects: list[bpy.types.Object],
) -> None:
    """Link objects into the active view layer when collection exclude blocked them."""
    view_layer = context.view_layer
    live = object_helpers.filter_valid_objects(objects)
    if not live:
        return

    missing = [
        obj for obj in live
        if obj.name not in _object_names_in_view_layer(view_layer)
    ]
    if not missing:
        return

    collections_to_enable: set[bpy.types.Collection] = set()
    for obj in missing:
        collections_to_enable.update(obj.users_collection)
        parent = obj.parent
        while parent is not None:
            collections_to_enable.update(parent.users_collection)
            parent = parent.parent

    if collections_to_enable:
        enable_collections_in_view_layer(context, list(collections_to_enable))

    view_layer.update()
    still_missing = [
        obj for obj in missing
        if obj.name not in _object_names_in_view_layer(view_layer)
    ]
    if not still_missing:
        return

    root_coll = scene.collection
    for obj in still_missing:
        if obj.name not in root_coll.objects:
            root_coll.objects.link(obj)
    view_layer.update()


@contextmanager
def temporary_bake_view_layer_access(
    context: bpy.types.Context,
    collections: list[bpy.types.Collection],
    objects: list[bpy.types.Object],
):
    """
    Un-exclude bake collections and ensure objects are selectable for bake/export.

    Restores prior exclude/hide state on exit (including errors).
    """
    snapshot = ensure_bake_project_visible(context, collections, objects)
    try:
        yield
    finally:
        restore_bake_visibility(context, snapshot)


@contextmanager
def temporary_bake_project_visibility(
    context: bpy.types.Context,
    collections: list[bpy.types.Collection],
    project_objects: list[bpy.types.Object],
    *,
    bake_targets: list[bpy.types.Object] | None = None,
):
    """Ensure bake project visibility for a full bake; restore on exit (including errors)."""
    snapshot = ensure_bake_project_visible(
        context,
        collections,
        project_objects,
        bake_targets=bake_targets,
    )
    try:
        yield snapshot
    finally:
        restore_bake_visibility(context, snapshot)

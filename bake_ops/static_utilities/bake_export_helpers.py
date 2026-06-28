"""Generic FBX export helpers for scoped object sets (no bake-domain imports)."""

from __future__ import annotations

from pathlib import Path

import bpy

from lks_baker.shared_utilities import object_helpers
from lks_baker.shared_utilities.filepath_helpers import get_abspath_from_relpath
from lks_baker.shared_utilities.lks_constants import (
    BAKE_PREP_COLLECTION_STEM,
    LKS_BAKE_EXPORT_TEMP_KEY,
    is_bake_prep_collection_name,
)

_EXPORT_SCENE_PREFIX = '_LKS_BakeFbxExport'


def _skip_export_mirror_collection(
    name: str,
    skip_collection_names: frozenset[str],
) -> bool:
    if name in skip_collection_names:
        return True
    return (
        BAKE_PREP_COLLECTION_STEM in skip_collection_names
        and is_bake_prep_collection_name(name)
    )


def ensure_export_directory(output_dir: str) -> Path:
    """Resolve Blender-relative output_dir and create the folder if needed."""
    abs_path = get_abspath_from_relpath(output_dir)
    abs_path.mkdir(parents=True, exist_ok=True)
    return abs_path


def checkout_export_filepath(filepath: Path) -> None:
    """Perforce checkout when available; otherwise ensure parent exists."""
    checkout = getattr(bpy.ops.scene, 'checkout_file', None)
    if checkout is not None:
        checkout(file=str(filepath.resolve()))
        return
    filepath.parent.mkdir(parents=True, exist_ok=True)


def tag_bake_export_temp_object(obj: bpy.types.Object) -> None:
    """Mark an object as temporary bake FBX export geometry."""
    obj[LKS_BAKE_EXPORT_TEMP_KEY] = True


def count_bake_export_temp_objects() -> int:
    """Count tagged export empties / mesh duplicates still in the file."""
    return sum(
        1 for obj in bpy.data.objects
        if obj.get(LKS_BAKE_EXPORT_TEMP_KEY)
    )


def cleanup_bake_export_temp_objects(
    objects: list[bpy.types.Object],
) -> int:
    """Remove tagged export empties and mesh duplicates; preserve sources."""
    removed = 0
    for obj in list(objects):
        if obj.name not in bpy.data.objects:
            continue
        if not obj.get(LKS_BAKE_EXPORT_TEMP_KEY):
            continue
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
    return removed


def mirror_child_collections_as_export_empties(
    source_coll: bpy.types.Collection,
    parent_empty: bpy.types.Object,
    scene_coll: bpy.types.Collection,
    *,
    skip_collection_names: frozenset[str] = frozenset(),
) -> dict[int, bpy.types.Object]:
    """Mirror nested child collections as origin empties; map includes ``source_coll``."""
    coll_to_empty: dict[int, bpy.types.Object] = {id(source_coll): parent_empty}

    def walk_children(
        parent_collection: bpy.types.Collection,
        parent_node: bpy.types.Object,
    ) -> None:
        for child_coll in parent_collection.children:
            if _skip_export_mirror_collection(child_coll.name, skip_collection_names):
                continue
            child_empty = create_export_empty(
                child_coll.name,
                scene_coll,
                parent=parent_node,
            )
            coll_to_empty[id(child_coll)] = child_empty
            walk_children(child_coll, child_empty)

    walk_children(source_coll, parent_empty)
    return coll_to_empty


def find_deepest_collection_for_object(
    root_coll: bpy.types.Collection,
    obj: bpy.types.Object,
    *,
    skip_collection_names: frozenset[str] = frozenset(),
) -> bpy.types.Collection:
    """Deepest collection in ``root_coll`` subtree that directly links ``obj``."""
    best: bpy.types.Collection | None = None
    best_depth = -1

    def walk(coll: bpy.types.Collection, depth: int) -> None:
        nonlocal best, best_depth
        if _skip_export_mirror_collection(coll.name, skip_collection_names):
            return
        if obj.name in coll.objects:
            if depth > best_depth:
                best = coll
                best_depth = depth
        for child_coll in coll.children:
            walk(child_coll, depth + 1)

    walk(root_coll, 0)
    return best if best is not None else root_coll


def empty_is_descendant_of_any(
    empty: bpy.types.Object,
    ancestors: list[bpy.types.Object],
) -> bool:
    """True when ``empty`` is a descendant of (or equal to) any object in ``ancestors``."""
    ancestor_ids = {id(obj) for obj in ancestors}
    current: bpy.types.Object | None = empty
    while current is not None:
        if id(current) in ancestor_ids:
            return True
        current = current.parent
    return False


def create_export_empty(
    name: str,
    collection: bpy.types.Collection,
    *,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    """Create an empty linked to collection, optionally parented."""
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_size = 0.1
    tag_bake_export_temp_object(empty)
    collection.objects.link(empty)
    if parent is not None:
        empty.parent = parent
        empty.matrix_basis.identity()
    else:
        empty.matrix_world.identity()
    return empty


def duplicate_mesh_for_export(
    context: bpy.types.Context,
    source: bpy.types.Object,
    collection: bpy.types.Collection,
    *,
    parent: bpy.types.Object | None = None,
    name: str | None = None,
) -> bpy.types.Object:
    """Evaluated mesh duplicate for FBX export; does not modify source."""
    dupe = object_helpers.duplicate_via_depsgraph(source, context=context)
    if name is not None:
        dupe.name = name
    tag_bake_export_temp_object(dupe)
    collection.objects.link(dupe)
    world_matrix = dupe.matrix_world.copy()
    if parent is not None:
        dupe.parent = parent
        dupe.matrix_world = world_matrix
    return dupe


def select_objects_for_export(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
) -> bpy.types.Object | None:
    """Deselect all, select export objects, set active."""
    context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    selected: list[bpy.types.Object] = []
    view_layer_objects = {
        obj.name for obj in context.view_layer.objects if obj is not None
    }
    for obj in objects:
        if not object_helpers.is_object_alive(obj):
            continue
        if obj.name not in view_layer_objects:
            context.scene.collection.objects.link(obj)
            context.view_layer.update()
            view_layer_objects.add(obj.name)
        obj.select_set(True)
        if obj.select_get():
            selected.append(obj)
    if not selected:
        return None
    active = selected[0]
    context.view_layer.objects.active = active
    return active


def export_fbx_selection(
    context: bpy.types.Context,
    filepath: Path,
    objects: list[bpy.types.Object],
    *,
    include_empties: bool = False,
    export_all_scene_objects: bool = False,
) -> None:
    """Export via FBX.

    When ``export_all_scene_objects`` is True, export the whole active scene
    (caller must use an isolated export scene). Otherwise export ``objects``
    via ``use_selection``.
    """
    object_types = {'MESH', 'EMPTY'} if include_empties else {'MESH'}
    checkout_export_filepath(filepath)

    if export_all_scene_objects:
        context.view_layer.update()
        bpy.ops.object.select_all(action='DESELECT')
        use_selection = False
    else:
        if not select_objects_for_export(context, objects):
            raise RuntimeError('No export objects to write FBX')
        use_selection = True

    bpy.ops.export_scene.fbx(
        filepath=str(filepath),
        check_existing=False,
        use_selection=use_selection,
        use_active_collection=False,
        global_scale=1.0,
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_NONE',
        use_space_transform=True,
        bake_space_transform=False,
        object_types=object_types,
        use_mesh_modifiers=True,
        use_mesh_modifiers_render=True,
        mesh_smooth_type='FACE',
        use_subsurf=False,
        use_mesh_edges=False,
        use_tspace=True,
        path_mode='AUTO',
        axis_forward='-Z',
        axis_up='Y',
    )


def create_isolated_export_scene(scene_name: str) -> bpy.types.Scene:
    """Fresh scene for temporary export hierarchies."""
    if scene_name in bpy.data.scenes:
        remove_export_scene(bpy.data.scenes[scene_name])
    return bpy.data.scenes.new(scene_name)


def remove_export_scene(scene: bpy.types.Scene) -> None:
    """Delete all objects in scene, then remove the scene datablock."""
    if scene.name not in bpy.data.scenes:
        return
    for obj in list(scene.objects):
        if object_helpers.is_object_alive(obj):
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.scenes.remove(scene)


def export_scene_name(stem: str) -> str:
    """Deterministic temp export scene name from a stem."""
    safe = stem.replace(' ', '_')
    return f'{_EXPORT_SCENE_PREFIX}_{safe}'

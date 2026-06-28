"""Generic leaf-to-root hierarchy flatten (Group Pro export pipeline)."""

from __future__ import annotations

from typing import Iterable

import bpy

from . import mesh_helpers, object_helpers
from .collection_instance_helpers import bake_colinst_objects_in_subtrees
from .deep_apply_debug import log as _deep_apply_log
from .grouppro_helpers import (
    GPRO_ADDON_MODULE,
    destructively_dissolve_grouppro_mesh_group_and_retrieve_meshes,
    get_exportable_grouppro_groups,
    is_exportable_grouppro_group,
    is_grouppro_mesh_group,
    is_grouppro_placeholder_object,
    is_legacy_grouppro_collection_instance,
    make_grouppro_groups_unique_manual,
)
from .geonodes_instance_helpers import dissolve_geonodes_collection_instances_in_objects


def _objects_in_filter(
    objects: Iterable[bpy.types.Object],
    object_filter: set[str] | None,
) -> list[bpy.types.Object]:
    if object_filter is None:
        return list(objects)
    return [obj for obj in objects if obj.name in object_filter]


def _grouppro_addon_available() -> bool:
    return bpy.context.preferences.addons.get(GPRO_ADDON_MODULE) is not None


def _make_grouppro_groups_unique(
    context: bpy.types.Context,
    group_objects: list[bpy.types.Object],
) -> bool:
    mesh_groups = [obj for obj in group_objects if is_grouppro_mesh_group(obj)]
    if not mesh_groups:
        return True

    if not hasattr(bpy.ops.object, 'gpro_makeunique'):
        return False

    bpy.ops.object.select_all(action='DESELECT')
    for obj in mesh_groups:
        obj.select_set(True)
    context.view_layer.objects.active = mesh_groups[0]

    bpy.ops.object.gpro_makeunique(
        maxDepth=0,
        makeDataUnique=True,
        makeMaterialsUnique=False,
    )
    context.view_layer.update()
    return True


def _instance_collection_needs_unique(obj: bpy.types.Object) -> bool:
    coll = obj.instance_collection
    if coll is None:
        return False
    instance_users = sum(
        1 for scene_obj in bpy.data.objects
        if scene_obj.instance_collection == coll
    )
    return instance_users > 1


def _make_collection_instances_unique_in_scene(
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
) -> None:
    """Isolate shared collection instance data (mirrors export-scene duplication)."""
    while True:
        to_unique = [
            obj for obj in _objects_in_filter(scene.objects, object_filter)
            if _instance_collection_needs_unique(obj)
        ]
        if not to_unique:
            break
        for obj in to_unique:
            for coll in list(obj.users_collection):
                object_helpers.make_collection_instance_hierarchy_unique_recursively(
                    obj,
                    coll,
                )


def _scene_subtree(root: bpy.types.Object) -> list[bpy.types.Object]:
    """Root plus all scene-graph descendants (``Object.children``)."""
    subtree: list[bpy.types.Object] = []
    stack = [root]
    while stack:
        obj = stack.pop()
        subtree.append(obj)
        stack.extend(obj.children)
    return subtree


def duplicate_objects_for_hierarchy_flatten(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    target_collection: bpy.types.Collection,
    *,
    preserve_modifiers: bool = False,
) -> list[bpy.types.Object]:
    """
    Duplicate forest roots for flatten prep — mirrors export-scene duplication.

    GP mesh groups: shallow object copy (dissolve expands internals).
    Collection instances: copy + unique instance hierarchy.
    Meshes with data (standalone): depsgraph-evaluated mesh duplicate, unless
    ``preserve_modifiers`` keeps the modifier stack for downstream UV unstack.
    Parented scene hierarchies: duplicate root subtree preserving parenting.
    Other empties: shallow copy.
    """
    valid = object_helpers.filter_valid_objects(objects)
    if not valid:
        _deep_apply_log(
            'duplicate_objects_for_hierarchy_flatten: no valid input objects',
            stage='no_dupes',
        )
        return []

    roots = object_helpers.collect_hierarchy_forest_roots(valid)
    dupes: list[bpy.types.Object] = []

    def link_to_target(dupe: bpy.types.Object) -> None:
        for coll in list(dupe.users_collection):
            coll.objects.unlink(dupe)
        if dupe.name not in target_collection.objects:
            target_collection.objects.link(dupe)

    def duplicate_subtree_root(root: bpy.types.Object) -> list[bpy.types.Object]:
        """Shallow-copy subtree without mutating source collection membership."""
        subtree = _scene_subtree(root)
        id_map: dict[int, bpy.types.Object] = {}
        new_dupes: list[bpy.types.Object] = []

        for member in subtree:
            dupe = member.copy()
            id_map[id(member)] = dupe
            link_to_target(dupe)
            new_dupes.append(dupe)

        for member in subtree:
            dupe = id_map[id(member)]
            src_parent = member.parent
            if src_parent is not None and id(src_parent) in id_map:
                dupe.parent = id_map[id(src_parent)]
            else:
                dupe.parent = src_parent
            dupe.matrix_local = member.matrix_local.copy()

        return new_dupes

    for obj in roots:
        if is_grouppro_mesh_group(obj):
            if obj.children:
                dupes.extend(duplicate_subtree_root(obj))
            else:
                dupe = obj.copy()
                link_to_target(dupe)
                dupes.append(dupe)
            continue

        if is_legacy_grouppro_collection_instance(obj):
            if obj.children:
                dupes.extend(duplicate_subtree_root(obj))
            else:
                dupe = obj.copy()
                link_to_target(dupe)
                dupes.append(dupe)
            continue

        if obj.instance_collection is not None:
            dupe = obj.copy()
            link_to_target(dupe)
            object_helpers.make_collection_instance_hierarchy_unique_recursively(
                dupe,
                target_collection,
            )
            dupes.append(dupe)
            continue

        if obj.children:
            dupes.extend(duplicate_subtree_root(obj))
            continue

        if obj.data is not None:
            if preserve_modifiers:
                dupe = obj.copy()
            else:
                dupe = object_helpers.duplicate_via_depsgraph(obj, context=context)
        else:
            dupe = obj.copy()

        link_to_target(dupe)
        dupes.append(dupe)

    if dupes:
        context.view_layer.update()
    return dupes


def _hierarchy_needs_transform_cook(root_obj: bpy.types.Object) -> bool:
    meshes = object_helpers.collect_all_meshes_in_hierarchy(root_obj)
    if not meshes:
        return False
    if root_obj.parent is not None:
        return True
    if len(meshes) > 1:
        return True
    if root_obj.children:
        return True
    return any(mesh.parent is not None for mesh in meshes)


def _is_single_parented_mesh_root(root_obj: bpy.types.Object) -> bool:
    """True when root is one mesh leaf/parentless-in-subtree node with scene parents."""
    if root_obj.type != 'MESH' or not root_obj.children:
        meshes = object_helpers.collect_all_meshes_in_hierarchy(root_obj)
        return len(meshes) == 1 and meshes[0] is root_obj
    return False


def _dissolve_grouppro_roots(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
) -> None:
    while True:
        candidates = [
            obj for obj in _objects_in_filter(scene.objects, object_filter)
            if is_exportable_grouppro_group(obj)
        ]
        if not candidates:
            break
        for group_obj in candidates:
            if group_obj.name not in bpy.data.objects:
                continue
            if is_grouppro_mesh_group(group_obj):
                destructively_dissolve_grouppro_mesh_group_and_retrieve_meshes(group_obj)
            elif is_legacy_grouppro_collection_instance(group_obj):
                object_helpers.destructively_dissolve_instance_collection_and_retrieve_meshes(
                    group_obj,
                )
        context.view_layer.update()


def _dissolve_instance_collections_in_scene(
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
) -> None:
    while True:
        instance_roots = [
            obj for obj in _objects_in_filter(scene.objects, object_filter)
            if obj.instance_collection is not None
        ]
        if not instance_roots:
            break
        for instance_root in instance_roots:
            object_helpers.destructively_dissolve_instance_collection_and_retrieve_meshes(
                instance_root,
            )


def _cook_remaining_hierarchies(
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
) -> None:
    candidates = _objects_in_filter(scene.objects, object_filter)
    forest_roots = object_helpers.collect_hierarchy_forest_roots(candidates)
    for root in forest_roots:
        if root.name not in bpy.data.objects:
            continue
        if not _hierarchy_needs_transform_cook(root):
            continue
        if _is_single_parented_mesh_root(root):
            object_helpers.cook_parented_mesh_to_world(root)
            continue
        object_helpers.destructively_retrieve_meshes_from_hierarchy(root)


def _remove_empties_in_scene(
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
) -> None:
    for obj in _objects_in_filter(scene.objects, object_filter):
        if obj.type == 'EMPTY':
            object_helpers.remove_object(obj)


def remove_grouppro_placeholder_objects(
    objects: Iterable[bpy.types.Object],
    *,
    object_filter: set[str] | None = None,
) -> None:
    for obj in list(objects):
        if object_filter is not None and obj.name not in object_filter:
            continue
        if is_grouppro_placeholder_object(obj):
            object_helpers.remove_object(obj)


def flatten_hierarchy_to_world_meshes(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
    apply_modifiers: bool = True,
) -> list[bpy.types.Object]:
    """
    Generic leaf-to-root flatten. Returns parentless world-space meshes matching
    viewport WYSIWYG (no instancing, no parent transforms, modifiers applied).

    Step order (matches ``OBJECT_OT_LKS_ExportFBXFromGroupProGroup`` dissolve path):

    1. Make Group Pro mesh groups unique (``gpro_makeunique``).
    2. Make collection instance hierarchies unique (per instance root).
    3. Dissolve Group Pro mesh groups (decompose + leaf-to-root transform cook).
    4. Dissolve collection instances (decompose + leaf-to-root transform cook).
    5. Leaf-to-root transform cook on remaining parented mesh hierarchies.
    6. Remove empties and Group Pro placeholder shells.
    7. Apply remaining modifiers on each result mesh (when ``apply_modifiers``).
    """
    candidates = _objects_in_filter(scene.objects, object_filter)
    group_objects = get_exportable_grouppro_groups(candidates)

    if group_objects:
        mesh_groups = [obj for obj in group_objects if is_grouppro_mesh_group(obj)]
        if mesh_groups:
            if _grouppro_addon_available():
                if not _make_grouppro_groups_unique(context, group_objects):
                    raise RuntimeError(
                        'Group Pro make-unique operator is unavailable; '
                        'cannot isolate prep data.',
                    )
            else:
                forest_roots = object_helpers.collect_hierarchy_forest_roots(candidates)
                unique_count = make_grouppro_groups_unique_manual(forest_roots)
                _deep_apply_log(
                    f'manual GP uniquify: {unique_count} group(s)',
                    stage='gp_unique_manual',
                )

    _make_collection_instances_unique_in_scene(scene, object_filter=object_filter)

    colinst_candidates = _objects_in_filter(scene.objects, object_filter)
    if colinst_candidates:
        colinst_roots = object_helpers.collect_hierarchy_forest_roots(
            colinst_candidates,
        )
        if colinst_roots:
            bake_colinst_objects_in_subtrees(context, colinst_roots)
            context.view_layer.update()

    _dissolve_grouppro_roots(context, scene, object_filter=object_filter)
    dissolve_geonodes_collection_instances_in_objects(
        context,
        _objects_in_filter(scene.objects, object_filter),
    )
    _dissolve_instance_collections_in_scene(scene, object_filter=object_filter)
    _cook_remaining_hierarchies(scene, object_filter=object_filter)
    _remove_empties_in_scene(scene, object_filter=object_filter)
    remove_grouppro_placeholder_objects(list(scene.objects), object_filter=object_filter)

    meshes = object_helpers.filter_mesh_objects(scene.objects)
    if object_filter is not None:
        meshes = [obj for obj in meshes if obj.name in object_filter]
    meshes = [obj for obj in meshes if not is_grouppro_placeholder_object(obj)]

    if apply_modifiers:
        for obj in list(meshes):
            if obj.name not in bpy.data.objects:
                continue
            mesh_helpers.apply_visible_modifiers_delete_hidden(context, obj)

        meshes = object_helpers.filter_mesh_objects(scene.objects)
        if object_filter is not None:
            meshes = [obj for obj in meshes if obj.name in object_filter]
        meshes = [obj for obj in meshes if not is_grouppro_placeholder_object(obj)]

    for obj in list(meshes):
        if obj.name not in bpy.data.objects or obj.type != 'MESH':
            continue
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        object_helpers.bake_matrix_local_into_mesh_data(obj)

    return meshes

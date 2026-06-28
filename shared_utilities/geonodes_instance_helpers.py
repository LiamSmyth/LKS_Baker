"""Detect and bake geometry-nodes collection instance modifiers to object hierarchies."""

from __future__ import annotations

import bpy
from mathutils import Matrix

from .geonodes_modifier_helpers import get_nodes_modifier_input
from .grouppro_helpers import (
    destructively_dissolve_grouppro_mesh_group_and_retrieve_meshes,
    is_grouppro_mesh_group,
)
from .transform_apply_helpers import smart_transform_mesh_data


def _modifier_collection_input(
    modifier: bpy.types.Modifier,
) -> bpy.types.Collection | None:
    if modifier.type != 'NODES' or modifier.node_group is None:
        return None

    for item in modifier.node_group.interface.items_tree:
        if item.item_type != 'SOCKET' or item.in_out != 'INPUT':
            continue
        if item.socket_type != 'NodeSocketCollection':
            continue
        value = get_nodes_modifier_input(modifier, item.identifier)
        if isinstance(value, bpy.types.Collection):
            return value
    return None


def is_geonodes_collection_instance_mesh(obj: bpy.types.Object | None) -> bool:
    """True when ``obj`` instances a collection via a geometry-nodes modifier."""
    if obj is None or obj.type != 'MESH':
        return False
    if is_grouppro_mesh_group(obj):
        return True
    return any(
        _modifier_collection_input(mod) is not None
        for mod in obj.modifiers
        if mod.type == 'NODES'
    )


def _link_object(obj: bpy.types.Object, collections: list[bpy.types.Collection]) -> None:
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    for coll in collections:
        if obj.name not in coll.objects:
            coll.objects.link(obj)


def _target_collections(
    obj: bpy.types.Object,
    *,
    fallback: bpy.types.Collection,
) -> list[bpy.types.Collection]:
    colls = list(obj.users_collection)
    return colls if colls else [fallback]


def _extract_evaluated_mesh_instances(
    source_obj: bpy.types.Object,
) -> list[bpy.types.Object]:
    """Realize depsgraph mesh instances parented under ``source_obj``."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    target_collections = _target_collections(
        source_obj,
        fallback=bpy.context.scene.collection,
    )
    results: list[bpy.types.Object] = []

    for inst in depsgraph.object_instances:
        if inst.parent is None or inst.parent.original != source_obj:
            continue
        eval_obj = inst.object
        original = eval_obj.original
        if eval_obj.type != 'MESH' or original is None:
            continue
        try:
            eval_mesh = eval_obj.to_mesh()
            if eval_mesh is None or not eval_mesh.vertices:
                continue
            mesh = bpy.data.meshes.new_from_object(eval_obj)
        except RuntimeError:
            continue
        finally:
            eval_obj.to_mesh_clear()
        if not mesh.vertices:
            bpy.data.meshes.remove(mesh)
            continue
        smart_transform_mesh_data(mesh, eval_obj.matrix_world.copy())
        leaf = bpy.data.objects.new(original.name, mesh)
        leaf.matrix_world = Matrix.Identity(4)
        _link_object(leaf, target_collections)
        results.append(leaf)

    return results


def bake_geonodes_collection_instance_to_hierarchy(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    parent_empty: bpy.types.Object | None = None,
) -> bpy.types.Object | list[bpy.types.Object]:
    """
    Replace geo-nodes collection instancing on ``obj`` with real objects.

    Group Pro mesh groups delegate to the GP dissolve path. Other collection
    instance modifiers are realized via depsgraph extraction under a new empty.
    """
    if not is_geonodes_collection_instance_mesh(obj):
        return obj

    if is_grouppro_mesh_group(obj):
        meshes = destructively_dissolve_grouppro_mesh_group_and_retrieve_meshes(obj)
        if parent_empty is not None:
            for mesh in meshes:
                mesh.parent = parent_empty
        return meshes

    target_collections = _target_collections(
        obj,
        fallback=context.scene.collection,
    )
    ci_parent = parent_empty if parent_empty is not None else obj.parent
    ci_matrix = obj.matrix_world.copy()
    ci_name = obj.name

    root_empty = bpy.data.objects.new(f'{ci_name}_decomposed', None)
    _link_object(root_empty, target_collections)
    root_empty.parent = ci_parent
    root_empty.matrix_world = ci_matrix

    leaves = _extract_evaluated_mesh_instances(obj)
    for index, leaf in enumerate(leaves):
        leaf.parent = root_empty
        leaf.name = f'{leaf.name}.{index:03d}' if len(leaves) > 1 else leaf.name

    if obj.name in bpy.data.objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    context.view_layer.update()
    return root_empty


def find_geonodes_collection_instance_meshes(
    objects: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    """Forest-root geo-nodes collection instance meshes in ``objects``."""
    from . import object_helpers

    instances = [obj for obj in objects if is_geonodes_collection_instance_mesh(obj)]
    return object_helpers.collect_hierarchy_forest_roots(instances)


def dissolve_geonodes_collection_instances_in_objects(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
) -> int:
    """Iteratively bake every geo-nodes collection instance mesh in ``objects``."""
    dissolved = 0
    pending_names = {obj.name for obj in objects}
    while pending_names:
        live_objects = [
            bpy.data.objects[name]
            for name in list(pending_names)
            if name in bpy.data.objects
        ]
        pending_names = {obj.name for obj in live_objects}
        candidates = find_geonodes_collection_instance_meshes(live_objects)
        if not candidates:
            break
        dissolved_this_pass = 0
        for obj in candidates:
            if obj.name not in bpy.data.objects:
                continue
            if not is_geonodes_collection_instance_mesh(obj):
                continue
            # Forest-root GP: leave for depsgraph worldspace extract (dissolve drifts).
            if is_grouppro_mesh_group(obj) and obj.parent is None:
                continue
            bake_geonodes_collection_instance_to_hierarchy(context, obj)
            dissolved += 1
            dissolved_this_pass += 1
        if dissolved_this_pass == 0:
            break
        context.view_layer.update()
    return dissolved

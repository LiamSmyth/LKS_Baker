"""Breadth-first in-place dissolve of collection / Group Pro instances."""

from __future__ import annotations

from dataclasses import dataclass, field

import bpy
from mathutils import Matrix

from . import object_helpers
from .deep_apply_debug import log as _colinst_log
from .grouppro_helpers import (
    get_grouppro_collection,
    is_grouppro_mesh_group,
    is_grouppro_placeholder_object,
)
from .lks_constants import GPRO_INSTANCE_MOD


@dataclass(frozen=True)
class ColinstExtractResult:
    """Outcome of dissolving collection / GP instances in selected subtrees."""

    extracted_count: int = 0
    dissolved_count: int = 0
    root_objects: list[bpy.types.Object] = field(default_factory=list)


def _dbg(message: str) -> None:
    _colinst_log(message, stage='colinst')


def _unique_object_name(base_name: str) -> str:
    if base_name not in bpy.data.objects:
        return base_name
    index = 1
    while f'{base_name}.{index:03d}' in bpy.data.objects:
        index += 1
    return f'{base_name}.{index:03d}'


def _target_collections(
    obj: bpy.types.Object,
    *,
    fallback: bpy.types.Collection,
) -> list[bpy.types.Collection]:
    colls = list(obj.users_collection)
    if colls:
        return colls
    return [fallback]


def _link_to_collections(
    obj: bpy.types.Object,
    collections: list[bpy.types.Collection],
) -> None:
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    for coll in collections:
        if obj.name not in coll.objects:
            coll.objects.link(obj)


def _copy_object_transform(target: bpy.types.Object, source: bpy.types.Object) -> None:
    target.matrix_basis = source.matrix_basis.copy()


def _uniquify_object_data(obj: bpy.types.Object) -> None:
    if obj.data is None:
        return
    if hasattr(obj.data, 'users') and obj.data.users > 1:
        obj.data = obj.data.copy()
        _dbg(f'  uniquified data on {obj.name!r}')


def _is_collection_instance(obj: bpy.types.Object) -> bool:
    return (
        obj.instance_collection is not None
        and getattr(obj, 'instance_type', None) == 'COLLECTION'
    )


def _get_instanced_collection(obj: bpy.types.Object) -> bpy.types.Collection | None:
    if _is_collection_instance(obj):
        return obj.instance_collection
    if is_grouppro_mesh_group(obj):
        return get_grouppro_collection(obj)
    return None


def _instance_kind(obj: bpy.types.Object) -> str:
    if _is_collection_instance(obj):
        return 'collection_instance'
    if is_grouppro_mesh_group(obj):
        return 'grouppro_instance'
    return 'plain'


def _duplicate_collection_member(member: bpy.types.Object) -> bpy.types.Object | None:
    if is_grouppro_placeholder_object(member) and not is_grouppro_mesh_group(member):
        _dbg(f'  skip placeholder member {member.name!r}')
        return None
    if is_grouppro_mesh_group(member):
        _dbg(f'  copy GP instance member {member.name!r}')
        return member.copy()
    if _is_collection_instance(member):
        _dbg(f'  copy nested CI member {member.name!r}')
        return member.copy()
    if member.type == 'MESH' and member.data is not None:
        dupe = member.copy()
        dupe.data = member.data.copy()
        _dbg(f'  copy mesh member {member.name!r}')
        return dupe
    if member.data is not None:
        dupe = member.copy()
        dupe.data = member.data.copy()
        _dbg(f'  copy data member {member.name!r} ({member.type})')
        return dupe
    if member.type == 'EMPTY':
        dupe = member.copy()
        dupe.instance_collection = None
        dupe.instance_type = 'NONE'
        _dbg(f'  copy empty member {member.name!r}')
        return dupe
    _dbg(f'  copy member {member.name!r} ({member.type})')
    return member.copy()


def _member_matrix_world(
    member: bpy.types.Object,
    member_set: set[bpy.types.Object],
    instance_matrix: Matrix,
) -> Matrix:
    """World matrix for a collection member under an instance shell."""
    if member.parent is not None and member.parent in member_set:
        parent_world = _member_matrix_world(
            member.parent, member_set, instance_matrix,
        )
        return parent_world @ member.matrix_basis.copy()
    return instance_matrix @ member.matrix_basis.copy()


def _add_collection_members_under(
    parent_obj: bpy.types.Object,
    collection: bpy.types.Collection,
    collections: list[bpy.types.Collection],
) -> int:
    members = list(collection.objects)
    member_set = set(members)
    member_map: dict[bpy.types.Object, bpy.types.Object] = {}
    added = 0
    instance_matrix = parent_obj.matrix_world.copy()

    _dbg(f'  add members from {collection.name!r} ({len(members)} member(s))')

    for member in members:
        child = _duplicate_collection_member(member)
        if child is None:
            continue
        child.name = _unique_object_name(member.name)
        _uniquify_object_data(child)
        _link_to_collections(child, collections)
        member_map[member] = child
        added += 1

    for member in members:
        if member not in member_map:
            continue
        child = member_map[member]
        if member.parent is not None and member.parent in member_map:
            child.parent = member_map[member.parent]
            _copy_object_transform(child, member)
            _dbg(f'  child {child.name!r} parented under in-collection parent')
        else:
            child.parent = parent_obj
            child.matrix_world = _member_matrix_world(
                member, member_set, instance_matrix,
            )
            _dbg(f'  child {child.name!r} parented under {parent_obj.name!r}')

    _dbg(f'  added {added} child object(s) under {parent_obj.name!r}')
    return added


def _finalize_instance(obj: bpy.types.Object) -> None:
    if is_grouppro_mesh_group(obj):
        group_mod = obj.modifiers.get(GPRO_INSTANCE_MOD)
        if group_mod is not None:
            obj.modifiers.remove(group_mod)
            _dbg(f'  removed {GPRO_INSTANCE_MOD!r} from {obj.name!r}')
        return

    if _is_collection_instance(obj):
        obj.instance_collection = None
        obj.instance_type = 'NONE'
        _dbg(f'  cleared collection instance on {obj.name!r} (now plain empty)')
        return

    _dbg(f'  finalize skipped {obj.name!r} (not an instance)')


def _dissolve_instance_in_place(
    obj: bpy.types.Object,
    collections: list[bpy.types.Collection],
) -> None:
    coll = _get_instanced_collection(obj)
    if coll is None:
        return
    _dbg(f'DISSOLVE {_instance_kind(obj)}: {obj.name!r}')
    _add_collection_members_under(obj, coll, collections)
    _finalize_instance(obj)


def _collect_child_names(obj: bpy.types.Object) -> list[str]:
    return [child.name for child in list(obj.children)]


def dissolve_subtree(
    context: bpy.types.Context,
    root: bpy.types.Object,
) -> tuple[bpy.types.Object, int]:
    """
    Breadth-first in-place dissolve under ``root``.

    Original instance objects are preserved; collection members are copied as
    real children, then instances are finalized (GP modifier removed or CI
    flags cleared). Returns ``(root, dissolved_instance_count)``.
    """
    scene = context.scene
    collections = _target_collections(root, fallback=scene.collection)
    current_level = [root.name]
    depth = 0
    dissolved_count = 0

    _dbg(f'=== begin subtree {root.name!r} ===')

    while current_level:
        current_level = list(dict.fromkeys(current_level))
        _dbg(f'--- depth {depth}: {len(current_level)} object(s) ---')
        next_level: list[str] = []

        for obj_name in current_level:
            obj = bpy.data.objects.get(obj_name)
            if obj is None:
                _dbg(f'SKIP missing {obj_name!r}')
                continue

            if _get_instanced_collection(obj) is not None:
                _dissolve_instance_in_place(obj, collections)
                dissolved_count += 1
            else:
                _dbg(f'VISIT plain {obj.name!r} ({obj.type})')

            for child_name in _collect_child_names(obj):
                _dbg(f'  queue child {child_name!r} for depth {depth + 1}')
                if child_name not in next_level:
                    next_level.append(child_name)

        current_level = next_level
        depth += 1

    _dbg(f'=== done subtree {root.name!r} ({depth} depth level(s)) ===')
    context.view_layer.update()
    return root, dissolved_count


def extract_object_hierarchy(
    context: bpy.types.Context,
    source_root: bpy.types.Object,
) -> bpy.types.Object:
    """Alias for :func:`dissolve_subtree` (legacy single-root API)."""
    root, _ = dissolve_subtree(context, source_root)
    return root


def extract_selection_to_hierarchy(
    context: bpy.types.Context,
    sources: list[bpy.types.Object],
) -> ColinstExtractResult:
    """Dissolve instances in each forest root subtree of ``sources``."""
    if not sources:
        return ColinstExtractResult()

    roots = object_helpers.collect_hierarchy_forest_roots(sources)
    dissolved_total = 0
    for root in roots:
        _, dissolved_count = dissolve_subtree(context, root)
        dissolved_total += dissolved_count

    context.view_layer.update()
    return ColinstExtractResult(
        extracted_count=len(roots),
        dissolved_count=dissolved_total,
        root_objects=list(roots),
    )

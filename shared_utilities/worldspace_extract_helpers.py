"""Depsgraph one-shot world-space mesh extraction (WYSIWYG viewport evaluated state)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import bpy
from mathutils import Matrix, Vector

from . import object_helpers
from .collection_instance_helpers import is_collection_instance
from .deep_apply_geometry_helpers import resolve_output_collection_for_roots
from .geonodes_instance_helpers import is_geonodes_collection_instance_mesh
from .grouppro_helpers import is_grouppro_mesh_group, is_grouppro_placeholder_object
from .transform_apply_helpers import matrix_has_negative_scale, smart_transform_mesh_data

_EXTRACTED_SUFFIX = '_extracted'
_TANGENT_ATTR_KEYWORDS = frozenset({'tangent', 'bitangent'})


@dataclass(frozen=True)
class WorldspaceExtractResult:
    """Outcome of a deep world-space geometry extraction pass."""

    extracted_objects: tuple[bpy.types.Object, ...]
    source_target_count: int = 0


ExtractTargetKind = Literal['mesh', 'instances']


def _target_collections(
    source_obj: bpy.types.Object,
    *,
    fallback: bpy.types.Collection,
) -> list[bpy.types.Collection]:
    colls = list(source_obj.users_collection)
    return colls if colls else [fallback]


def _link_to_collections(
    obj: bpy.types.Object,
    collections: list[bpy.types.Collection],
) -> None:
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    for coll in collections:
        if obj.name not in coll.objects:
            coll.objects.link(obj)


def _transform_tangent_attributes(mesh: bpy.types.Mesh, matrix: Matrix) -> None:
    """Bake world orientation into stored tangent/bitangent corner vector attributes."""
    linear = matrix.to_3x3()
    flip = matrix_has_negative_scale(matrix)
    for attr in mesh.attributes:
        if attr.data_type != 'FLOAT_VECTOR':
            continue
        name_lower = attr.name.lower()
        if not any(keyword in name_lower for keyword in _TANGENT_ATTR_KEYWORDS):
            continue
        if attr.domain not in {'CORNER', 'FACE_CORNER'}:
            continue
        data = attr.data
        for item in data:
            vec = linear @ Vector(item.vector)
            if flip and 'bitangent' in name_lower:
                vec.negate()
            item.vector = vec


def _mesh_from_evaluated_object(eval_obj: bpy.types.Object) -> bpy.types.Mesh | None:
    try:
        probe = eval_obj.to_mesh()
        if probe is None or not probe.vertices:
            eval_obj.to_mesh_clear()
            return None
        mesh = bpy.data.meshes.new_from_object(eval_obj)
    except RuntimeError:
        return None
    finally:
        eval_obj.to_mesh_clear()
    if not mesh.vertices:
        bpy.data.meshes.remove(mesh)
        return None
    return mesh


def extract_evaluated_mesh_worldspace(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    name: str | None = None,
) -> bpy.types.Object:
    """Extract one evaluated mesh with world positions/normals/tangents baked into data."""
    if obj.type != 'MESH':
        raise ValueError(f"Expected mesh object, got {obj.type!r}")

    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = _mesh_from_evaluated_object(eval_obj)
    if mesh is None:
        raise RuntimeError(f"No evaluated mesh geometry for '{obj.name}'")

    world_matrix = eval_obj.matrix_world.copy()
    smart_transform_mesh_data(mesh, world_matrix)
    _transform_tangent_attributes(mesh, world_matrix)
    mesh.update()

    result_name = name or f'{obj.name}{_EXTRACTED_SUFFIX}'
    result = bpy.data.objects.new(result_name, mesh)
    result.matrix_world = Matrix.Identity(4)
    return result


def extract_evaluated_instances_worldspace(
    context: bpy.types.Context,
    source_obj: bpy.types.Object,
    *,
    filter_eval_vert_count: bool = False,
) -> list[bpy.types.Object]:
    """Realize depsgraph mesh instances parented under ``source_obj`` (GP / CI / geo-nodes)."""
    depsgraph = context.evaluated_depsgraph_get()
    results: list[bpy.types.Object] = []

    for inst in depsgraph.object_instances:
        if inst.parent is None or inst.parent.original != source_obj:
            continue
        eval_obj = inst.object
        original = eval_obj.original
        if eval_obj.type != 'MESH' or original is None:
            continue

        mesh = _mesh_from_evaluated_object(eval_obj)
        if mesh is None:
            continue
        if filter_eval_vert_count and original.data is not None:
            if len(mesh.vertices) != len(original.data.vertices):
                bpy.data.meshes.remove(mesh)
                continue

        world_matrix = eval_obj.matrix_world.copy()
        smart_transform_mesh_data(mesh, world_matrix)
        _transform_tangent_attributes(mesh, world_matrix)
        mesh.update()

        leaf = bpy.data.objects.new(original.name, mesh)
        leaf.matrix_world = Matrix.Identity(4)
        results.append(leaf)

    return results


def collect_worldspace_extract_targets(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
) -> list[tuple[ExtractTargetKind, bpy.types.Object]]:
    """Discover plain meshes and instance roots to extract under ``roots``."""
    _ = context
    seen: set[str] = set()
    targets: list[tuple[ExtractTargetKind, bpy.types.Object]] = []

    for obj in object_helpers.collect_objects_in_subtrees(roots):
        if obj.name in seen:
            continue

        if is_collection_instance(obj):
            targets.append(('instances', obj))
            seen.add(obj.name)
            continue

        if is_grouppro_mesh_group(obj):
            targets.append(('instances', obj))
            seen.add(obj.name)
            continue

        if is_geonodes_collection_instance_mesh(obj):
            targets.append(('instances', obj))
            seen.add(obj.name)
            continue

        if obj.type != 'MESH' or obj.data is None:
            continue
        if is_grouppro_placeholder_object(obj):
            continue

        targets.append(('mesh', obj))
        seen.add(obj.name)

    return targets


def _target_hierarchy_depth(obj: bpy.types.Object) -> int:
    """Parent-chain depth — deepest targets must extract first in-place."""
    depth = 0
    parent = obj.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def _sort_extract_targets_deepest_first(
    targets: list[tuple[ExtractTargetKind, bpy.types.Object]],
) -> list[tuple[ExtractTargetKind, bpy.types.Object]]:
    return sorted(targets, key=lambda item: _target_hierarchy_depth(item[1]), reverse=True)


def _detach_parentless_identity(obj: bpy.types.Object) -> None:
    """Unparent and snap ``matrix_world`` to identity (world mesh expected next)."""
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)


def _uniquify_inplace_mesh_target(obj: bpy.types.Object) -> None:
    """Isolate mesh data before any in-place extract mutation."""
    object_helpers.uniquify_mesh_data_for_inplace_edit(obj)


def _replace_mesh_in_place(
    source: bpy.types.Object,
    extracted: bpy.types.Object,
) -> bpy.types.Object:
    old_mesh = source.data
    new_mesh = extracted.data
    while source.modifiers:
        source.modifiers.remove(source.modifiers[0])
    bpy.data.objects.remove(extracted, do_unlink=True)
    _detach_parentless_identity(source)
    source.data = new_mesh
    if old_mesh is not None and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    return source


def _replace_instance_source(
    source: bpy.types.Object,
    leaves: list[bpy.types.Object],
    collections: list[bpy.types.Collection],
) -> list[bpy.types.Object]:
    for index, leaf in enumerate(leaves):
        if len(leaves) > 1:
            leaf.name = f'{source.name}{_EXTRACTED_SUFFIX}.{index:03d}'
        else:
            leaf.name = f'{source.name}{_EXTRACTED_SUFFIX}'
        _link_to_collections(leaf, collections)

    if source.name in bpy.data.objects:
        bpy.data.objects.remove(source, do_unlink=True)
    return leaves


def deep_extract_worldspace_geometry(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
    *,
    duplicate: bool = True,
) -> WorldspaceExtractResult:
    """Extract evaluated world-space meshes for every target under ``roots``."""
    targets = _sort_extract_targets_deepest_first(
        collect_worldspace_extract_targets(context, roots),
    )
    if not targets:
        return WorldspaceExtractResult(extracted_objects=(), source_target_count=0)

    output_coll = resolve_output_collection_for_roots(context, roots)
    extracted: list[bpy.types.Object] = []

    for kind, source in targets:
        collections = _target_collections(source, fallback=output_coll)

        if kind == 'mesh':
            if not duplicate:
                _uniquify_inplace_mesh_target(source)
            try:
                new_obj = extract_evaluated_mesh_worldspace(context, source)
            except (RuntimeError, ValueError):
                continue
            if duplicate:
                new_obj.name = f'{source.name}{_EXTRACTED_SUFFIX}'
                _link_to_collections(new_obj, collections)
                extracted.append(new_obj)
            else:
                extracted.append(_replace_mesh_in_place(source, new_obj))
            continue

        leaves = extract_evaluated_instances_worldspace(
            context,
            source,
            filter_eval_vert_count=is_grouppro_mesh_group(source),
        )
        if not leaves:
            continue
        if duplicate:
            for index, leaf in enumerate(leaves):
                if len(leaves) > 1:
                    leaf.name = f'{source.name}{_EXTRACTED_SUFFIX}.{index:03d}'
                else:
                    leaf.name = f'{source.name}{_EXTRACTED_SUFFIX}'
                _link_to_collections(leaf, collections)
            extracted.extend(leaves)
        else:
            for leaf in leaves:
                _uniquify_inplace_mesh_target(leaf)
            extracted.extend(_replace_instance_source(source, leaves, collections))

    context.view_layer.update()
    return WorldspaceExtractResult(
        extracted_objects=tuple(extracted),
        source_target_count=len(targets),
    )

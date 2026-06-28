"""Bake-specific geometry prep wrappers (Stage B deep apply)."""

from __future__ import annotations

import bpy

from .static_utilities.bake_merged_lowpoly_helpers import (
    generate_extracted_highpoly_for_roots,
    generate_merged_lowpoly_for_roots,
)
from ..shared_utilities.collection_instance_helpers import is_colinst_object
from ..shared_utilities.deep_apply_geometry_helpers import (
    deep_apply_roots,
    is_flatten_hierarchy_object,
    object_has_flatten_geometry,
)
from ..shared_utilities.grouppro_helpers import is_exportable_grouppro_group, is_grouppro_placeholder_object
from ..shared_utilities import object_helpers
from .helpers_bake_cleanup import (
    ensure_bake_project_prep_collection,
    ensure_child_collection,
    get_bake_group_role_collection,
    get_high_collections,
    get_low_collections,
    is_bake_high_pipeline_artifact,
    is_bake_low_pipeline_artifact,
    iter_bake_group_high_objects,
    iter_bake_group_low_objects,
)
from ..shared_utilities.lks_constants import (
    BAKE_PREP_COLLECTION_STEM,
    is_bake_prep_collection_name,
)


def bake_group_low_has_flatten_geometry(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bool:
    """True when low role containers hold at least one flattenable hierarchy."""
    objects = get_bake_group_low_meshes(project, group)
    if not objects:
        return False
    return any(object_has_flatten_geometry(root) for root in objects)


def bake_group_high_has_flatten_geometry(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bool:
    """True when high role containers hold at least one flattenable hierarchy."""
    objects = get_bake_group_high_meshes(project, group)
    if not objects:
        return False
    return any(object_has_flatten_geometry(root) for root in objects)


def _iter_bake_group_low_merge_sources(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Low-role collection objects plus any legacy ``low_root`` subtree."""
    objects = list(iter_bake_group_low_objects(project, group))
    seen = {obj.name for obj in objects}
    low_root = group.low_root
    if low_root is not None and object_helpers.is_object_alive(low_root):
        stack = [low_root]
        while stack:
            obj = stack.pop()
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
            stack.extend(obj.children)
    return objects


def _iter_low_collection_linked_objects(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Objects directly linked in low role collections (nested, excluding _BAKE_PREP)."""
    seen: set[str] = set()
    linked: list[bpy.types.Object] = []

    def walk_collection(coll: bpy.types.Collection) -> None:
        if is_bake_prep_collection_name(coll.name):
            return
        for obj in coll.objects:
            if obj.name in seen or is_bake_low_pipeline_artifact(obj):
                continue
            seen.add(obj.name)
            linked.append(obj)
        for child_coll in coll.children:
            walk_collection(child_coll)

    for coll in get_low_collections(project, group):
        walk_collection(coll)
    return linked


def _iter_bake_group_high_merge_sources(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """High-role collection objects plus any legacy ``high_root`` subtree."""
    objects = list(iter_bake_group_high_objects(project, group))
    seen = {obj.name for obj in objects}
    high_root = group.high_root
    if high_root is not None and object_helpers.is_object_alive(high_root):
        stack = [high_root]
        while stack:
            obj = stack.pop()
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
            stack.extend(obj.children)
    return objects


def _iter_high_collection_linked_objects(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Objects directly linked in high role collections (nested, excluding _BAKE_PREP)."""
    seen: set[str] = set()
    linked: list[bpy.types.Object] = []

    def walk_collection(coll: bpy.types.Collection) -> None:
        if is_bake_prep_collection_name(coll.name):
            return
        for obj in coll.objects:
            if obj.name in seen or is_bake_high_pipeline_artifact(obj):
                continue
            seen.add(obj.name)
            linked.append(obj)
        for child_coll in coll.children:
            walk_collection(child_coll)

    for coll in get_high_collections(project, group):
        walk_collection(coll)
    return linked


def get_bake_group_high_meshes(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Forest roots for every flattenable high in role collections."""
    sources = [
        obj for obj in _iter_bake_group_high_merge_sources(project, group)
        if not is_bake_high_pipeline_artifact(obj)
        and is_flatten_hierarchy_object(obj)
        and object_has_flatten_geometry(obj)
    ]
    if not sources:
        return []

    participants = object_helpers.expand_objects_with_parent_chain(sources)
    participants = [
        obj for obj in participants
        if not is_bake_high_pipeline_artifact(obj)
        and is_flatten_hierarchy_object(obj)
    ]
    roots = object_helpers.collect_hierarchy_forest_roots(participants)
    covered = {
        obj.name
        for root in roots
        for obj in object_helpers.collect_objects_in_subtrees([root])
    }
    for obj in _iter_high_collection_linked_objects(project, group):
        if obj.name in covered:
            continue
        if obj.type != 'MESH' or is_bake_high_pipeline_artifact(obj):
            continue
        if not is_flatten_hierarchy_object(obj) or not object_has_flatten_geometry(obj):
            continue
        roots.append(obj)
        covered.add(obj.name)
    return object_helpers.collect_hierarchy_forest_roots(roots)


def get_bake_group_low_meshes(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Forest roots for every flattenable low in role collections."""
    role_objects = [
        obj for obj in _iter_bake_group_low_merge_sources(project, group)
        if not is_bake_low_pipeline_artifact(obj)
        and is_flatten_hierarchy_object(obj)
    ]
    if not role_objects:
        return []

    merge_seeds: list[bpy.types.Object] = []
    seen_seeds: set[str] = set()

    def add_merge_seed(obj: bpy.types.Object) -> None:
        if obj.name in seen_seeds:
            return
        if not object_has_flatten_geometry(obj):
            return
        if obj.type == 'MESH' and not is_grouppro_placeholder_object(obj):
            seen_seeds.add(obj.name)
            merge_seeds.append(obj)
        elif is_colinst_object(obj) or is_exportable_grouppro_group(obj):
            seen_seeds.add(obj.name)
            merge_seeds.append(obj)

    for obj in role_objects:
        add_merge_seed(obj)

    linked_roots = _iter_low_collection_linked_objects(project, group)
    colinst_in_low = [
        obj for obj in object_helpers.collect_objects_in_subtrees(linked_roots)
        if not is_bake_low_pipeline_artifact(obj)
        and is_colinst_object(obj)
    ]
    for obj in object_helpers.collect_hierarchy_forest_roots(colinst_in_low):
        add_merge_seed(obj)

    if not merge_seeds:
        return []

    participants = object_helpers.expand_objects_with_parent_chain(merge_seeds)
    participants = [
        obj for obj in participants
        if not is_bake_low_pipeline_artifact(obj)
        and is_flatten_hierarchy_object(obj)
    ]
    roots = object_helpers.collect_hierarchy_forest_roots(participants)
    covered = {
        obj.name
        for root in roots
        for obj in object_helpers.collect_objects_in_subtrees([root])
    }
    for linked in linked_roots:
        for obj in object_helpers.collect_objects_in_subtrees([linked]):
            if obj.name in covered:
                continue
            if is_bake_low_pipeline_artifact(obj):
                continue
            if not is_flatten_hierarchy_object(obj) or not object_has_flatten_geometry(obj):
                continue
            if is_grouppro_placeholder_object(obj) and not (
                is_colinst_object(obj) or is_exportable_grouppro_group(obj)
            ):
                continue
            if obj.type != 'MESH' and not (
                is_colinst_object(obj) or is_exportable_grouppro_group(obj)
            ):
                continue
            roots.append(obj)
            covered.update(
                o.name
                for o in object_helpers.collect_objects_in_subtrees([obj])
            )
    return object_helpers.collect_hierarchy_forest_roots(roots)


def ensure_bake_prep_collection(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    role: str = 'low',
) -> bpy.types.Collection | None:
    """Return `{name}_{role}/_BAKE_PREP/` subcollection, creating if missing."""
    role_key = 'HIGH' if role.upper() == 'HIGH' else 'LOW'
    role_coll = (
        group.high_collection if role_key == 'HIGH' else group.low_collection
    )
    if role_coll is None:
        role_coll = get_bake_group_role_collection(project, group, role_key)
    if role_coll is None:
        return None
    for child in role_coll.children:
        if is_bake_prep_collection_name(child.name):
            return child
    return ensure_child_collection(role_coll, BAKE_PREP_COLLECTION_STEM)


def deep_apply_bake_group_geometry(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    *,
    preview: bool = True,
) -> list[bpy.types.Object]:
    """
    Deep-apply geometry on transient duplicates of `{name}_low/` contents.

    Preview mode places parentless world-space meshes in `{name}_low/`.
    Source objects in `{name}_low/` are not modified.
    """
    low_objects = get_bake_group_low_meshes(project, group)
    if not low_objects:
        return []

    output_coll = group.low_collection
    if output_coll is None:
        output_coll = get_bake_group_role_collection(project, group, 'LOW')
    if output_coll is None:
        return []

    return deep_apply_roots(
        context,
        low_objects,
        output_coll,
        preview=preview,
        work_scene_name=f'_LKS_BakePrep_{group.name}',
    )


def generate_merged_lowpoly_for_bake_group(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bpy.types.Object | None:
    """One merged lowpoly mesh for a bake group's low role containers (duplicates only)."""
    low_objects = get_bake_group_low_meshes(project, group)
    if not low_objects:
        return None

    output_coll = group.low_collection
    if output_coll is None:
        output_coll = get_bake_group_role_collection(project, group, 'LOW')
    if output_coll is None:
        return None

    return generate_merged_lowpoly_for_roots(
        context,
        low_objects,
        output_coll,
        result_name=f'{group.name}_merged_low',
        work_scene_name=f'_LKS_MergedLow_{group.name}',
    )


def generate_merged_lowpoly_for_bake_groups(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    groups: list[LKS_PG_BakeGroup] | None = None,
) -> list[bpy.types.Object]:
    """Run merged lowpoly generation for each bake group in ``groups`` (default: all)."""
    targets = list(project.bake_groups) if groups is None else list(groups)
    results: list[bpy.types.Object] = []
    for group in targets:
        merged = generate_merged_lowpoly_for_bake_group(context, project, group)
        if merged is not None:
            results.append(merged)
    return results


def generate_extracted_highpoly_for_bake_group(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Unmerged extracted high meshes for a bake group's high role containers (duplicates only)."""
    high_objects = get_bake_group_high_meshes(project, group)
    if not high_objects:
        return []

    output_coll = group.high_collection
    if output_coll is None:
        output_coll = get_bake_group_role_collection(project, group, 'HIGH')
    if output_coll is None:
        return []

    return generate_extracted_highpoly_for_roots(
        context,
        high_objects,
        output_coll,
        work_scene_name=f'_LKS_ExtractedHigh_{group.name}',
    )


def generate_extracted_highpoly_for_bake_groups(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    groups: list[LKS_PG_BakeGroup] | None = None,
) -> list[bpy.types.Object]:
    """Run extracted highpoly generation for each bake group in ``groups`` (default: all)."""
    targets = list(project.bake_groups) if groups is None else list(groups)
    results: list[bpy.types.Object] = []
    for group in targets:
        extracted = generate_extracted_highpoly_for_bake_group(context, project, group)
        results.extend(extracted)
    return results


def get_bake_project_low_meshes(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    """Forest roots for every flattenable low across all bake groups."""
    roots: list[bpy.types.Object] = []
    for group in project.bake_groups:
        if not bake_group_low_has_flatten_geometry(project, group):
            continue
        roots.extend(get_bake_group_low_meshes(project, group))
    if not roots:
        return []
    return object_helpers.collect_hierarchy_forest_roots(roots)


def get_bake_project_high_meshes(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    """Forest roots for every flattenable high across all bake groups."""
    roots: list[bpy.types.Object] = []
    for group in project.bake_groups:
        if not bake_group_high_has_flatten_geometry(project, group):
            continue
        roots.extend(get_bake_group_high_meshes(project, group))
    if not roots:
        return []
    return object_helpers.collect_hierarchy_forest_roots(roots)


def generate_merged_lowpoly_for_bake_project(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
) -> bpy.types.Object | None:
    """One merged lowpoly mesh from all bake groups' low role containers (duplicates only)."""
    low_objects = get_bake_project_low_meshes(project)
    if not low_objects:
        return None

    output_coll = ensure_bake_project_prep_collection(project)
    if output_coll is None:
        return None

    return generate_merged_lowpoly_for_roots(
        context,
        low_objects,
        output_coll,
        result_name=f'{project.name}_merged_low',
        work_scene_name=f'_LKS_MergedLow_{project.name}',
    )


def generate_extracted_highpoly_for_bake_project(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    """Unmerged extracted high meshes from all bake groups' high role containers."""
    high_objects = get_bake_project_high_meshes(project)
    if not high_objects:
        return []

    output_coll = ensure_bake_project_prep_collection(project)
    if output_coll is None:
        return []

    return generate_extracted_highpoly_for_roots(
        context,
        high_objects,
        output_coll,
        work_scene_name=f'_LKS_ExtractedHigh_{project.name}',
    )

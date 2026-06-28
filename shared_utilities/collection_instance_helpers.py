"""Convert collection instances and Group Pro instances into real object hierarchies."""

from __future__ import annotations

from dataclasses import dataclass, field

import bpy

from . import object_helpers
from .colinst_extract_helpers import (
    ColinstExtractResult,
    extract_object_hierarchy,
    extract_selection_to_hierarchy,
)
from .grouppro_helpers import get_grouppro_collection, is_grouppro_mesh_group


@dataclass(frozen=True)
class BakeCollectionInstancesResult:
    """Outcome of dissolving collection / GP instances in the current selection."""

    baked_count: int = 0
    dissolved_count: int = 0
    root_empties: list[bpy.types.Object] = field(default_factory=list)


def is_collection_instance(obj: bpy.types.Object | None) -> bool:
    """True when ``obj`` is a Blender collection instance empty."""
    return (
        obj is not None
        and obj.instance_collection is not None
        and getattr(obj, 'instance_type', None) == 'COLLECTION'
    )


def is_colinst_object(obj: bpy.types.Object | None) -> bool:
    """True when ``obj`` is a Blender collection instance or Group Pro mesh instance."""
    if obj is None:
        return False
    if is_collection_instance(obj):
        return True
    return is_grouppro_mesh_group(obj)


def get_instanced_collection(
    obj: bpy.types.Object | None,
) -> bpy.types.Collection | None:
    """Return the instanced collection for a CI empty or GP ``GPro_Instance`` mesh."""
    if obj is None:
        return None
    if is_collection_instance(obj):
        return obj.instance_collection
    if is_grouppro_mesh_group(obj):
        return get_grouppro_collection(obj)
    return None


def selection_has_colinst_objects(context: bpy.types.Context) -> bool:
    """True when the selection subtree contains at least one CI or GP instance."""
    return bool(find_colinst_roots_in_selection(context))


def selection_has_collection_instances(context: bpy.types.Context) -> bool:
    """Alias for :func:`selection_has_colinst_objects`."""
    return selection_has_colinst_objects(context)


def find_colinst_roots_in_selection(
    context: bpy.types.Context,
    roots: list[bpy.types.Object] | None = None,
) -> list[bpy.types.Object]:
    """Forest-root CI / GP instances under the selection subtree."""
    if roots is None:
        selected = object_helpers.context_selected_objects(context)
        if not selected:
            return []
        roots = object_helpers.collect_hierarchy_forest_roots(selected)

    subtree = object_helpers.collect_objects_in_subtrees(roots)
    instances = [obj for obj in subtree if is_colinst_object(obj)]
    return object_helpers.collect_hierarchy_forest_roots(instances)


def find_collection_instances_in_selection(
    context: bpy.types.Context,
    roots: list[bpy.types.Object] | None = None,
) -> list[bpy.types.Object]:
    """Alias for :func:`find_colinst_roots_in_selection`."""
    return find_colinst_roots_in_selection(context, roots)


def _result_from_extract(extract_result: ColinstExtractResult) -> BakeCollectionInstancesResult:
    return BakeCollectionInstancesResult(
        baked_count=extract_result.extracted_count,
        dissolved_count=extract_result.dissolved_count,
        root_empties=extract_result.root_objects,
    )


def bake_colinst_to_hierarchy(
    context: bpy.types.Context,
    instance_obj: bpy.types.Object,
    *,
    parent_empty: bpy.types.Object | None = None,
) -> bpy.types.Object:
    """Dissolve a single object subtree; ``parent_empty`` is ignored (legacy API)."""
    _ = parent_empty
    return extract_object_hierarchy(context, instance_obj)


def bake_collection_instance_to_hierarchy(
    context: bpy.types.Context,
    instance_obj: bpy.types.Object,
    *,
    parent_empty: bpy.types.Object | None = None,
) -> bpy.types.Object:
    """Alias for :func:`bake_colinst_to_hierarchy`."""
    return bake_colinst_to_hierarchy(
        context,
        instance_obj,
        parent_empty=parent_empty,
    )


def bake_colinst_objects_in_subtrees(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
) -> BakeCollectionInstancesResult:
    """Dissolve instances in each forest root subtree using breadth-first traversal."""
    return _result_from_extract(extract_selection_to_hierarchy(context, roots))


def bake_collection_instances_in_selection(
    context: bpy.types.Context,
) -> BakeCollectionInstancesResult:
    """Dissolve instances under selected object forest roots."""
    selected = object_helpers.context_selected_objects(context)
    if not selected:
        return BakeCollectionInstancesResult()
    return bake_colinst_objects_in_subtrees(context, selected)


__all__ = [
    'BakeCollectionInstancesResult',
    'bake_collection_instance_to_hierarchy',
    'bake_collection_instances_in_selection',
    'bake_colinst_objects_in_subtrees',
    'bake_colinst_to_hierarchy',
    'find_colinst_roots_in_selection',
    'find_collection_instances_in_selection',
    'get_instanced_collection',
    'is_collection_instance',
    'is_colinst_object',
    'selection_has_colinst_objects',
    'selection_has_collection_instances',
]

"""Shared export/bake geometry helpers — re-exports deep apply + export flatten entry points."""

from __future__ import annotations

import bpy

from .deep_apply_geometry_helpers import (
    deep_apply_geometry,
    duplicate_objects_preserving_hierarchy,
    flatten_geometry,
)
from .mesh_attribute_sync_helpers import sync_mesh_attributes_for_join
from .hierarchy_flatten_helpers import (
    flatten_hierarchy_to_world_meshes,
    remove_grouppro_placeholder_objects,
)


def prepare_grouppro_groups_in_scene(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
) -> None:
    """Dissolve Group Pro mesh groups in scene (export/bake flatten B2a–B2c)."""
    flatten_hierarchy_to_world_meshes(
        context,
        scene,
        object_filter=object_filter,
        apply_modifiers=False,
    )


def flatten_mesh_hierarchy_in_scene(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
) -> list[bpy.types.Object]:
    """Flatten any transform hierarchy: GP, instances, cook, cleanup (B2)."""
    return flatten_hierarchy_to_world_meshes(
        context,
        scene,
        object_filter=object_filter,
        apply_modifiers=False,
    )


def flatten_geometry_for_bake(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
    uvset_count: int | None = None,
    vcol_count: int | None = None,
) -> list[bpy.types.Object]:
    """Flatten hierarchy, sync attributes, and apply modifiers (Stage B2–B3)."""
    return flatten_geometry(
        context,
        scene,
        object_filter=object_filter,
        uvset_count=uvset_count,
        vcol_count=vcol_count,
    )

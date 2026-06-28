"""Test operator — uniquify scope meshes and apply baker-managed project low material."""

from __future__ import annotations

import bpy

from ..shared_utilities import object_helpers
from .static_utilities.bake_low_material_helpers import (
    bake_low_material_prefix,
    bake_low_material_suffix,
    bake_project_low_material_name,
    collect_hierarchy_meshes_expanded,
    uniquify_and_apply_bake_low_material,
)
from .helpers_bake_cleanup import iter_bake_group_low_objects
from .lks_bake_props import (
    LKS_PG_BakeGroup,
    LKS_PG_BakeProject,
    get_active_bake_project,
    read_active_bake_group_index,
)


def resolve_bake_low_material_roots(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """
    Scope roots for low-material test.

    Selection forest roots take priority (matches Set Low input objects).
    With no selection, falls back to active bake group low-role objects.
    """
    selected = object_helpers.context_selected_objects(context)
    if selected:
        return object_helpers.collect_hierarchy_forest_roots(selected)
    low_objects = iter_bake_group_low_objects(project, group)
    return object_helpers.collect_hierarchy_forest_roots(low_objects)


class LKS_OT_ApplyBakeLowMaterialTest(bpy.types.Operator):
    """Uniquify meshes in scope and assign the active bake project's single low material."""
    bl_idname = 'object.lks_apply_bake_low_material_test'
    bl_label = 'Apply Bake Low Material (Test)'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def _active_group(
        cls,
        project: LKS_PG_BakeProject,
    ) -> LKS_PG_BakeGroup | None:
        index = read_active_bake_group_index(project)
        if not (0 <= index < len(project.bake_groups)):
            return None
        return project.bake_groups[index]

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        project = get_active_bake_project(context.scene)
        if project is None or len(project.bake_groups) == 0:
            return False
        group = cls._active_group(project)
        if group is None:
            return False
        if len(context.selected_objects) > 0:
            return True
        return len(iter_bake_group_low_objects(project, group)) > 0

    def execute(self, context: bpy.types.Context) -> set[str]:
        project = get_active_bake_project(context.scene, write_back=True)
        if project is None:
            self.report({'ERROR'}, 'No active bake project')
            return {'CANCELLED'}

        group = self._active_group(project)
        if group is None:
            self.report({'ERROR'}, 'No active bake group')
            return {'CANCELLED'}

        roots = resolve_bake_low_material_roots(context, project, group)
        if not roots:
            self.report({'ERROR'}, 'No scope roots — select objects or assign lows to the bake group')
            return {'CANCELLED'}

        meshes_before = collect_hierarchy_meshes_expanded(roots)
        if not meshes_before:
            self.report({'ERROR'}, 'No meshes found in scope (including CI / GP expansion)')
            return {'CANCELLED'}

        count = uniquify_and_apply_bake_low_material(project, roots, context.scene)
        mat_name = bake_project_low_material_name(
            project.name,
            prefix=bake_low_material_prefix(project, context.scene),
            suffix=bake_low_material_suffix(project),
        )
        scope = 'selection' if context.selected_objects else f"bake group '{group.name}' lows"
        self.report(
            {'INFO'},
            f"Applied '{mat_name}' to {count} mesh(es) from {scope}",
        )
        return {'FINISHED'}

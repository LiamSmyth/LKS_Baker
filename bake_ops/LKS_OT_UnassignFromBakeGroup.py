"""Unlink selected objects from the active bake group collection tree."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import (
    selected_objects_in_bake_group,
    unassign_objects_from_bake_group,
)
from .lks_bake_props import get_active_bake_project, read_active_bake_group_index


class LKS_OT_UnassignFromBakeGroup(bpy.types.Operator):
    """Move selected objects from the active bake group tree to scene collection only."""
    bl_idname = 'object.lks_unassign_from_bake_group'
    bl_label = 'Unassign'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        project = get_active_bake_project(context.scene)
        if project is None or len(project.bake_groups) == 0:
            return False
        group_index = read_active_bake_group_index(project)
        if not (0 <= group_index < len(project.bake_groups)):
            return False
        group = project.bake_groups[group_index]
        return len(selected_objects_in_bake_group(context, project, group)) > 0

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        project = get_active_bake_project(scene, write_back=True)
        if project is None:
            self.report({'ERROR'}, 'No active bake project')
            return {'CANCELLED'}

        group_index = read_active_bake_group_index(project)
        if not (0 <= group_index < len(project.bake_groups)):
            self.report({'ERROR'}, 'No active bake group')
            return {'CANCELLED'}

        group = project.bake_groups[group_index]
        objects = selected_objects_in_bake_group(context, project, group)
        if not objects:
            self.report({'ERROR'}, 'Selection is not in the active bake group')
            return {'CANCELLED'}

        removed = unassign_objects_from_bake_group(project, group, objects, scene)
        self.report({'INFO'}, f"Unassigned {removed} object(s) from '{group.name}'")
        return {'FINISHED'}

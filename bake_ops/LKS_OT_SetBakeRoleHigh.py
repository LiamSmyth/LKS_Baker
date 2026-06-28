"""Assign selected objects to the high role container."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import assign_bake_role
from .lks_bake_props import get_active_bake_project, read_active_bake_group_index


class LKS_OT_SetBakeRoleHigh(bpy.types.Operator):
    """Move selection exclusively into `{name}_BakeGroup/{name}_high/`; objects keep their names."""
    bl_idname = 'object.lks_set_bake_role_high'
    bl_label = 'Set High'
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
        return len(context.selected_objects) > 0

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
        selected = list(context.selected_objects)
        if not selected:
            self.report({'ERROR'}, 'No objects selected')
            return {'CANCELLED'}

        role_coll = assign_bake_role(project, group, selected, 'HIGH')
        if role_coll is None:
            self.report({'ERROR'}, 'Could not assign high role')
            return {'CANCELLED'}

        self.report({'INFO'}, f"Assigned high role in '{role_coll.name}' on '{group.name}'")
        return {'FINISHED'}

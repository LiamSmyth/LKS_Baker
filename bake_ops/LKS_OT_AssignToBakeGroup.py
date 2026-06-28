"""Move selected objects exclusively into the active bake group staging folder."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import assign_objects_to_bake_group, assignable_bake_selected_objects
from .lks_bake_props import get_active_bake_project, read_active_bake_group_index


class LKS_OT_AssignToBakeGroup(bpy.types.Operator):
    """Move selected bake-eligible objects exclusively into the active group's `{name}_BakeGroup/` collection."""
    bl_idname = 'object.lks_assign_to_bake_group'
    bl_label = 'Assign'
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
        return len(assignable_bake_selected_objects(context)) > 0

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
        objects = assignable_bake_selected_objects(context)
        if not objects:
            self.report({'ERROR'}, 'No bake-eligible objects in selection')
            return {'CANCELLED'}

        moved = assign_objects_to_bake_group(project, group, objects)
        self.report(
            {'INFO'},
            f"Assigned {moved} object(s) to '{group.name}'",
        )
        return {'FINISHED'}

"""Create an empty bake group row and staging collection under the active project."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import create_bake_group, unique_bake_group_name
from .lks_bake_props import get_active_bake_project


class LKS_OT_NewBakeGroup(bpy.types.Operator):
    """Create a bake group collection and RNA row on the active bake project."""
    bl_idname = 'object.lks_new_bake_group'
    bl_label = 'New Bake Group'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        return get_active_bake_project(context.scene) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        project = get_active_bake_project(scene, write_back=True)
        if project is None:
            self.report({'ERROR'}, 'No active bake project')
            return {'CANCELLED'}

        group_name = unique_bake_group_name(project)
        try:
            create_bake_group(project, group_name, scene)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        self.report({'INFO'}, f"Created bake group '{group_name}'")
        return {'FINISHED'}

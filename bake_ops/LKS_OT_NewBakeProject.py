"""Create a new LKS BakeProject RNA entry and root collection stub."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import create_bake_project, unique_bake_project_name


class LKS_OT_NewBakeProject(bpy.types.Operator):
    """Create a bake project collection tree and scene RNA entry."""
    bl_idname = 'object.lks_new_bake_project'
    bl_label = 'New Bake Project'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        project_name = unique_bake_project_name(scene)
        create_bake_project(scene, project_name)
        self.report({'INFO'}, f"Created bake project '{project_name}'")
        return {'FINISHED'}

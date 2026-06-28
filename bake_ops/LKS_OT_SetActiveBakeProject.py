"""Set the scene active bake project by collection index."""

from __future__ import annotations

import bpy

from .lks_bake_props import clamp_active_bake_project_index


class LKS_OT_SetActiveBakeProject(bpy.types.Operator):
    """Select which bake project is active for operators and detail UI."""
    bl_idname = 'object.lks_set_active_bake_project'
    bl_label = 'Set Active Bake Project'
    bl_options = {'REGISTER', 'INTERNAL'}

    project_index: bpy.props.IntProperty(name='Project Index', min=0)

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        if 0 <= self.project_index < len(scene.lks_bake_projects):
            scene.lks_active_bake_project_index = self.project_index
        else:
            clamp_active_bake_project_index(scene)
        return {'FINISHED'}

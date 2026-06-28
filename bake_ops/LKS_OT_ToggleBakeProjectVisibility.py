"""Toggle viewport visibility for all objects in a bake project collection tree."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import bake_project_any_visible, iter_bake_project_objects


class LKS_OT_ToggleBakeProjectVisibility(bpy.types.Operator):
    """Show or hide all objects in the bake project collection tree."""
    bl_idname = 'object.lks_toggle_bake_project_visibility'
    bl_label = 'Toggle Bake Project Visibility'
    bl_options = {'REGISTER', 'UNDO'}

    project_index: bpy.props.IntProperty(
        name='Project Index',
        default=-1,
        description='Bake project index (-1 = active project)',
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        return len(context.scene.lks_bake_projects) > 0

    def _resolve_project_index(self, scene: bpy.types.Scene) -> int:
        if self.project_index >= 0:
            return self.project_index
        return scene.lks_active_bake_project_index

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        index = self._resolve_project_index(scene)
        if not (0 <= index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[index]
        hide = bake_project_any_visible(project)
        objects = iter_bake_project_objects(project)
        for obj in objects:
            obj.hide_viewport = hide

        verb = 'Hidden' if hide else 'Shown'
        self.report({'INFO'}, f"{verb} {len(objects)} object(s) for '{project.name}'")
        return {'FINISHED'}

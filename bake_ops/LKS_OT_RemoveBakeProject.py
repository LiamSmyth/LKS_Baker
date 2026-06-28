"""Remove a bake project, dissolve its collection tree, and drop scene RNA."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import bake_project_has_geometry, cleanup_bake_project
from .lks_bake_props import clamp_active_bake_project_index


class LKS_OT_RemoveBakeProject(bpy.types.Operator):
    """Remove bake project RNA and dissolve its collection tree."""
    bl_idname = 'object.lks_remove_bake_project'
    bl_label = 'Remove Bake Project'
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

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        scene = context.scene
        index = self._resolve_project_index(scene)
        if not (0 <= index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project to remove')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[index]
        if bake_project_has_geometry(project):
            return context.window_manager.invoke_confirm(
                self,
                event,
                message=(
                    'Bake collections hold geometry. '
                    'Objects will be moved to the scene collection, not deleted.'
                ),
            )
        return self.execute(context)

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        index = self._resolve_project_index(scene)
        if not (0 <= index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project to remove')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[index]
        project_name = project.name

        cleanup_bake_project(project, scene)

        scene.lks_bake_projects.remove(index)
        clamp_active_bake_project_index(scene)

        self.report({'INFO'}, f"Removed bake project '{project_name}'")
        return {'FINISHED'}

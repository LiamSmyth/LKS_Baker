"""Select all objects in a bake project collection tree."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import iter_bake_project_objects
from .lks_bake_props import clamp_active_bake_project_index


class LKS_OT_SelectBakeProjectContents(bpy.types.Operator):
    """Select all objects linked to the bake project collections."""
    bl_idname = 'object.lks_select_bake_project_contents'
    bl_label = 'Select Bake Project Contents'
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
        scene.lks_active_bake_project_index = index
        clamp_active_bake_project_index(scene)

        objects = iter_bake_project_objects(project)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        if objects:
            context.view_layer.objects.active = objects[0]

        self.report({'INFO'}, f"Selected {len(objects)} object(s) in '{project.name}'")
        return {'FINISHED'}

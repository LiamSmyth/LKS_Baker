"""Select all objects in a bake group collection subtree."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import iter_bake_group_objects
from .lks_bake_props import (
    clamp_active_bake_group_index,
    clamp_active_bake_project_index,
    get_active_bake_project,
)


class LKS_OT_SelectBakeGroupContents(bpy.types.Operator):
    """Select all objects linked to the bake group collections."""
    bl_idname = 'object.lks_select_bake_group_contents'
    bl_label = 'Select Bake Group Contents'
    bl_options = {'REGISTER', 'UNDO'}

    project_index: bpy.props.IntProperty(
        name='Project Index',
        default=-1,
        description='Parent bake project index (-1 = active project)',
    )
    group_index: bpy.props.IntProperty(
        name='Group Index',
        default=-1,
        description='Bake group index (-1 = active group on resolved project)',
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        return len(context.scene.lks_bake_projects) > 0

    def _resolve_project(self, scene: bpy.types.Scene) -> bpy.types.PropertyGroup | None:
        if self.project_index >= 0:
            projects = scene.lks_bake_projects
            if 0 <= self.project_index < len(projects):
                return projects[self.project_index]
            return None
        return get_active_bake_project(scene, write_back=True)

    def _resolve_group_index(self, project: bpy.types.PropertyGroup) -> int:
        if self.group_index >= 0:
            return self.group_index
        return project.active_bake_group_index

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        project = self._resolve_project(scene)
        if project is None:
            self.report({'ERROR'}, 'No bake project')
            return {'CANCELLED'}

        group_index = self._resolve_group_index(project)
        if not (0 <= group_index < len(project.bake_groups)):
            self.report({'ERROR'}, 'No bake group')
            return {'CANCELLED'}

        if self.project_index >= 0:
            scene.lks_active_bake_project_index = self.project_index
        clamp_active_bake_project_index(scene)
        project.active_bake_group_index = group_index
        clamp_active_bake_group_index(project)

        group = project.bake_groups[group_index]
        objects = iter_bake_group_objects(project, group)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        if objects:
            context.view_layer.objects.active = objects[0]

        self.report({'INFO'}, f"Selected {len(objects)} object(s) in '{group.name}'")
        return {'FINISHED'}

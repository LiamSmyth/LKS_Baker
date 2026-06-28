"""Toggle viewport visibility for all objects in a bake group collection subtree."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import bake_group_any_visible, iter_bake_group_objects
from .lks_bake_props import (
    clamp_active_bake_group_index,
    clamp_active_bake_project_index,
    get_active_bake_project,
)


class LKS_OT_ToggleBakeGroupVisibility(bpy.types.Operator):
    """Show or hide all objects in the bake group collection subtree."""
    bl_idname = 'object.lks_toggle_bake_group_visibility'
    bl_label = 'Toggle Bake Group Visibility'
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
        hide = bake_group_any_visible(project, group)
        objects = iter_bake_group_objects(project, group)
        for obj in objects:
            obj.hide_viewport = hide

        verb = 'Hidden' if hide else 'Shown'
        self.report({'INFO'}, f"{verb} {len(objects)} object(s) for '{group.name}'")
        return {'FINISHED'}

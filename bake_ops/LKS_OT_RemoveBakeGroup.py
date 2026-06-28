"""Remove one bake group from a project with collection cleanup."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import bake_group_has_geometry, cleanup_bake_group
from .lks_bake_props import get_active_bake_project


class LKS_OT_RemoveBakeGroup(bpy.types.Operator):
    """Remove a bake group row and dissolve its staging/role collections."""
    bl_idname = 'object.lks_remove_bake_group'
    bl_label = 'Remove Bake Group'
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
        scene = context.scene
        project = get_active_bake_project(scene)
        return project is not None and len(project.bake_groups) > 0

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

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        project = self._resolve_project(context.scene)
        if project is None:
            self.report({'ERROR'}, 'No bake project to edit')
            return {'CANCELLED'}

        group_index = self._resolve_group_index(project)
        if not (0 <= group_index < len(project.bake_groups)):
            self.report({'ERROR'}, 'No bake group to remove')
            return {'CANCELLED'}

        group = project.bake_groups[group_index]
        if bake_group_has_geometry(project, group):
            return context.window_manager.invoke_confirm(
                self,
                event,
                message=(
                    'Role or staging collections hold geometry. '
                    'Objects will be moved to the scene collection, not deleted.'
                ),
            )
        return self.execute(context)

    def execute(self, context: bpy.types.Context) -> set[str]:
        project = self._resolve_project(context.scene)
        if project is None:
            self.report({'ERROR'}, 'No bake project to edit')
            return {'CANCELLED'}

        group_index = self._resolve_group_index(project)
        if not (0 <= group_index < len(project.bake_groups)):
            self.report({'ERROR'}, 'No bake group to remove')
            return {'CANCELLED'}

        group = project.bake_groups[group_index]
        group_name = group.name
        cleanup_bake_group(project, group_index, context.scene)

        self.report({'INFO'}, f"Removed bake group '{group_name}'")
        return {'FINISHED'}

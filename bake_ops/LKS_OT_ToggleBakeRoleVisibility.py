"""Toggle viewport visibility for bake high/low role geometry."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import (
    toggle_bake_group_role_visibility,
    toggle_bake_project_role_visibility,
)
from .lks_bake_props import (
    clamp_active_bake_group_index,
    clamp_active_bake_project_index,
    get_active_bake_project,
)


class _LKS_OT_ToggleBakeProjectRoleVisibilityBase(bpy.types.Operator):
    """Shared execute for project-scoped high/low visibility toggles."""

    bl_options = {'REGISTER', 'UNDO'}
    role: str = 'high'

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
        count, hide = toggle_bake_project_role_visibility(project, role=self.role)
        role_label = 'high' if self.role == 'high' else 'low'
        verb = 'Hidden' if hide else 'Shown'
        self.report(
            {'INFO'},
            f"{verb} {count} {role_label} object(s) for '{project.name}'",
        )
        return {'FINISHED'}


class _LKS_OT_ToggleBakeGroupRoleVisibilityBase(bpy.types.Operator):
    """Shared execute for group-scoped high/low visibility toggles."""

    bl_options = {'REGISTER', 'UNDO'}
    role: str = 'high'

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
        count, hide = toggle_bake_group_role_visibility(
            project,
            group,
            role=self.role,
        )
        role_label = 'high' if self.role == 'high' else 'low'
        verb = 'Hidden' if hide else 'Shown'
        self.report(
            {'INFO'},
            f"{verb} {count} {role_label} object(s) for '{group.name}'",
        )
        return {'FINISHED'}


class LKS_OT_ToggleBakeProjectHighVisibility(_LKS_OT_ToggleBakeProjectRoleVisibilityBase):
    """Show or hide all high-role objects across every bake group in the project."""
    bl_idname = 'object.lks_toggle_bake_project_high_vis'
    bl_label = 'Toggle Bake Project High Visibility'
    role = 'high'


class LKS_OT_ToggleBakeProjectLowVisibility(_LKS_OT_ToggleBakeProjectRoleVisibilityBase):
    """Show or hide all low-role objects across every bake group in the project."""
    bl_idname = 'object.lks_toggle_bake_project_low_vis'
    bl_label = 'Toggle Bake Project Low Visibility'
    role = 'low'


class LKS_OT_ToggleBakeGroupHighVisibility(_LKS_OT_ToggleBakeGroupRoleVisibilityBase):
    """Show or hide high-role objects for this bake group."""
    bl_idname = 'object.lks_toggle_bake_group_high_vis'
    bl_label = 'Toggle Bake Group High Visibility'
    role = 'high'


class LKS_OT_ToggleBakeGroupLowVisibility(_LKS_OT_ToggleBakeGroupRoleVisibilityBase):
    """Show or hide low-role objects for this bake group."""
    bl_idname = 'object.lks_toggle_bake_group_low_vis'
    bl_label = 'Toggle Bake Group Low Visibility'
    role = 'low'

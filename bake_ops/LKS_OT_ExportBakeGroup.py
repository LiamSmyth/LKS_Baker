"""Export one bake group — generate processed geometry then write scoped FBX."""

from __future__ import annotations

import bpy

from ..shared_utilities.lks_constants import (
    BAKE_EXPORT_MODE_DEFAULT,
    BAKE_EXPORT_MODE_ITEMS,
)
from .helpers_bake_export import export_bake_group
from .lks_bake_props import read_active_bake_group_index, read_active_bake_project_index


class LKS_OT_ExportBakeGroup(bpy.types.Operator):
    """Generate merged low / extracted high meshes for one group, then export FBX."""
    bl_idname = 'object.lks_export_bake_group'
    bl_label = 'Export Bake Group'
    bl_options = {'REGISTER'}

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
    export_mode: bpy.props.EnumProperty(
        name='Export Mode',
        description='How to package this bake group geometry into FBX files',
        items=BAKE_EXPORT_MODE_ITEMS,
        default=BAKE_EXPORT_MODE_DEFAULT,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        return len(context.scene.lks_bake_projects) > 0

    def _resolve_project_index(self, scene: bpy.types.Scene) -> int:
        if self.project_index >= 0:
            return self.project_index
        return read_active_bake_project_index(scene)

    def _resolve_group_index(self, project: bpy.types.Any) -> int:
        if self.group_index >= 0:
            return self.group_index
        return read_active_bake_group_index(project)

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        project_index = self._resolve_project_index(scene)
        if not (0 <= project_index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project to export from')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[project_index]
        group_index = self._resolve_group_index(project)
        if not (0 <= group_index < len(project.bake_groups)):
            self.report({'ERROR'}, 'No bake group to export')
            return {'CANCELLED'}

        group = project.bake_groups[group_index]
        export_mode = self.export_mode

        try:
            paths = export_bake_group(
                context,
                project,
                group,
                export_mode=export_mode,
                output_dir=project.output_dir,
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Exported {len(paths)} FBX file(s) for '{group.name}' to {project.output_dir}",
        )
        return {'FINISHED'}

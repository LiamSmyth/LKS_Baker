"""Export bake project — generate processed geometry then write scoped FBX."""

from __future__ import annotations

import bpy

from ..shared_utilities.lks_constants import (
    BAKE_EXPORT_MODE_DEFAULT,
    BAKE_EXPORT_MODE_ITEMS,
)
from .helpers_bake_export import export_bake_project


class LKS_OT_ExportBakeProject(bpy.types.Operator):
    """Generate merged low / extracted high meshes, then export FBX to the project output directory."""
    bl_idname = 'object.lks_export_bake_project'
    bl_label = 'Export Bake Project'
    bl_options = {'REGISTER'}

    project_index: bpy.props.IntProperty(
        name='Project Index',
        default=-1,
        description='Bake project index (-1 = active project)',
    )
    export_mode: bpy.props.EnumProperty(
        name='Export Mode',
        description='How to package bake group geometry into FBX files',
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
        return scene.lks_active_bake_project_index

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        index = self._resolve_project_index(scene)
        if not (0 <= index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project to export')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[index]
        export_mode = self.export_mode

        try:
            paths = export_bake_project(
                context,
                project,
                export_mode=export_mode,
                output_dir=project.output_dir,
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Exported {len(paths)} FBX file(s) to {project.output_dir}",
        )
        return {'FINISHED'}

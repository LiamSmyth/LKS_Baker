"""Toggle solo baked-map preview on the project low material."""

from __future__ import annotations

import bpy

from .static_utilities.bake_preview_material_helpers import (
    bake_map_image_exists_on_disk,
    nudge_viewport_material_shading,
    toggle_solo_map_preview,
)
from .helpers_bake_run import collect_project_low_roots


class LKS_OT_ToggleBakeMapPreview(bpy.types.Operator):
    """Preview one baked map on all project low meshes (radio toggle)."""
    bl_idname = 'object.lks_toggle_bake_map_preview'
    bl_label = 'Toggle Bake Map Preview'
    bl_options = {'REGISTER'}

    project_index: bpy.props.IntProperty(
        name='Project Index',
        default=-1,
        min=-1,
    )
    map_id: bpy.props.StringProperty(
        name='Map ID',
        default='',
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.area is not None and context.area.type == 'VIEW_3D'

    def _resolve_project_index(self, scene: bpy.types.Scene) -> int:
        if self.project_index >= 0:
            return self.project_index
        return scene.lks_active_bake_project_index

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        map_id = (self.map_id or '').strip()
        if not map_id:
            self.report({'ERROR'}, 'No bake map specified')
            return {'CANCELLED'}

        index = self._resolve_project_index(scene)
        if not (0 <= index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project for preview')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[index]
        if not bake_map_image_exists_on_disk(project, map_id):
            self.report({'WARNING'}, f"No baked image on disk for '{map_id}'")
            return {'CANCELLED'}

        low_roots = collect_project_low_roots(project)
        if not low_roots:
            self.report({'ERROR'}, 'No low meshes assigned in bake project')
            return {'CANCELLED'}

        project.lks_preview_map_id = toggle_solo_map_preview(
            context,
            project,
            map_id,
            low_roots,
        )
        nudge_viewport_material_shading(context)
        return {'FINISHED'}

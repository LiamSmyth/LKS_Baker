"""Reconstruct the bake project low preview material from project state."""

from __future__ import annotations

import bpy

from .helpers_bake_run import collect_project_low_roots
from .static_utilities.bake_preview_material_helpers import reapply_bake_preview_material


class LKS_OT_ReapplyBakePreviewMaterial(bpy.types.Operator):
    """Rebuild preview shader wiring from baked maps (composite or active solo preview)."""
    bl_idname = 'object.lks_reapply_bake_preview_material'
    bl_label = 'Reapply Preview Material'
    bl_options = {'REGISTER', 'UNDO'}

    project_index: bpy.props.IntProperty(
        name='Project Index',
        default=-1,
        min=-1,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        if len(context.scene.lks_bake_projects) == 0:
            return False
        index = context.scene.lks_active_bake_project_index
        if not (0 <= index < len(context.scene.lks_bake_projects)):
            return False
        project = context.scene.lks_bake_projects[index]
        return len(collect_project_low_roots(project)) > 0

    def _resolve_project_index(self, scene: bpy.types.Scene) -> int:
        if self.project_index >= 0:
            return self.project_index
        return scene.lks_active_bake_project_index

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        index = self._resolve_project_index(scene)
        if not (0 <= index < len(scene.lks_bake_projects)):
            self.report({'ERROR'}, 'No bake project for preview material')
            return {'CANCELLED'}

        project = scene.lks_bake_projects[index]
        low_roots = collect_project_low_roots(project)
        if not low_roots:
            self.report({'ERROR'}, 'No low meshes assigned in bake project')
            return {'CANCELLED'}

        mesh_count = reapply_bake_preview_material(context, project, low_roots)
        preview_map_id = (getattr(project, 'lks_preview_map_id', None) or '').strip()
        if preview_map_id:
            self.report(
                {'INFO'},
                f"Reapplied solo preview for '{preview_map_id}' on {mesh_count} mesh(es)",
            )
        else:
            self.report(
                {'INFO'},
                f'Reapplied composite preview material on {mesh_count} mesh(es)',
            )
        return {'FINISHED'}

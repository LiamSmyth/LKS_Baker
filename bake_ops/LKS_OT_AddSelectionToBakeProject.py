"""Move eligible selection exclusively to the active bake project root."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import (
    create_bake_project,
    eligible_bake_selected_objects,
    move_objects_to_project_root,
    resolve_bake_project_stem_from_selection,
    unique_bake_project_name,
)
from .lks_bake_props import get_active_bake_project


class LKS_OT_AddSelectionToBakeProject(bpy.types.Operator):
    """Move selection exclusively to the active bake project root (no bake group)."""
    bl_idname = 'object.lks_add_selection_to_bake_project'
    bl_label = 'From Selected'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        return len(eligible_bake_selected_objects(context)) > 0

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        eligible = eligible_bake_selected_objects(context)
        if not eligible:
            self.report({'ERROR'}, 'No bake-eligible objects in selection')
            return {'CANCELLED'}

        project = get_active_bake_project(scene, write_back=True)
        if project is None:
            stem = resolve_bake_project_stem_from_selection(context, eligible)
            project_name = unique_bake_project_name(scene, stem)
            project = create_bake_project(scene, project_name)

        if project.root_collection is None:
            self.report({'ERROR'}, 'Bake project has no root collection')
            return {'CANCELLED'}

        moved = move_objects_to_project_root(project, eligible)
        self.report(
            {'INFO'},
            f'Moved {moved} object(s) to project root ({len(eligible)} eligible)',
        )
        return {'FINISHED'}

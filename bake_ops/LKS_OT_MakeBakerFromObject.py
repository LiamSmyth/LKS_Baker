"""Initialize a bake group from the current selection under the active project."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import (
    create_bake_group,
    eligible_bake_selected_objects,
    move_objects_to_bake_group_staging,
    resolve_bake_project_stem_from_selection,
    unique_bake_group_name,
)
from .lks_bake_props import get_active_bake_project


class LKS_OT_MakeBakerFromObject(bpy.types.Operator):
    """Create a bake group row and staging collection from the selection."""
    bl_idname = 'object.lks_make_baker_from_object'
    bl_label = 'Make Baker From Object'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        if get_active_bake_project(context.scene) is None:
            return False
        return len(eligible_bake_selected_objects(context)) > 0

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        project = get_active_bake_project(scene, write_back=True)
        if project is None:
            self.report({'ERROR'}, 'No active bake project')
            return {'CANCELLED'}

        eligible = eligible_bake_selected_objects(context)
        if not eligible:
            self.report({'ERROR'}, 'No bake-eligible objects in selection')
            return {'CANCELLED'}

        stem = resolve_bake_project_stem_from_selection(context, eligible)
        group_name = unique_bake_group_name(project, stem)
        try:
            bake_group = create_bake_group(project, group_name, scene)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        moved = move_objects_to_bake_group_staging(project, bake_group, eligible)
        self.report(
            {'INFO'},
            f"Created bake group '{group_name}' with {moved} moved object(s)",
        )
        return {'FINISHED'}

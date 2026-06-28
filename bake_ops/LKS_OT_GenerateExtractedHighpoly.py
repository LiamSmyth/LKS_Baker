"""Temporary operator — extracted highpoly meshes per bake group (no join)."""

from __future__ import annotations

import bpy

from .helpers_bake_prep import (
    bake_group_high_has_flatten_geometry,
    generate_extracted_highpoly_for_bake_group,
    generate_extracted_highpoly_for_bake_groups,
)
from .lks_bake_props import (
    LKS_PG_BakeGroup,
    LKS_PG_BakeProject,
    get_active_bake_project,
    read_active_bake_group_index,
)


class LKS_OT_GenerateExtractedHighpoly(bpy.types.Operator):
    """(Temporary) Duplicate highs, deep-apply, and extract unmerged meshes per bake group."""
    bl_idname = 'object.lks_generate_extracted_highpoly'
    bl_label = 'Generate Extracted Highpoly (Temp)'
    bl_options = {'REGISTER', 'UNDO'}

    all_groups: bpy.props.BoolProperty(
        name='All Groups',
        description='Process every bake group in the active project (otherwise active group only)',
        default=False,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.area is None or context.area.type != 'VIEW_3D':
            return False
        project = get_active_bake_project(context.scene)
        if project is None or len(project.bake_groups) == 0:
            return False
        if cls._poll_all_groups(context, project):
            return True
        group = cls._active_group(project)
        return group is not None and bake_group_high_has_flatten_geometry(project, group)

    @classmethod
    def _active_group(
        cls,
        project: LKS_PG_BakeProject,
    ) -> LKS_PG_BakeGroup | None:
        index = read_active_bake_group_index(project)
        if not (0 <= index < len(project.bake_groups)):
            return None
        return project.bake_groups[index]

    @classmethod
    def _poll_all_groups(
        cls,
        context: bpy.types.Context,
        project,
    ) -> bool:
        _ = context
        return any(
            bake_group_high_has_flatten_geometry(project, group)
            for group in project.bake_groups
        )

    def execute(self, context: bpy.types.Context) -> set[str]:
        project = get_active_bake_project(context.scene, write_back=True)
        if project is None:
            self.report({'ERROR'}, 'No active bake project')
            return {'CANCELLED'}

        if self.all_groups:
            extracted = generate_extracted_highpoly_for_bake_groups(context, project)
            if not extracted:
                self.report({'ERROR'}, 'No bake groups produced extracted highpoly meshes')
                return {'CANCELLED'}
            self.report(
                {'INFO'},
                f'Generated {len(extracted)} extracted highpoly mesh(es)',
            )
            return {'FINISHED'}

        group = self._active_group(project)
        if group is None:
            self.report({'ERROR'}, 'No active bake group')
            return {'CANCELLED'}

        results = generate_extracted_highpoly_for_bake_group(context, project, group)
        if not results:
            self.report(
                {'ERROR'},
                f"No extracted highpoly produced for '{group.name}'",
            )
            return {'CANCELLED'}

        coll_name = group.high_collection.name if group.high_collection else 'high collection'
        self.report(
            {'INFO'},
            f'Extracted {len(results)} highpoly mesh(es) in {coll_name}',
        )
        return {'FINISHED'}

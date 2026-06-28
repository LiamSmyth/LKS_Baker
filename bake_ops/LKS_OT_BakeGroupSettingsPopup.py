"""Popup for static bake group configuration (gear icon on group rows)."""

from __future__ import annotations

import bpy

from .static_utilities.bake_resolution_helpers import (
    format_project_default_resolution,
)
from .lks_bake_props import LKS_PG_BakeGroup, LKS_PG_BakeProject


def _resolve_group(
    scene: bpy.types.Scene,
    project_index: int,
    group_index: int,
) -> tuple[LKS_PG_BakeProject, LKS_PG_BakeGroup] | None:
    if not (0 <= project_index < len(scene.lks_bake_projects)):
        return None
    project = scene.lks_bake_projects[project_index]
    if not (0 <= group_index < len(project.bake_groups)):
        return None
    return project, project.bake_groups[group_index]


def _effective_resolution_label(project: LKS_PG_BakeProject, bake_group: LKS_PG_BakeGroup) -> str:
    if bake_group.resolution_override > 0:
        return str(bake_group.resolution_override)
    return format_project_default_resolution(project)


def _effective_samples(project: LKS_PG_BakeProject, bake_group: LKS_PG_BakeGroup) -> int:
    if bake_group.bake_samples_override > 0:
        return bake_group.bake_samples_override
    return project.default_bake_samples


def draw_bake_group_settings(
    layout: bpy.types.UILayout,
    project: LKS_PG_BakeProject,
    bake_group: LKS_PG_BakeGroup,
) -> None:
    """Draw static group configuration into a popup or panel body."""
    export_header, export_body = layout.panel(
        'lks_bake_group_settings_export',
        default_closed=False,
    )
    if export_header:
        export_header.label(text='Export', icon='EXPORT')
    if export_body:
        export_body.prop(bake_group, 'export_mode', text='Export Mode')
        export_body.label(
            text=f'Output: {project.output_dir or "(not set)"}',
            icon='FILE_FOLDER',
        )

    layout.separator()

    override_header, override_body = layout.panel(
        'lks_bake_group_settings_overrides',
        default_closed=False,
    )
    if override_header:
        override_header.label(text='Bake Overrides', icon='RENDER_STILL')
    if override_body:
        override_body.label(
            text=f'Project defaults: {format_project_default_resolution(project)} / {project.default_bake_samples} samples',
            icon='INFO',
        )
        res_row = override_body.row(align=True)
        res_row.prop(bake_group, 'resolution_override', text='Resolution')
        res_row.label(text=f'→ {_effective_resolution_label(project, bake_group)}')
        smp_row = override_body.row(align=True)
        smp_row.prop(bake_group, 'bake_samples_override', text='Samples')
        smp_row.label(text=f'→ {_effective_samples(project, bake_group)}')


class LKS_OT_BakeGroupSettingsPopup(bpy.types.Operator):
    """Edit static bake group settings."""
    bl_idname = 'object.lks_bake_group_settings_popup'
    bl_label = 'Bake Group Settings'
    bl_options = {'INTERNAL'}

    project_index: bpy.props.IntProperty(name='Project Index', default=-1)
    group_index: bpy.props.IntProperty(name='Group Index', default=-1)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if _resolve_group(context.scene, self.project_index, self.group_index) is None:
            self.report({'WARNING'}, 'Bake group not found')
            return {'CANCELLED'}
        return context.window_manager.invoke_popup(self, width=320)

    def draw(self, context: bpy.types.Context) -> None:
        resolved = _resolve_group(context.scene, self.project_index, self.group_index)
        if resolved is None:
            self.layout.label(text='Bake group not found', icon='ERROR')
            return
        project, bake_group = resolved
        self.layout.label(text=bake_group.name or '(unnamed)', icon='OUTLINER_COLLECTION')
        self.layout.separator()
        draw_bake_group_settings(self.layout, project, bake_group)

    def execute(self, context: bpy.types.Context) -> set[str]:
        return {'FINISHED'}

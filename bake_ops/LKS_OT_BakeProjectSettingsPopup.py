"""Popup for static bake project configuration (gear icon on project rows)."""

from __future__ import annotations

import bpy

from .static_utilities.bake_map_catalog import (
    BAKE_MAP_CATEGORY_COLUMNS,
    BAKE_MAP_CATEGORY_LABELS,
    iter_catalog_specs_for_category,
)
from .static_utilities.bake_resolution_helpers import draw_linked_texture_resolution_row
from .helpers_bake_cleanup import schedule_bake_map_catalog_seed_if_needed
from .LKS_OT_ReapplyBakePreviewMaterial import LKS_OT_ReapplyBakePreviewMaterial
from .LKS_UL_BakeMaps import bake_maps_uilist_for_category
from .lks_bake_props import LKS_PG_BakeProject


def _resolve_project(
    scene: bpy.types.Scene,
    project_index: int,
) -> LKS_PG_BakeProject | None:
    if 0 <= project_index < len(scene.lks_bake_projects):
        return scene.lks_bake_projects[project_index]
    return None


def _enabled_map_count(project: LKS_PG_BakeProject) -> int:
    return sum(1 for entry in project.map_entries if entry.enabled)


def draw_texture_output_properties(
    layout: bpy.types.UILayout,
    project: LKS_PG_BakeProject,
) -> None:
    """Draw project-level texture output defaults in the base panel."""
    header, body = layout.panel(
        'lks_bake_project_texture_output',
        default_closed=False,
    )
    if header:
        header.label(text='Texture Outputs', icon='FILE_IMAGE')
    if body:
        format_row = body.row(align=True)
        format_row.prop(project, 'lks_image_file_type', text='Format')
        format_row.prop(project, 'lks_image_color_depth', text='Depth')
        draw_linked_texture_resolution_row(
            body,
            project,
            x_prop='default_resolution_x',
            y_prop='default_resolution_y',
            linked_prop='default_resolution_linked',
            linked=project.default_resolution_linked,
        )
        body.prop(project, 'default_bake_samples', text='Samples')
        body.prop(project, 'default_bake_margin', text='Margin')
        body.prop(project, 'default_bake_margin_pre_erode', text='Pre-Erode')


def _rows_for_category(category: str) -> int:
    count = len(iter_catalog_specs_for_category(category))
    return max(2, count) if count else 2


def _draw_bake_maps_subsection(
    layout: bpy.types.UILayout,
    project: LKS_PG_BakeProject,
    project_index: int,
    category: str,
) -> None:
    subsection = layout.column(align=True)
    subsection.label(text=BAKE_MAP_CATEGORY_LABELS.get(category, category))
    uilist_cls = bake_maps_uilist_for_category(category)
    subsection.template_list(
        uilist_cls.bl_idname,
        f'lks_bake_maps_{project_index}_{category}',
        project,
        'map_entries',
        project,
        'active_bake_map_index',
        rows=_rows_for_category(category),
    )


def draw_bake_project_maps_list(
    layout: bpy.types.UILayout,
    project: LKS_PG_BakeProject,
    project_index: int,
    *,
    scene: bpy.types.Scene,
) -> None:
    """Draw per-map UILists in two columns with subsection headers."""
    maps_header, maps_body = layout.panel(
        'lks_bake_project_maps',
        default_closed=False,
    )
    if maps_header:
        header_row = maps_header.row(align=True)
        header_row.label(
            text=f'Bakes ({_enabled_map_count(project)} enabled)',
            icon='TEXTURE',
        )
        reapply_op = header_row.operator(
            LKS_OT_ReapplyBakePreviewMaterial.bl_idname,
            text='',
            icon='SHADING_RENDERED',
        )
        reapply_op.project_index = project_index
    if maps_body:
        schedule_bake_map_catalog_seed_if_needed(scene, project)
        maps_row = maps_body.row()
        left_col = maps_row.column()
        right_col = maps_row.column()
        for col_index, column_categories in enumerate(BAKE_MAP_CATEGORY_COLUMNS):
            column = left_col if col_index == 0 else right_col
            for category in column_categories:
                _draw_bake_maps_subsection(column, project, project_index, category)


def draw_bake_project_settings(layout: bpy.types.UILayout, project: LKS_PG_BakeProject) -> None:
    """Draw static project configuration into a popup or panel body."""
    export_header, export_body = layout.panel(
        'lks_bake_project_settings_export',
        default_closed=False,
    )
    if export_header:
        export_header.label(text='Export & Naming', icon='EXPORT')
    if export_body:
        export_body.prop(project, 'export_mode', text='Export Mode')
        naming = export_body.box()
        naming.label(text='Texture Naming', icon='FILE_IMAGE')
        prefix_row = naming.row(align=True)
        prefix_row.prop(project, 'lks_material_prefix', text='Prefix')
        prefix_row.prop(project, 'lks_material_suffix', text='Suffix')

    layout.separator()

    bake_header, bake_body = layout.panel(
        'lks_bake_project_settings_bake',
        default_closed=False,
    )
    if bake_header:
        bake_header.label(text='Bake Settings', icon='RENDER_STILL')
    if bake_body:
        bake_body.prop(project, 'bake_mode', text='Bake Mode')
        cage_row = bake_body.row(align=True)
        cage_row.prop(project, 'use_cage', text='Cage')
        cage_row.prop(project, 'cage_extrusion', text='Extrusion')
        dist_row = bake_body.row(align=True)
        dist_row.prop(project, 'max_ray_distance', text='Max Ray')
        bake_body.prop(project, 'use_gpu_bake', text='GPU Bake')


class LKS_OT_BakeProjectSettingsPopup(bpy.types.Operator):
    """Edit static bake project settings."""
    bl_idname = 'object.lks_bake_project_settings_popup'
    bl_label = 'Bake Project Settings'
    bl_options = {'INTERNAL'}

    project_index: bpy.props.IntProperty(name='Project Index', default=-1)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if _resolve_project(context.scene, self.project_index) is None:
            self.report({'WARNING'}, 'Bake project not found')
            return {'CANCELLED'}
        return context.window_manager.invoke_popup(self, width=360)

    def draw(self, context: bpy.types.Context) -> None:
        project = _resolve_project(context.scene, self.project_index)
        if project is None:
            self.layout.label(text='Bake project not found', icon='ERROR')
            return
        self.layout.label(text=project.name or '(unnamed)', icon='FILE_CACHE')
        self.layout.separator()
        draw_bake_project_settings(self.layout, project)

    def execute(self, context: bpy.types.Context) -> set[str]:
        return {'FINISHED'}

"""Popup for per-map bake overrides (gear icon on map rows)."""

from __future__ import annotations

import bpy

from .static_utilities.bake_map_catalog import get_map_display_label, get_bake_map_spec
from .static_utilities.bake_method_catalog import map_has_method_selector
from .static_utilities.bake_method_cfg_router import draw_bake_method_settings
from .static_utilities.bake_post_process_ui import draw_bake_post_process_settings
from .static_utilities.bake_margin_helpers import (
    resolve_bake_margin_pixels,
    resolve_effective_margin,
    resolve_margin_pre_erode_pixels,
)
from .static_utilities.bake_resolution_helpers import (
    format_project_default_resolution,
    resolve_bake_texture_dimensions,
)
from .lks_bake_props import LKS_PG_BakeMapEntry, LKS_PG_BakeProject


def _resolve_map_entry(
    scene: bpy.types.Scene,
    project_index: int,
    map_id: str,
) -> tuple[LKS_PG_BakeProject, LKS_PG_BakeMapEntry] | None:
    if not map_id or not (0 <= project_index < len(scene.lks_bake_projects)):
        return None
    project = scene.lks_bake_projects[project_index]
    for entry in project.map_entries:
        if entry.map_id == map_id:
            return project, entry
    return None


def _effective_resolution_label(project: LKS_PG_BakeProject, entry: LKS_PG_BakeMapEntry) -> str:
    width, height = resolve_bake_texture_dimensions(project, entry)
    if entry.resolution > 0:
        return str(entry.resolution)
    if width == height:
        return f'{width}px'
    return f'{width}×{height}px'


def _effective_samples(project: LKS_PG_BakeProject, entry: LKS_PG_BakeMapEntry) -> int:
    if entry.samples > 0:
        return entry.samples
    return project.default_bake_samples


def _effective_margin_label(project: LKS_PG_BakeProject, entry: LKS_PG_BakeMapEntry) -> str:
    width, height = resolve_bake_texture_dimensions(project, entry)
    effective = resolve_effective_margin(entry, project)
    if effective == 0:
        return 'none'
    if effective < 0:
        pixels = resolve_bake_margin_pixels(entry, width, height, project)
        return f'{pixels}px (∞)'
    return f'{effective}px'


def _effective_margin_pre_erode_label(project: LKS_PG_BakeProject, entry: LKS_PG_BakeMapEntry) -> str:
    pixels = resolve_margin_pre_erode_pixels(entry, project)
    if pixels <= 0:
        return 'off'
    return f'{pixels}px'


def draw_bake_map_settings(
    layout: bpy.types.UILayout,
    project: LKS_PG_BakeProject,
    entry: LKS_PG_BakeMapEntry,
) -> None:
    """Draw per-map override fields into a popup or panel body."""
    _dm = project.default_bake_margin
    _margin_text = '∞' if _dm < 0 else ('none' if _dm == 0 else f'{_dm}px')
    _pre_erode = project.default_bake_margin_pre_erode
    _pre_erode_text = 'off' if _pre_erode <= 0 else f'{_pre_erode}px'
    layout.label(
        text=(
            f'Project defaults: {format_project_default_resolution(project)} / '
            f'{project.default_bake_samples} smp / {_margin_text} margin / '
            f'{_pre_erode_text} pre-erode'
        ),
        icon='INFO',
    )
    res_row = layout.row(align=True)
    res_row.prop(entry, 'resolution', text='Resolution')
    res_row.label(text=f'→ {_effective_resolution_label(project, entry)}')
    sm_row = layout.row(align=True)
    sm_row.prop(entry, 'samples', text='Samples')
    sm_row.label(text=f'→ {_effective_samples(project, entry)}')
    sm_row.prop(entry, 'margin', text='Margin')
    sm_row.label(text=f'→ {_effective_margin_label(project, entry)}')
    erode_row = layout.row(align=True)
    erode_row.prop(entry, 'lks_bake_margin_pre_erode', text='Pre-Erode')
    erode_row.label(text=f'→ {_effective_margin_pre_erode_label(project, entry)}')
    layout.label(
        text=(
            'Margin: 0 = project default (−1 = ∞ fill). '
            'Pre-Erode: shrink seed mask inward (0 = project default, higher = deeper rim trim)'
        ),
        icon='INFO',
    )
    if map_has_method_selector(entry.map_id):
        layout.prop(entry, 'lks_bake_method', text='Method')
        spec = get_bake_map_spec(entry.map_id)
        if spec is not None and spec.derive_from:
            parents = ', '.join(spec.derive_from)
            layout.label(text=f'Derives from: {parents}', icon='LINKED')
        draw_bake_method_settings(layout, entry, project)
    draw_bake_post_process_settings(layout, entry)


class LKS_OT_BakeMapSettingsPopup(bpy.types.Operator):
    """Edit per-map bake overrides."""
    bl_idname = 'object.lks_bake_map_settings_popup'
    bl_label = 'Bake Map Settings'
    bl_options = {'INTERNAL'}

    project_index: bpy.props.IntProperty(name='Project Index', default=-1)
    map_id: bpy.props.StringProperty(name='Map ID', default='')

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.area is not None and context.area.type == 'VIEW_3D'

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if _resolve_map_entry(context.scene, self.project_index, self.map_id) is None:
            self.report({'WARNING'}, 'Bake map entry not found')
            return {'CANCELLED'}
        return context.window_manager.invoke_popup(self, width=320)

    def draw(self, context: bpy.types.Context) -> None:
        resolved = _resolve_map_entry(context.scene, self.project_index, self.map_id)
        if resolved is None:
            self.layout.label(text='Bake map entry not found', icon='ERROR')
            return
        project, entry = resolved
        label = get_map_display_label(entry.map_id)
        self.layout.label(text=label, icon='TEXTURE')
        draw_bake_map_settings(self.layout, project, entry)

    def execute(self, context: bpy.types.Context) -> set[str]:
        return {'FINISHED'}


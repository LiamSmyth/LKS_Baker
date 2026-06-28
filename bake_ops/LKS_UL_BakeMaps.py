"""UIList for bake map entries on the active LKS BakeProject."""

from __future__ import annotations

import bpy

from .static_utilities.bake_map_catalog import (
    get_bake_map_spec,
    get_map_display_label,
)
from .static_utilities.bake_blender_helpers import map_id_is_bakeable
from .static_utilities.bake_preview_material_helpers import bake_map_image_exists_on_disk
from .LKS_OT_BakeMapSettingsPopup import LKS_OT_BakeMapSettingsPopup
from .LKS_OT_ToggleBakeMapPreview import LKS_OT_ToggleBakeMapPreview
from .lks_bake_props import LKS_PG_BakeMapEntry, LKS_PG_BakeProject


def _project_index(context: bpy.types.Context, project: LKS_PG_BakeProject) -> int:
    for index, scene_project in enumerate(context.scene.lks_bake_projects):
        if scene_project == project:
            return index
    return -1


def _entry_matches_category(entry: LKS_PG_BakeMapEntry, category: str) -> bool:
    spec = get_bake_map_spec(entry.map_id)
    return spec is not None and spec.category == category


class LKS_UL_BakeMaps(bpy.types.UIList):
    """Bake map rows: enable toggle, catalog label, gear for per-map overrides."""

    bl_idname = 'LKS_UL_BakeMaps'
    bake_map_category: str = ''

    def filter_items(
        self,
        context: bpy.types.Context,
        data: bpy.types.Any,
        propname: str,
    ) -> tuple[list[int], list[int]]:
        category = self.bake_map_category
        if not category:
            return [], []

        items = getattr(data, propname)
        flt_flags = [
            self.bitflag_filter_item
            if _entry_matches_category(item, category)
            else 0
            for item in items
        ]
        return flt_flags, []

    def sort_items(
        self,
        context: bpy.types.Context,
        data: bpy.types.Any,
        propname: str,
    ) -> list[int]:
        items = getattr(data, propname)

        def _sort_order(_index: int, item: LKS_PG_BakeMapEntry) -> int:
            spec = get_bake_map_spec(item.map_id)
            return spec.sort_order if spec is not None else 9999

        return bpy.types.UI_UL_list.sort_items_helper(
            items,
            [(_sort_order, False), (lambda _i, item: item.map_id, False)],
        )

    def draw_item(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        data: bpy.types.Any,
        item: bpy.types.Any,
        icon: int,
        active_data: bpy.types.Any,
        active_propname: str,
        index: int,
        flt_flag: int,
    ) -> None:
        entry: LKS_PG_BakeMapEntry = item
        project: LKS_PG_BakeProject = data
        project_index = _project_index(context, project)
        label = get_map_display_label(entry.map_id)
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(entry, 'enabled', text='')
            row.label(text=label)

            actions = row.row(align=True)
            actions.alignment = 'RIGHT'

            preview_active = project.lks_preview_map_id == entry.map_id
            has_preview_image = bake_map_image_exists_on_disk(project, entry.map_id)
            preview_icon = 'HIDE_OFF' if preview_active else 'HIDE_ON'
            preview_row = actions.row(align=True)
            preview_row.active = has_preview_image
            preview_op = preview_row.operator(
                LKS_OT_ToggleBakeMapPreview.bl_idname,
                text='',
                icon=preview_icon,
                depress=preview_active,
                emboss=False,
            )
            preview_op.project_index = project_index
            preview_op.map_id = entry.map_id

            bake_row = actions.row(align=True)
            bake_row.enabled = map_id_is_bakeable(entry.map_id)
            bake_op = bake_row.operator(
                f'object.lks_bake_map_{entry.map_id}',
                text='',
                icon='RENDER_STILL',
                emboss=False,
            )
            bake_op.project_index = project_index

            settings_op = actions.operator(
                LKS_OT_BakeMapSettingsPopup.bl_idname,
                text='',
                icon='PREFERENCES',
                emboss=False,
            )
            settings_op.project_index = project_index
            settings_op.map_id = entry.map_id
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            icon_id = 'CHECKMARK' if entry.enabled else 'BLANK1'
            layout.label(text=label, icon=icon_id)


class LKS_UL_BakeMapsSurface(LKS_UL_BakeMaps):
    bl_idname = 'LKS_UL_BakeMapsSurface'
    bake_map_category = 'surface'


class LKS_UL_BakeMapsLighting(LKS_UL_BakeMaps):
    bl_idname = 'LKS_UL_BakeMapsLighting'
    bake_map_category = 'lighting'


class LKS_UL_BakeMapsMasks(LKS_UL_BakeMaps):
    bl_idname = 'LKS_UL_BakeMapsMasks'
    bake_map_category = 'masks'


class LKS_UL_BakeMapsPbr(LKS_UL_BakeMaps):
    bl_idname = 'LKS_UL_BakeMapsPbr'
    bake_map_category = 'pbr'


_BAKE_MAPS_UILIST_BY_CATEGORY: dict[str, type[LKS_UL_BakeMaps]] = {
    'surface': LKS_UL_BakeMapsSurface,
    'lighting': LKS_UL_BakeMapsLighting,
    'masks': LKS_UL_BakeMapsMasks,
    'pbr': LKS_UL_BakeMapsPbr,
}


def bake_maps_uilist_for_category(category: str) -> type[LKS_UL_BakeMaps]:
    return _BAKE_MAPS_UILIST_BY_CATEGORY[category]

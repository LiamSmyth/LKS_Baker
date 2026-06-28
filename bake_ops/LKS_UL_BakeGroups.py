"""UIList for bake groups in the active LKS BakeProject."""

from __future__ import annotations

import bpy

from .LKS_OT_BakeGroupSettingsPopup import LKS_OT_BakeGroupSettingsPopup
from .LKS_OT_ExportBakeGroup import LKS_OT_ExportBakeGroup
from .LKS_OT_RemoveBakeGroup import LKS_OT_RemoveBakeGroup
from .LKS_OT_SelectBakeGroupContents import LKS_OT_SelectBakeGroupContents
from .LKS_OT_ToggleBakeGroupVisibility import LKS_OT_ToggleBakeGroupVisibility
from .LKS_OT_ToggleBakeRoleVisibility import (
    LKS_OT_ToggleBakeGroupHighVisibility,
    LKS_OT_ToggleBakeGroupLowVisibility,
)
from .helpers_bake_cleanup import bake_group_any_visible, bake_group_role_any_visible
from .lks_bake_props import LKS_PG_BakeProject


def _project_index(context: bpy.types.Context, project: LKS_PG_BakeProject) -> int:
    for index, scene_project in enumerate(context.scene.lks_bake_projects):
        if scene_project == project:
            return index
    return -1


class LKS_UL_BakeGroups(bpy.types.UIList):
    """Minimal bake group rows: name + compact inline action icons."""

    bl_idname = 'LKS_UL_BakeGroups'

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
        bake_group = item
        project: LKS_PG_BakeProject = data
        project_index = _project_index(context, project)
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=bake_group.name or '(unnamed)')

            actions = row.row(align=True)
            actions.alignment = 'RIGHT'

            high_op = actions.operator(
                LKS_OT_ToggleBakeGroupHighVisibility.bl_idname,
                text='H',
                depress=bake_group_role_any_visible(
                    project,
                    bake_group,
                    role='high',
                ),
                emboss=False,
            )
            high_op.project_index = project_index
            high_op.group_index = index
            low_op = actions.operator(
                LKS_OT_ToggleBakeGroupLowVisibility.bl_idname,
                text='L',
                depress=bake_group_role_any_visible(
                    project,
                    bake_group,
                    role='low',
                ),
                emboss=False,
            )
            low_op.project_index = project_index
            low_op.group_index = index

            export_op = actions.operator(
                LKS_OT_ExportBakeGroup.bl_idname,
                text='',
                icon='EXPORT',
                emboss=False,
            )
            export_op.project_index = project_index
            export_op.group_index = index
            export_op.export_mode = bake_group.export_mode

            vis_icon = (
                'HIDE_OFF'
                if bake_group_any_visible(project, bake_group)
                else 'HIDE_ON'
            )
            vis_op = actions.operator(
                LKS_OT_ToggleBakeGroupVisibility.bl_idname,
                text='',
                icon=vis_icon,
                emboss=False,
            )
            vis_op.project_index = project_index
            vis_op.group_index = index

            select_op = actions.operator(
                LKS_OT_SelectBakeGroupContents.bl_idname,
                text='',
                icon='RESTRICT_SELECT_OFF',
                emboss=False,
            )
            select_op.project_index = project_index
            select_op.group_index = index

            settings_op = actions.operator(
                LKS_OT_BakeGroupSettingsPopup.bl_idname,
                text='',
                icon='PREFERENCES',
                emboss=False,
            )
            settings_op.project_index = project_index
            settings_op.group_index = index

            remove_op = actions.operator(
                LKS_OT_RemoveBakeGroup.bl_idname,
                text='',
                icon='X',
                emboss=False,
            )
            remove_op.project_index = project_index
            remove_op.group_index = index
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=bake_group.name or '(unnamed)', icon='OUTLINER_COLLECTION')

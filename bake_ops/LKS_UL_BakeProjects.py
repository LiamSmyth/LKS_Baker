"""UIList for scene-level LKS bake projects."""

from __future__ import annotations

import bpy

from .LKS_OT_BakeBakeProject import LKS_OT_BakeBakeProject
from .LKS_OT_BakeProjectSettingsPopup import LKS_OT_BakeProjectSettingsPopup
from .LKS_OT_ExportBakeProject import LKS_OT_ExportBakeProject
from .LKS_OT_RemoveBakeProject import LKS_OT_RemoveBakeProject
from .LKS_OT_SelectBakeProjectContents import LKS_OT_SelectBakeProjectContents
from .LKS_OT_ToggleBakeProjectVisibility import LKS_OT_ToggleBakeProjectVisibility
from .LKS_OT_ToggleBakeRoleVisibility import (
    LKS_OT_ToggleBakeProjectHighVisibility,
    LKS_OT_ToggleBakeProjectLowVisibility,
)
from .helpers_bake_cleanup import bake_project_any_visible, bake_project_role_any_visible


class LKS_UL_BakeProjects(bpy.types.UIList):
    """Minimal bake project rows: name + compact inline action icons."""

    bl_idname = 'LKS_UL_BakeProjects'

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
        project = item
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=project.name or '(unnamed)')

            actions = row.row(align=True)
            actions.alignment = 'RIGHT'

            high_op = actions.operator(
                LKS_OT_ToggleBakeProjectHighVisibility.bl_idname,
                text='H',
                depress=bake_project_role_any_visible(project, role='high'),
                emboss=False,
            )
            high_op.project_index = index
            low_op = actions.operator(
                LKS_OT_ToggleBakeProjectLowVisibility.bl_idname,
                text='L',
                depress=bake_project_role_any_visible(project, role='low'),
                emboss=False,
            )
            low_op.project_index = index

            export_op = actions.operator(
                LKS_OT_ExportBakeProject.bl_idname,
                text='',
                icon='EXPORT',
                emboss=False,
            )
            export_op.project_index = index
            export_op.export_mode = project.export_mode

            bake_op = actions.operator(
                LKS_OT_BakeBakeProject.bl_idname,
                text='',
                icon='RENDER_STILL',
                emboss=False,
            )
            bake_op.project_index = index

            vis_icon = 'HIDE_OFF' if bake_project_any_visible(project) else 'HIDE_ON'
            vis_op = actions.operator(
                LKS_OT_ToggleBakeProjectVisibility.bl_idname,
                text='',
                icon=vis_icon,
                emboss=False,
            )
            vis_op.project_index = index

            select_op = actions.operator(
                LKS_OT_SelectBakeProjectContents.bl_idname,
                text='',
                icon='RESTRICT_SELECT_OFF',
                emboss=False,
            )
            select_op.project_index = index

            settings_op = actions.operator(
                LKS_OT_BakeProjectSettingsPopup.bl_idname,
                text='',
                icon='PREFERENCES',
                emboss=False,
            )
            settings_op.project_index = index

            remove_op = actions.operator(
                LKS_OT_RemoveBakeProject.bl_idname,
                text='',
                icon='X',
                emboss=False,
            )
            remove_op.project_index = index
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=project.name or '(unnamed)', icon='FILE_CACHE')

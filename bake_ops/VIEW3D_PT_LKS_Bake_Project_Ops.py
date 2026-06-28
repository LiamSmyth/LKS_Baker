"""Top-level LKS sidebar panel for BakeProject scaffolding."""

from __future__ import annotations

import bpy

from .LKS_OT_AddSelectionToBakeGroup import LKS_OT_AddSelectionToBakeGroup
from .LKS_OT_ApplyBakeLowMaterialTest import LKS_OT_ApplyBakeLowMaterialTest
from .LKS_OT_AddSelectionToBakeProject import LKS_OT_AddSelectionToBakeProject
from .LKS_OT_AssignToBakeGroup import LKS_OT_AssignToBakeGroup
from .LKS_OT_GenerateExtractedHighpoly import LKS_OT_GenerateExtractedHighpoly
from .LKS_OT_GenerateMergedLowpoly import LKS_OT_GenerateMergedLowpoly
from .LKS_OT_NewBakeGroup import LKS_OT_NewBakeGroup
from .LKS_OT_NewBakeProject import LKS_OT_NewBakeProject
from .LKS_OT_SetBakeRoleHigh import LKS_OT_SetBakeRoleHigh
from .LKS_OT_SetBakeRoleLow import LKS_OT_SetBakeRoleLow
from .LKS_OT_BakeProjectSettingsPopup import (
    draw_bake_project_maps_list,
    draw_texture_output_properties,
)
from .LKS_OT_UnassignFromBakeGroup import LKS_OT_UnassignFromBakeGroup
from .LKS_UL_BakeGroupHighs import LKS_UL_BakeGroupHighs
from .LKS_UL_BakeGroupLows import LKS_UL_BakeGroupLows
from .LKS_UL_BakeGroups import LKS_UL_BakeGroups
from .LKS_UL_BakeProjects import LKS_UL_BakeProjects
from .helpers_bake_cleanup import (
    ensure_bake_group_ui_slots,
    iter_bake_group_high_objects,
    iter_bake_group_low_objects,
    resolve_object_bake_role_label,
)
from .helpers_bake_prep import (
    bake_group_high_has_flatten_geometry,
    bake_group_low_has_flatten_geometry,
)
from .lks_bake_props import (
    LKS_PG_BakeGroup,
    LKS_PG_BakeProject,
    get_active_bake_project,
    read_active_bake_group_index,
    read_active_bake_project_index,
)
from .static_utilities.bake_progress_helpers import draw_bake_progress_bar


def _draw_bake_group_properties(
    layout: bpy.types.UILayout,
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    bake_group: LKS_PG_BakeGroup,
    *,
    project_index: int,
    group_index: int,
) -> None:
    layout.prop(bake_group, 'name', text='Name')

    action_row = layout.row(align=True)
    action_row.operator(LKS_OT_AssignToBakeGroup.bl_idname)
    action_row.operator(LKS_OT_UnassignFromBakeGroup.bl_idname)
    active = context.active_object
    action_row.operator(
        LKS_OT_SetBakeRoleHigh.bl_idname,
        depress=(
            active is not None
            and resolve_object_bake_role_label(project, bake_group, active) == 'high'
        ),
    )
    action_row.operator(
        LKS_OT_SetBakeRoleLow.bl_idname,
        depress=(
            active is not None
            and resolve_object_bake_role_label(project, bake_group, active) == 'low'
        ),
    )

    high_count = len(iter_bake_group_high_objects(project, bake_group))
    low_count = len(iter_bake_group_low_objects(project, bake_group))
    list_rows = min(6, max(2, max(high_count, low_count, 1)))

    if high_count == 0 and low_count == 0:
        layout.label(text='No high or low objects assigned', icon='INFO')
    else:
        layout.separator()
        ensure_bake_group_ui_slots(bake_group)
        row = layout.row()
        split = row.split(factor=0.5)
        col_high = split.column()
        col_high.label(text='Highs', icon='TRIA_UP')
        col_high.template_list(
            LKS_UL_BakeGroupHighs.bl_idname,
            f'lks_bake_group_highs_{project_index}_{group_index}',
            bake_group,
            'ui_list_slots',
            bake_group,
            'active_high_index',
            rows=list_rows,
        )
        col_low = split.column()
        col_low.label(text='Lows', icon='TRIA_DOWN')
        col_low.template_list(
            LKS_UL_BakeGroupLows.bl_idname,
            f'lks_bake_group_lows_{project_index}_{group_index}',
            bake_group,
            'ui_list_slots',
            bake_group,
            'active_low_index',
            rows=list_rows,
        )

def _draw_bake_debug_section(
    layout: bpy.types.UILayout,
    project: LKS_PG_BakeProject,
) -> None:
    debug_header, debug_body = layout.panel('lks_bake_ops_debug', default_closed=True)
    if debug_header:
        debug_header.label(text='Debug', icon='CONSOLE')
    if debug_body:
        debug_body.operator(
            LKS_OT_ApplyBakeLowMaterialTest.bl_idname,
            text='Apply Bake Low Material (Test)',
            icon='MATERIAL',
        )

        active_group_index = read_active_bake_group_index(project)
        bake_group = None
        if 0 <= active_group_index < len(project.bake_groups):
            bake_group = project.bake_groups[active_group_index]

        prep_row = debug_body.row(align=True)
        prep_row.enabled = (
            bake_group is not None
            and bake_group_low_has_flatten_geometry(project, bake_group)
        )
        prep_row.operator(
            LKS_OT_GenerateMergedLowpoly.bl_idname,
            text='Generate Merged Lowpoly (Temp)',
            icon='MOD_BOOLEAN',
        )

        high_prep_row = debug_body.row(align=True)
        high_prep_row.enabled = (
            bake_group is not None
            and bake_group_high_has_flatten_geometry(project, bake_group)
        )
        high_prep_row.operator(
            LKS_OT_GenerateExtractedHighpoly.bl_idname,
            text='Generate Extracted Highpoly (Temp)',
            icon='MOD_BOOLEAN',
        )


class VIEW3D_PT_LKS_Bake_Project_Ops(bpy.types.Panel):
    """Bake project panel — sibling to Export/Import, Mesh Ops, etc."""

    bl_idname = 'VIEW3D_PT_LKS_Bake_Project_Ops'
    bl_label = 'Bake Ops'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'LKS Baker'

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        draw_bake_progress_bar(layout, context)
        scene = context.scene
        projects = scene.lks_bake_projects
        active_index = read_active_bake_project_index(scene)
        project = get_active_bake_project(scene)

        top_row = layout.row(align=True)
        top_row.operator(LKS_OT_NewBakeProject.bl_idname, icon='ADD')
        top_row.operator(LKS_OT_AddSelectionToBakeProject.bl_idname, icon='OUTLINER_OB_MESH')

        if len(projects) == 0:
            layout.label(
                text='No bake projects — use New Bake Project or From Selected',
                icon='INFO',
            )
            return

        layout.template_list(
            LKS_UL_BakeProjects.bl_idname,
            'lks_bake_projects',
            scene,
            'lks_bake_projects',
            scene,
            'lks_active_bake_project_index',
            rows=min(6, max(3, len(projects))),
        )

        if project is None:
            return

        layout.separator()

        panel_id = f'lks_bake_project_props_{active_index}'
        header, body = layout.panel(panel_id, default_closed=False)
        if header:
            header.label(text='Bake Project', icon='PROPERTIES')
        if body:
            identity_box = body.box()
            name_row = identity_box.row(align=True)
            name_row.prop(project, 'name', text='Name')
            name_row.prop(project, 'output_dir', text='Output')

            body.separator()

            outputs_box = body.box()
            draw_texture_output_properties(outputs_box, project)
            outputs_box.separator()
            draw_bake_project_maps_list(outputs_box, project, active_index, scene=scene)

            body.separator(factor=1.5)

            groups_box = body.box()
            groups_box.label(text='Bake Groups', icon='OUTLINER_COLLECTION')
            group_row = groups_box.row(align=True)
            group_row.operator(LKS_OT_NewBakeGroup.bl_idname, icon='ADD')
            group_row.operator(LKS_OT_AddSelectionToBakeGroup.bl_idname, icon='OUTLINER_OB_MESH')

            if len(project.bake_groups) == 0:
                groups_box.label(text='No bake groups', icon='BLANK1')
            else:
                groups_box.template_list(
                    LKS_UL_BakeGroups.bl_idname,
                    f'lks_bake_groups_{active_index}',
                    project,
                    'bake_groups',
                    project,
                    'active_bake_group_index',
                    rows=min(4, max(1, len(project.bake_groups))),
                )

                active_group_index = read_active_bake_group_index(project)
                if 0 <= active_group_index < len(project.bake_groups):
                    bake_group = project.bake_groups[active_group_index]
                    groups_box.separator()
                    group_panel_id = (
                        f'lks_bake_group_props_{active_index}_{active_group_index}'
                    )
                    g_header, g_body = groups_box.panel(group_panel_id, default_closed=False)
                    if g_header:
                        g_header.label(
                            text='Bake Group',
                            icon='PROPERTIES',
                        )
                    if g_body:
                        _draw_bake_group_properties(
                            g_body,
                            context,
                            project,
                            bake_group,
                            project_index=active_index,
                            group_index=active_group_index,
                        )
                else:
                    groups_box.label(text='Select a bake group', icon='INFO')

        _draw_bake_debug_section(layout, project)


def register_props() -> None:
    pass


def unregister_props() -> None:
    pass

"""Register bake_ops category: RNA, operators, and top-level panel."""

from __future__ import annotations

import importlib
from types import ModuleType

import bpy

from ..shared_utilities.register_helpers import (
    register_classes,
    reload_modules,
    unregister_classes,
)

from . import LKS_OT_BakeGroupSettingsPopup
from . import LKS_OT_BakeMapSettingsPopup
from . import LKS_OT_BakeProjectSettingsPopup
from . import LKS_OT_AddSelectionToBakeGroup
from . import LKS_OT_AddSelectionToBakeProject
from . import LKS_OT_ApplyBakeLowMaterialTest
from . import LKS_OT_AssignToBakeGroup
from . import LKS_OT_BakeBakeProject
from . import LKS_OT_BakeMapOperators
from . import LKS_OT_ExportBakeGroup
from . import LKS_OT_ExportBakeProject
from . import LKS_OT_GenerateExtractedHighpoly
from . import LKS_OT_GenerateMergedLowpoly
from . import LKS_OT_MakeBakerFromObject
from . import LKS_OT_NewBakeGroup
from . import LKS_OT_NewBakeProject
from . import LKS_OT_RemoveBakeGroup
from . import LKS_OT_ReapplyBakePreviewMaterial
from . import LKS_OT_RemoveBakeProject
from . import LKS_OT_SelectBakeGroupContents
from . import LKS_OT_SelectBakeProjectContents
from . import LKS_OT_SetActiveBakeProject
from . import LKS_OT_SetBakeRoleHigh
from . import LKS_OT_SetBakeRoleLow
from . import LKS_OT_ToggleBakeMapPreview
from . import LKS_OT_ToggleBakeGroupVisibility
from . import LKS_OT_ToggleBakeProjectVisibility
from . import LKS_OT_ToggleBakeRoleVisibility
from . import LKS_OT_UnassignFromBakeGroup
from . import LKS_UL_BakeGroupHighs
from . import LKS_UL_BakeGroupLows
from . import LKS_UL_BakeGroups
from . import LKS_UL_BakeMaps
from . import LKS_UL_BakeProjects
from . import VIEW3D_PT_LKS_Bake_Project_Ops
from . import helpers_bake_cleanup
from . import helpers_bake_export
from . import helpers_bake_prep
from . import helpers_bake_run
from . import lks_bake_props
from .static_utilities import bake_progress_helpers

modules: list[ModuleType] = [
    lks_bake_props,
    helpers_bake_cleanup,
    helpers_bake_export,
    helpers_bake_prep,
    helpers_bake_run,
    LKS_OT_BakeGroupSettingsPopup,
    LKS_OT_BakeMapSettingsPopup,
    LKS_OT_BakeProjectSettingsPopup,
    LKS_OT_NewBakeProject,
    LKS_OT_AddSelectionToBakeProject,
    LKS_OT_NewBakeGroup,
    LKS_OT_AddSelectionToBakeGroup,
    LKS_OT_ApplyBakeLowMaterialTest,
    LKS_OT_GenerateExtractedHighpoly,
    LKS_OT_GenerateMergedLowpoly,
    LKS_OT_MakeBakerFromObject,
    LKS_OT_AssignToBakeGroup,
    LKS_OT_UnassignFromBakeGroup,
    LKS_OT_SetBakeRoleHigh,
    LKS_OT_SetBakeRoleLow,
    LKS_OT_RemoveBakeProject,
    LKS_OT_RemoveBakeGroup,
    LKS_OT_SetActiveBakeProject,
    LKS_OT_ToggleBakeProjectVisibility,
    LKS_OT_ToggleBakeRoleVisibility,
    LKS_OT_SelectBakeProjectContents,
    LKS_OT_ExportBakeProject,
    LKS_OT_BakeBakeProject,
    LKS_OT_BakeMapOperators,
    LKS_OT_ReapplyBakePreviewMaterial,
    LKS_OT_ToggleBakeMapPreview,
    LKS_OT_ToggleBakeGroupVisibility,
    LKS_OT_SelectBakeGroupContents,
    LKS_OT_ExportBakeGroup,
    LKS_UL_BakeGroupHighs,
    LKS_UL_BakeGroupLows,
    LKS_UL_BakeGroups,
    LKS_UL_BakeMaps,
    LKS_UL_BakeProjects,
    VIEW3D_PT_LKS_Bake_Project_Ops,
]

ops = [
    LKS_OT_BakeGroupSettingsPopup.LKS_OT_BakeGroupSettingsPopup,
    LKS_OT_BakeMapSettingsPopup.LKS_OT_BakeMapSettingsPopup,
    LKS_OT_BakeProjectSettingsPopup.LKS_OT_BakeProjectSettingsPopup,
    LKS_OT_NewBakeProject.LKS_OT_NewBakeProject,
    LKS_OT_AddSelectionToBakeProject.LKS_OT_AddSelectionToBakeProject,
    LKS_OT_NewBakeGroup.LKS_OT_NewBakeGroup,
    LKS_OT_AddSelectionToBakeGroup.LKS_OT_AddSelectionToBakeGroup,
    LKS_OT_ApplyBakeLowMaterialTest.LKS_OT_ApplyBakeLowMaterialTest,
    LKS_OT_GenerateExtractedHighpoly.LKS_OT_GenerateExtractedHighpoly,
    LKS_OT_GenerateMergedLowpoly.LKS_OT_GenerateMergedLowpoly,
    LKS_OT_MakeBakerFromObject.LKS_OT_MakeBakerFromObject,
    LKS_OT_AssignToBakeGroup.LKS_OT_AssignToBakeGroup,
    LKS_OT_UnassignFromBakeGroup.LKS_OT_UnassignFromBakeGroup,
    LKS_OT_SetBakeRoleHigh.LKS_OT_SetBakeRoleHigh,
    LKS_OT_SetBakeRoleLow.LKS_OT_SetBakeRoleLow,
    LKS_OT_RemoveBakeProject.LKS_OT_RemoveBakeProject,
    LKS_OT_RemoveBakeGroup.LKS_OT_RemoveBakeGroup,
    LKS_OT_SetActiveBakeProject.LKS_OT_SetActiveBakeProject,
    LKS_OT_ToggleBakeProjectVisibility.LKS_OT_ToggleBakeProjectVisibility,
    LKS_OT_ToggleBakeRoleVisibility.LKS_OT_ToggleBakeProjectHighVisibility,
    LKS_OT_ToggleBakeRoleVisibility.LKS_OT_ToggleBakeProjectLowVisibility,
    LKS_OT_ToggleBakeRoleVisibility.LKS_OT_ToggleBakeGroupHighVisibility,
    LKS_OT_ToggleBakeRoleVisibility.LKS_OT_ToggleBakeGroupLowVisibility,
    LKS_OT_SelectBakeProjectContents.LKS_OT_SelectBakeProjectContents,
    LKS_OT_ExportBakeProject.LKS_OT_ExportBakeProject,
    LKS_OT_BakeBakeProject.LKS_OT_BakeBakeProject,
    *LKS_OT_BakeMapOperators.BAKE_MAP_OPERATOR_CLASSES,
    LKS_OT_ToggleBakeMapPreview.LKS_OT_ToggleBakeMapPreview,
    LKS_OT_ReapplyBakePreviewMaterial.LKS_OT_ReapplyBakePreviewMaterial,
    LKS_OT_ToggleBakeGroupVisibility.LKS_OT_ToggleBakeGroupVisibility,
    LKS_OT_SelectBakeGroupContents.LKS_OT_SelectBakeGroupContents,
    LKS_OT_ExportBakeGroup.LKS_OT_ExportBakeGroup,
]

ui_classes = [
    LKS_UL_BakeGroups.LKS_UL_BakeGroups,
    LKS_UL_BakeMaps.LKS_UL_BakeMaps,
    LKS_UL_BakeMaps.LKS_UL_BakeMapsSurface,
    LKS_UL_BakeMaps.LKS_UL_BakeMapsLighting,
    LKS_UL_BakeMaps.LKS_UL_BakeMapsMasks,
    LKS_UL_BakeMaps.LKS_UL_BakeMapsPbr,
    LKS_UL_BakeProjects.LKS_UL_BakeProjects,
    LKS_UL_BakeGroupHighs.LKS_UL_BakeGroupHighs,
    LKS_UL_BakeGroupLows.LKS_UL_BakeGroupLows,
    VIEW3D_PT_LKS_Bake_Project_Ops.VIEW3D_PT_LKS_Bake_Project_Ops,
]

main_panel = VIEW3D_PT_LKS_Bake_Project_Ops.VIEW3D_PT_LKS_Bake_Project_Ops


def _deferred_migrate_bake_group_ui_slots() -> float | None:
    """One-shot post-register migration when bpy.data is unrestricted."""
    helpers_bake_cleanup.migrate_bake_group_ui_slots_all_scenes()
    return None


def _deferred_refresh_bake_low_materials() -> float | None:
    """Restore composite low-material wiring after register or blend load."""
    for scene in bpy.data.scenes:
        helpers_bake_run.refresh_all_bake_projects_low_material(scene)
    return None


@bpy.app.handlers.persistent
def _on_blend_load_refresh_bake_low_materials(_dummy) -> None:
    bpy.app.timers.register(_deferred_refresh_bake_low_materials, first_interval=0.0)


def register_props() -> None:
    """register props for the bake ops category.
    """
    bake_progress_helpers.register_props()
    lks_bake_props.register_props()
    VIEW3D_PT_LKS_Bake_Project_Ops.register_props()


def unregister_props() -> None:
    """unregister props for the bake ops category.
    """
    VIEW3D_PT_LKS_Bake_Project_Ops.unregister_props()
    lks_bake_props.unregister_props()
    bake_progress_helpers.unregister_props()


def register_ops() -> None:
    """register ops for the bake ops category.
    """
    register_classes(ops)


def unregister_ops() -> None:
    """unregister ops for the bake ops category.
    """
    unregister_classes(ops)


def register_ui() -> None:
    """register ui for the bake ops category.
    """
    register_classes(ui_classes)


def unregister_ui() -> None:
    """unregister ui for the bake ops category.
    """
    unregister_classes(list(reversed(ui_classes)))


def register() -> None:
    """register for the bake ops category.
    """
    register_props()
    register_ops()
    register_ui()
    bpy.app.timers.register(_deferred_migrate_bake_group_ui_slots, first_interval=0.0)
    bpy.app.timers.register(_deferred_refresh_bake_low_materials, first_interval=0.0)
    if _on_blend_load_refresh_bake_low_materials not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_blend_load_refresh_bake_low_materials)


def unregister() -> None:
    """unregister for the bake ops category.
    """
    if _on_blend_load_refresh_bake_low_materials in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_blend_load_refresh_bake_low_materials)
    unregister_ui()
    unregister_ops()
    unregister_props()


def reload() -> None:
    """Reload.
    """
    reload_modules(modules)

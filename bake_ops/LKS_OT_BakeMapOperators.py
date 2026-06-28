"""Thin per-map bake operators — one class per catalog map_id."""

from __future__ import annotations

import bpy

from .static_utilities.bake_blender_helpers import get_map_bake_blocker, map_id_is_bakeable
from .static_utilities.bake_map_catalog import BAKE_MAP_CATALOG, get_bake_map_spec
from ..shared_utilities.lks_constants import (
    BAKE_MAP_RENDER_CTRL_TOOLTIP,
    BAKE_MAP_RENDER_TOOLTIP,
)
from .helpers_bake_run import bake_project_has_bakable_groups, run_bake_project_map
from .static_utilities.bake_texture_derivatives import BakeMapSkipped


def _map_id_to_class_name(map_id: str) -> str:
    return 'LKS_OT_BakeMap' + ''.join(part.capitalize() for part in map_id.split('_'))


def _make_bake_map_operator(map_id: str):
    spec = get_bake_map_spec(map_id)
    label = spec.label if spec is not None else map_id
    class_name = _map_id_to_class_name(map_id)

    class _LKS_OT_BakeMap(bpy.types.Operator):
        f"""{BAKE_MAP_RENDER_TOOLTIP} {BAKE_MAP_RENDER_CTRL_TOOLTIP}"""
        bl_idname = f'object.lks_bake_map_{map_id}'
        bl_label = f'Bake {label}'
        bl_options = {'REGISTER', 'UNDO'}

        project_index: bpy.props.IntProperty(
            name='Project Index',
            default=-1,
            description='Bake project index (-1 = active project)',
        )
        force_rebuild_dependencies: bpy.props.BoolProperty(
            name='Force Rebuild Dependencies',
            default=False,
            description=BAKE_MAP_RENDER_CTRL_TOOLTIP,
            options={'HIDDEN', 'SKIP_SAVE'},
        )

        @classmethod
        def poll(cls, context: bpy.types.Context) -> bool:
            if context.area is None or context.area.type != 'VIEW_3D':
                return False
            return len(context.scene.lks_bake_projects) > 0

        def _resolve_project_index(self, scene: bpy.types.Scene) -> int:
            if self.project_index >= 0:
                return self.project_index
            return scene.lks_active_bake_project_index

        def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
            self.force_rebuild_dependencies = event.ctrl
            return self.execute(context)

        def execute(self, context: bpy.types.Context) -> set[str]:
            scene = context.scene
            index = self._resolve_project_index(scene)
            if not (0 <= index < len(scene.lks_bake_projects)):
                self.report({'ERROR'}, 'No bake project to bake')
                return {'CANCELLED'}

            project = scene.lks_bake_projects[index]
            if not bake_project_has_bakable_groups(project):
                self.report(
                    {'ERROR'},
                    f"Project '{project.name}' needs high and low geometry across its bake groups",
                )
                return {'CANCELLED'}

            if not map_id_is_bakeable(map_id):
                blocker = get_map_bake_blocker(map_id) or 'not implemented yet'
                self.report({'WARNING'}, f"{label} — {blocker}")
                return {'CANCELLED'}

            try:
                baked = run_bake_project_map(
                    context,
                    project,
                    map_id,
                    reuse_existing_dependencies=not self.force_rebuild_dependencies,
                )
            except BakeMapSkipped as exc:
                self.report({'WARNING'}, str(exc))
                return {'CANCELLED'}
            except RuntimeError as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}

            self.report(
                {'INFO'},
                f"Baked {label} ({len(baked)} image(s)) to {project.output_dir}",
            )
            return {'FINISHED'}

    _LKS_OT_BakeMap.__name__ = class_name
    _LKS_OT_BakeMap.__qualname__ = class_name
    return _LKS_OT_BakeMap


BAKE_MAP_OPERATOR_CLASSES: list[type] = [
    _make_bake_map_operator(map_id)
    for map_id in sorted(BAKE_MAP_CATALOG.keys(), key=lambda mid: BAKE_MAP_CATALOG[mid].sort_order)
]

# Named exports for tests and keymaps.
for _op_cls in BAKE_MAP_OPERATOR_CLASSES:
    globals()[_op_cls.__name__] = _op_cls

LKS_OT_BakeMapNormal = globals()['LKS_OT_BakeMapNormal']
LKS_OT_BakeMapAo = globals()['LKS_OT_BakeMapAo']
LKS_OT_BakeMapPosition = globals()['LKS_OT_BakeMapPosition']
LKS_OT_BakeMapRoughness = globals()['LKS_OT_BakeMapRoughness']
LKS_OT_BakeMapAlbedo = globals()['LKS_OT_BakeMapAlbedo']

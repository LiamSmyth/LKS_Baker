"""UIList of low-role objects in the active bake group."""

from __future__ import annotations

import bpy

from .helpers_bake_cleanup import find_bake_group_project, iter_bake_group_low_objects
from .lks_bake_props import LKS_PG_BakeGroup


class LKS_UL_BakeGroupLows(bpy.types.UIList):
    """Object names for all low-role collections in the active bake group."""

    bl_idname = 'LKS_UL_BakeGroupLows'

    def _objects(
        self,
        context: bpy.types.Context,
        bake_group: LKS_PG_BakeGroup,
    ) -> list[bpy.types.Object]:
        project = find_bake_group_project(context.scene, bake_group)
        if project is None:
            return []
        return iter_bake_group_low_objects(project, bake_group)

    def filter_items(
        self,
        context: bpy.types.Context,
        data: bpy.types.Any,
        propname: str,
    ) -> tuple[list[int], list[int]]:
        bake_group: LKS_PG_BakeGroup = data
        slots = getattr(bake_group, propname)
        entry_count = len(self._objects(context, bake_group))
        flt_flags = [
            self.bitflag_filter_item if index < entry_count else 0
            for index in range(len(slots))
        ]
        return flt_flags, []

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
        bake_group: LKS_PG_BakeGroup = data
        objects = self._objects(context, bake_group)
        if index >= len(objects):
            return
        obj = objects[index]
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if obj is not None:
                layout.label(text=obj.name, icon='OBJECT_DATA')
            else:
                layout.label(text='(missing)', icon='ERROR')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            name = obj.name if obj is not None else '(missing)'
            layout.label(text=name, icon='OBJECT_DATA')

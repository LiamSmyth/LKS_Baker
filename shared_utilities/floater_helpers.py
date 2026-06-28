import bpy

from .lks_constants import (
    FLOATER_DATA_TRANSFER_LOOP_TYPES,
    FLOATER_MOD_DATA_TRANSFER,
    FLOATER_MOD_DISPLACE,
    FLOATER_MOD_SHRINKWRAP,
    FLOATER_VG_SHRINKWRAP,
    FLOATER_VG_TRANSFER,
)


def get_or_create_modifier(
    obj: bpy.types.Object,
    name: str,
    mod_type: str,
) -> bpy.types.Modifier:
    mod = obj.modifiers.get(name)
    if mod is None:
        mod = obj.modifiers.new(name=name, type=mod_type)
    return mod


def configure_floater_shrinkwrap(
    floater: bpy.types.Object,
    target: bpy.types.Object,
    *,
    mod_name: str = FLOATER_MOD_SHRINKWRAP,
    vertex_group: str = FLOATER_VG_SHRINKWRAP,
) -> bpy.types.ShrinkwrapModifier:
    shrinkwrap = get_or_create_modifier(floater, mod_name, "SHRINKWRAP")
    shrinkwrap.target = target
    shrinkwrap.wrap_method = 'TARGET_PROJECT'
    shrinkwrap.use_negative_direction = True
    shrinkwrap.vertex_group = vertex_group
    return shrinkwrap


def configure_floater_displace(
    floater: bpy.types.Object,
    strength: float,
    *,
    mod_name: str = FLOATER_MOD_DISPLACE,
    vertex_group: str = FLOATER_VG_SHRINKWRAP,
) -> bpy.types.DisplaceModifier:
    displace = get_or_create_modifier(floater, mod_name, "DISPLACE")
    displace.mid_level = 0
    displace.strength = strength
    displace.vertex_group = vertex_group
    return displace


def configure_floater_data_transfer(
    floater: bpy.types.Object,
    source: bpy.types.Object,
    *,
    mod_name: str = FLOATER_MOD_DATA_TRANSFER,
    vertex_group: str = FLOATER_VG_TRANSFER,
) -> bpy.types.DataTransferModifier:
    datatransfer = get_or_create_modifier(floater, mod_name, "DATA_TRANSFER")
    datatransfer.object = source
    datatransfer.use_loop_data = True
    datatransfer.data_types_loops = set(FLOATER_DATA_TRANSFER_LOOP_TYPES)
    datatransfer.loop_mapping = 'POLYINTERP_NEAREST'
    datatransfer.vertex_group = vertex_group
    return datatransfer

import bpy

from .lks_constants import (
    BEVEL_ANGLE_DEFAULT,
    BEVEL_ANGLE_SIZE_DEFAULT,
    BEVEL_CUSP_ANGLE_DEFAULT,
    BEVEL_PROFILE_FWN,
    BEVEL_PROFILE_SUBSURF,
    BEVEL_SEGMENTS_FWN,
    BEVEL_SEGMENTS_SUBSURF,
    LEGACY_BEVEL_MOD_AUTO_SMOOTH,
    LEGACY_BEVEL_MOD_DYNA_DECIMATE,
    LEGACY_BEVEL_MOD_DYNA_REMESH,
    LEGACY_BEVEL_MOD_DYNA_SMOOTH,
    LEGACY_BEVEL_MOD_DYNA_WEIGHTED_NORMAL,
    LEGACY_BEVEL_MOD_FWN_ANGLE,
    LEGACY_BEVEL_MOD_FWN_TRIANGULATE,
    LEGACY_BEVEL_MOD_FWN_WEIGHT,
    LEGACY_BEVEL_MOD_FWN_WEIGHTED_NORMAL,
    LEGACY_BEVEL_MOD_SUBSURF,
    LEGACY_BEVEL_MOD_SUBSURF_BEVEL,
    LEGACY_BEVEL_MOD_SUBSURF_WEIGHTED_NORMAL,
    LEGACY_MOD_NAME_BEVEL,
    MOD_NAME_BEVEL_ANGLE,
    MOD_NAME_BEVEL_DYNA_DECIMATE,
    MOD_NAME_BEVEL_DYNA_REMESH,
    MOD_NAME_BEVEL_DYNA_SMOOTH,
    MOD_NAME_BEVEL_LIMIT,
    MOD_NAME_BEVEL_SUBSURF,
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    MOD_NAME_NORMALS_TRIANGULATE,
    MOD_NAME_NORMALS_WEIGHTED_NORMAL,
)
from .modifier_helpers import reorder_modifiers_to_end
from .modifier_helpers import modifier_visibility_is_on
from .normal_mod_helpers import (
    ensure_lks_normals_tail_stack,
    iter_mesh_selection,
    set_modifier_visibility,
)
from .shading_helpers import (
    apply_smooth_by_angle,
    consolidate_smooth_by_angle_modifiers,
    is_smooth_by_angle_modifier,
    set_mesh_shade_smooth,
    set_smooth_by_angle_ignore_sharps,
)

BEVEL_MODE_FWN = 'FWN'
BEVEL_MODE_SUBSURF = 'SUBSURF'
BEVEL_MODE_DYNA = 'DYNA'

FWN_STACK_MOD_NAMES = (
    MOD_NAME_BEVEL_LIMIT,
    MOD_NAME_BEVEL_ANGLE,
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    MOD_NAME_NORMALS_TRIANGULATE,
)

SUBSURF_STACK_MOD_NAMES = (
    MOD_NAME_BEVEL_LIMIT,
    MOD_NAME_BEVEL_ANGLE,
    MOD_NAME_BEVEL_SUBSURF,
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    MOD_NAME_NORMALS_TRIANGULATE,
)

DYNA_STACK_MOD_NAMES = (
    MOD_NAME_BEVEL_DYNA_REMESH,
    MOD_NAME_BEVEL_DYNA_SMOOTH,
    MOD_NAME_BEVEL_DYNA_DECIMATE,
    MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    MOD_NAME_NORMALS_TRIANGULATE,
)

BEVEL_MANAGED_MOD_NAMES = tuple(dict.fromkeys(
    FWN_STACK_MOD_NAMES + SUBSURF_STACK_MOD_NAMES + DYNA_STACK_MOD_NAMES
))

_LEGACY_TO_LKS_NAME = {
    LEGACY_MOD_NAME_BEVEL: MOD_NAME_BEVEL_LIMIT,
    LEGACY_BEVEL_MOD_FWN_WEIGHT: MOD_NAME_BEVEL_LIMIT,
    LEGACY_BEVEL_MOD_FWN_ANGLE: MOD_NAME_BEVEL_ANGLE,
    LEGACY_BEVEL_MOD_FWN_WEIGHTED_NORMAL: MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    LEGACY_BEVEL_MOD_FWN_TRIANGULATE: MOD_NAME_NORMALS_TRIANGULATE,
    LEGACY_BEVEL_MOD_SUBSURF_BEVEL: MOD_NAME_BEVEL_LIMIT,
    LEGACY_BEVEL_MOD_SUBSURF: MOD_NAME_BEVEL_SUBSURF,
    LEGACY_BEVEL_MOD_SUBSURF_WEIGHTED_NORMAL: MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    LEGACY_BEVEL_MOD_DYNA_REMESH: MOD_NAME_BEVEL_DYNA_REMESH,
    LEGACY_BEVEL_MOD_DYNA_SMOOTH: MOD_NAME_BEVEL_DYNA_SMOOTH,
    LEGACY_BEVEL_MOD_DYNA_DECIMATE: MOD_NAME_BEVEL_DYNA_DECIMATE,
    LEGACY_BEVEL_MOD_DYNA_WEIGHTED_NORMAL: MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    LEGACY_BEVEL_MOD_AUTO_SMOOTH: MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
}

_MANAGED_BEVEL_MOD_NAMES = frozenset({MOD_NAME_BEVEL_LIMIT, MOD_NAME_BEVEL_ANGLE})

_DEFAULT_WEIGHTED_KEEP_SHARP = True
_DEFAULT_TRIANGULATE_KEEP_NORMALS = True
_DEFAULT_TRIANGULATE_QUAD_METHOD = 'BEAUTY'
_DEFAULT_TRIANGULATE_NGON_METHOD = 'BEAUTY'
_DEFAULT_DYNA_REMESH_DENSITY = 100
_DEFAULT_DYNA_SMOOTH_ITERATIONS = 50
_DEFAULT_DYNA_DECIMATE_RATIO = 0.05


def default_bevel_size_from_object(obj: bpy.types.Object) -> float:
    return max(obj.dimensions) * 0.002


def default_dynamesh_voxel_size(obj: bpy.types.Object) -> float:
    return max(obj.dimensions) / _DEFAULT_DYNA_REMESH_DENSITY


def iter_bevel_managed_modifier_names(obj: bpy.types.Object) -> list[str]:
    return [
        mod.name for mod in obj.modifiers
        if mod.name in BEVEL_MANAGED_MOD_NAMES
    ]


def set_bevel_managed_visibility(
    objects: list[bpy.types.Object],
    visible: bool,
) -> int:
    count = 0
    for obj in objects:
        for mod_name in iter_bevel_managed_modifier_names(obj):
            if set_modifier_visibility(obj, mod_name, visible):
                count += 1
    return count


def toggle_bevel_managed_visibility(objects: list[bpy.types.Object]) -> int:
    toggle_state = True
    for obj in objects:
        for mod_name in iter_bevel_managed_modifier_names(obj):
            mod = obj.modifiers.get(mod_name)
            if mod is not None:
                toggle_state = not modifier_visibility_is_on(mod)
                break
        else:
            continue
        break
    return set_bevel_managed_visibility(objects, toggle_state)


def _rename_legacy_modifier(obj: bpy.types.Object, legacy_name: str, lks_name: str) -> bpy.types.Modifier | None:
    mod = obj.modifiers.get(legacy_name)
    if mod is None:
        return None
    if lks_name in obj.modifiers and obj.modifiers[lks_name] is not mod:
        obj.modifiers.remove(mod)
        return obj.modifiers.get(lks_name)
    mod.name = lks_name
    return mod


def migrate_legacy_bevel_modifiers(obj: bpy.types.Object) -> None:
    for legacy_name, lks_name in _LEGACY_TO_LKS_NAME.items():
        _rename_legacy_modifier(obj, legacy_name, lks_name)


def _remove_unmanaged_bevel_duplicates(obj: bpy.types.Object) -> None:
    """Remove legacy duplicate bevel modifiers not managed by LKS naming."""
    legacy_bevel_names = {
        LEGACY_MOD_NAME_BEVEL,
        LEGACY_BEVEL_MOD_FWN_ANGLE,
        LEGACY_BEVEL_MOD_FWN_WEIGHT,
        LEGACY_BEVEL_MOD_SUBSURF_BEVEL,
    }
    mods_to_remove: list[bpy.types.Modifier] = []
    for mod in obj.modifiers:
        if mod.type != 'BEVEL':
            continue
        if mod.name in _MANAGED_BEVEL_MOD_NAMES:
            continue
        if mod.name in legacy_bevel_names:
            mods_to_remove.append(mod)
    for mod in mods_to_remove:
        obj.modifiers.remove(mod)


def reorder_modifier_stack(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    ordered_names: tuple[str, ...],
    *,
    use_triangulate: bool | None = None,
) -> None:
    existing = [name for name in ordered_names if name in obj.modifiers]
    if existing:
        reorder_modifiers_to_end(context, obj, existing)
    ensure_lks_normals_tail_stack(context, obj, use_triangulate=use_triangulate)


def _get_or_create_bevel_limit(obj: bpy.types.Object) -> bpy.types.BevelModifier:
    migrate_legacy_bevel_modifiers(obj)
    mod = obj.modifiers.get(MOD_NAME_BEVEL_LIMIT)
    if mod is None or mod.type != 'BEVEL':
        mod = obj.modifiers.new(MOD_NAME_BEVEL_LIMIT, 'BEVEL')
    return mod


def _get_or_create_bevel_angle(obj: bpy.types.Object) -> bpy.types.BevelModifier:
    migrate_legacy_bevel_modifiers(obj)
    mod = obj.modifiers.get(MOD_NAME_BEVEL_ANGLE)
    if mod is None or mod.type != 'BEVEL':
        mod = obj.modifiers.new(MOD_NAME_BEVEL_ANGLE, 'BEVEL')
    return mod


def _remove_bevel_limit(obj: bpy.types.Object) -> None:
    mod = obj.modifiers.get(MOD_NAME_BEVEL_LIMIT)
    if mod is not None:
        obj.modifiers.remove(mod)


def _remove_bevel_angle(obj: bpy.types.Object) -> None:
    mod = obj.modifiers.get(MOD_NAME_BEVEL_ANGLE)
    if mod is not None:
        obj.modifiers.remove(mod)


def configure_bevel_limit_modifier(
    mod: bpy.types.BevelModifier,
    *,
    size: float,
    segments: int,
    profile: float,
) -> None:
    mod.limit_method = 'WEIGHT'
    mod.offset_type = 'OFFSET'
    mod.width = size
    mod.segments = segments
    mod.use_clamp_overlap = False
    mod.profile = profile


def configure_bevel_angle_modifier(
    mod: bpy.types.BevelModifier,
    *,
    size: float,
    segments: int,
    profile: float,
    angle: float,
) -> None:
    mod.limit_method = 'ANGLE'
    mod.offset_type = 'OFFSET'
    mod.width = size
    mod.segments = segments
    mod.use_clamp_overlap = False
    mod.profile = profile
    mod.angle_limit = angle


def _apply_bevel_modifiers(
    obj: bpy.types.Object,
    *,
    size: float,
    angle_size: float,
    segments: int,
    profile: float,
    use_limit: bool,
    use_angle: bool,
    bevel_angle: float,
) -> None:
    if use_limit:
        limit_mod = _get_or_create_bevel_limit(obj)
        configure_bevel_limit_modifier(
            limit_mod,
            size=size,
            segments=segments,
            profile=profile,
        )
    else:
        _remove_bevel_limit(obj)

    if use_angle:
        angle_mod = _get_or_create_bevel_angle(obj)
        configure_bevel_angle_modifier(
            angle_mod,
            size=angle_size,
            segments=segments,
            profile=profile,
            angle=bevel_angle,
        )
    else:
        _remove_bevel_angle(obj)


def configure_bevel_modifier(
    mod: bpy.types.BevelModifier,
    *,
    size: float,
    segments: int,
    profile: float,
) -> None:
    """Legacy alias — configures a weight-limited bevel modifier."""
    configure_bevel_limit_modifier(
        mod,
        size=size,
        segments=segments,
        profile=profile,
    )


def _get_or_create_smooth(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    smooth_angle: float,
) -> bpy.types.Modifier | None:
    migrate_legacy_bevel_modifiers(obj)
    consolidate_smooth_by_angle_modifiers(
        obj,
        keeper_name=MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    )

    smooth_mod = apply_smooth_by_angle(
        context,
        obj,
        smooth_angle,
        modifier_name=MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
        pin_to_last=False,
    )
    if smooth_mod is None:
        return None

    smooth_mod = obj.modifiers.get(MOD_NAME_NORMALS_SMOOTH_BY_ANGLE)
    if smooth_mod is None or not is_smooth_by_angle_modifier(smooth_mod):
        return None

    set_smooth_by_angle_ignore_sharps(smooth_mod, False)
    return smooth_mod


def _get_or_create_weighted_normal(
    obj: bpy.types.Object,
    *,
    wn_weight: int,
    wn_threshold: float,
    wn_mode: str,
) -> bpy.types.WeightedNormalModifier:
    migrate_legacy_bevel_modifiers(obj)
    mod = obj.modifiers.get(MOD_NAME_NORMALS_WEIGHTED_NORMAL)
    if mod is None or mod.type != 'WEIGHTED_NORMAL':
        mod = obj.modifiers.new(MOD_NAME_NORMALS_WEIGHTED_NORMAL, 'WEIGHTED_NORMAL')

    mod.keep_sharp = _DEFAULT_WEIGHTED_KEEP_SHARP
    mod.use_face_influence = True
    mod.weight = wn_weight
    mod.thresh = wn_threshold
    mod.mode = wn_mode
    return mod


def _get_or_create_triangulate(
    obj: bpy.types.Object,
    *,
    min_vertices: int,
) -> bpy.types.TriangulateModifier:
    migrate_legacy_bevel_modifiers(obj)
    mod = obj.modifiers.get(MOD_NAME_NORMALS_TRIANGULATE)
    if mod is None or mod.type != 'TRIANGULATE':
        mod = obj.modifiers.new(MOD_NAME_NORMALS_TRIANGULATE, 'TRIANGULATE')

    mod.keep_custom_normals = _DEFAULT_TRIANGULATE_KEEP_NORMALS
    mod.quad_method = _DEFAULT_TRIANGULATE_QUAD_METHOD
    mod.ngon_method = _DEFAULT_TRIANGULATE_NGON_METHOD
    mod.min_vertices = min_vertices
    return mod


def _apply_triangulate_optional(
    obj: bpy.types.Object,
    *,
    use_triangulate: bool,
    tri_min_vertices: int,
) -> None:
    if use_triangulate:
        _get_or_create_triangulate(obj, min_vertices=tri_min_vertices)
        return
    tri_mod = obj.modifiers.get(MOD_NAME_NORMALS_TRIANGULATE)
    if tri_mod is not None:
        obj.modifiers.remove(tri_mod)


def _get_or_create_subsurf(
    obj: bpy.types.Object,
    *,
    levels: int,
) -> bpy.types.SubsurfModifier:
    migrate_legacy_bevel_modifiers(obj)
    mod = obj.modifiers.get(MOD_NAME_BEVEL_SUBSURF)
    if mod is None or mod.type != 'SUBSURF':
        mod = obj.modifiers.new(MOD_NAME_BEVEL_SUBSURF, 'SUBSURF')
    mod.levels = levels
    mod.render_levels = levels
    mod.quality = 1
    return mod


def _get_or_create_dynamesh_modifiers(
    obj: bpy.types.Object,
    *,
    voxel_size: float,
    smooth_iterations: int,
    decimate_ratio: float,
    wn_weight: int,
    wn_threshold: float,
    wn_mode: str,
) -> tuple[
    bpy.types.RemeshModifier,
    bpy.types.SmoothModifier,
    bpy.types.DecimateModifier,
    bpy.types.WeightedNormalModifier,
]:
    migrate_legacy_bevel_modifiers(obj)

    remesh = obj.modifiers.get(MOD_NAME_BEVEL_DYNA_REMESH)
    if remesh is None or remesh.type != 'REMESH':
        remesh = obj.modifiers.new(MOD_NAME_BEVEL_DYNA_REMESH, 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = voxel_size
    remesh.use_smooth_shade = True

    smooth = obj.modifiers.get(MOD_NAME_BEVEL_DYNA_SMOOTH)
    if smooth is None or smooth.type != 'SMOOTH':
        smooth = obj.modifiers.new(MOD_NAME_BEVEL_DYNA_SMOOTH, 'SMOOTH')
    smooth.iterations = smooth_iterations

    decimate = obj.modifiers.get(MOD_NAME_BEVEL_DYNA_DECIMATE)
    if decimate is None or decimate.type != 'DECIMATE':
        decimate = obj.modifiers.new(MOD_NAME_BEVEL_DYNA_DECIMATE, 'DECIMATE')
    decimate.decimate_type = 'COLLAPSE'
    decimate.ratio = decimate_ratio

    weighted = _get_or_create_weighted_normal(
        obj,
        wn_weight=wn_weight,
        wn_threshold=wn_threshold,
        wn_mode=wn_mode,
    )
    return remesh, smooth, decimate, weighted


def apply_fwn_stack(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    size: float,
    wn_weight: int,
    wn_threshold: float,
    wn_mode: str,
    use_triangulate: bool,
    tri_min_vertices: int,
    use_limit: bool = True,
    use_angle: bool = False,
    bevel_angle: float = BEVEL_ANGLE_DEFAULT,
    angle_size: float = BEVEL_ANGLE_SIZE_DEFAULT,
    cusp_angle: float = BEVEL_CUSP_ANGLE_DEFAULT,
) -> None:
    migrate_legacy_bevel_modifiers(obj)
    _remove_unmanaged_bevel_duplicates(obj)

    set_mesh_shade_smooth(obj)

    _apply_bevel_modifiers(
        obj,
        size=size,
        angle_size=angle_size,
        segments=BEVEL_SEGMENTS_FWN,
        profile=BEVEL_PROFILE_FWN,
        use_limit=use_limit,
        use_angle=use_angle,
        bevel_angle=bevel_angle,
    )

    _get_or_create_smooth(context, obj, cusp_angle)
    _get_or_create_weighted_normal(
        obj,
        wn_weight=wn_weight,
        wn_threshold=wn_threshold,
        wn_mode=wn_mode,
    )

    _apply_triangulate_optional(
        obj,
        use_triangulate=use_triangulate,
        tri_min_vertices=tri_min_vertices,
    )

    reorder_modifier_stack(
        context,
        obj,
        FWN_STACK_MOD_NAMES,
        use_triangulate=use_triangulate,
    )


def apply_subsurf_stack(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    size: float,
    wn_weight: int,
    wn_threshold: float,
    wn_mode: str,
    subsurf_levels: int,
    use_triangulate: bool,
    tri_min_vertices: int,
    use_limit: bool = True,
    use_angle: bool = False,
    bevel_angle: float = BEVEL_ANGLE_DEFAULT,
    angle_size: float = BEVEL_ANGLE_SIZE_DEFAULT,
    cusp_angle: float = BEVEL_CUSP_ANGLE_DEFAULT,
) -> None:
    migrate_legacy_bevel_modifiers(obj)
    _remove_unmanaged_bevel_duplicates(obj)

    set_mesh_shade_smooth(obj)

    _apply_bevel_modifiers(
        obj,
        size=size,
        angle_size=angle_size,
        segments=BEVEL_SEGMENTS_SUBSURF,
        profile=BEVEL_PROFILE_SUBSURF,
        use_limit=use_limit,
        use_angle=use_angle,
        bevel_angle=bevel_angle,
    )

    _get_or_create_subsurf(obj, levels=subsurf_levels)
    _get_or_create_smooth(context, obj, cusp_angle)
    _get_or_create_weighted_normal(
        obj,
        wn_weight=wn_weight,
        wn_threshold=wn_threshold,
        wn_mode=wn_mode,
    )

    _apply_triangulate_optional(
        obj,
        use_triangulate=use_triangulate,
        tri_min_vertices=tri_min_vertices,
    )

    reorder_modifier_stack(
        context,
        obj,
        SUBSURF_STACK_MOD_NAMES,
        use_triangulate=use_triangulate,
    )


def apply_dynamesh_stack(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    voxel_size: float,
    wn_weight: int,
    wn_threshold: float,
    wn_mode: str,
    smooth_iterations: int,
    decimate_ratio: float,
    use_triangulate: bool,
    tri_min_vertices: int,
) -> None:
    migrate_legacy_bevel_modifiers(obj)
    _remove_unmanaged_bevel_duplicates(obj)
    _get_or_create_dynamesh_modifiers(
        obj,
        voxel_size=voxel_size,
        smooth_iterations=smooth_iterations,
        decimate_ratio=decimate_ratio,
        wn_weight=wn_weight,
        wn_threshold=wn_threshold,
        wn_mode=wn_mode,
    )
    _apply_triangulate_optional(
        obj,
        use_triangulate=use_triangulate,
        tri_min_vertices=tri_min_vertices,
    )
    reorder_modifier_stack(
        context,
        obj,
        DYNA_STACK_MOD_NAMES,
        use_triangulate=use_triangulate,
    )


def bevel_wn_kwargs_from_scene(scn: bpy.types.Scene) -> dict[str, object]:
    return {
        'wn_weight': scn.lks_bevel_wn_weight if hasattr(scn, 'lks_bevel_wn_weight') else 50,
        'wn_threshold': scn.lks_bevel_wn_threshold if hasattr(scn, 'lks_bevel_wn_threshold') else 0.01,
        'wn_mode': scn.lks_bevel_wn_mode if hasattr(scn, 'lks_bevel_wn_mode') else 'FACE_AREA',
    }


def bevel_mod_kwargs_from_scene(scn: bpy.types.Scene) -> dict[str, object]:
    return {
        'use_limit': scn.lks_bevel_use_limit if hasattr(scn, 'lks_bevel_use_limit') else True,
        'use_angle': scn.lks_bevel_use_angle if hasattr(scn, 'lks_bevel_use_angle') else False,
        'bevel_angle': scn.lks_bevel_angle if hasattr(scn, 'lks_bevel_angle') else BEVEL_ANGLE_DEFAULT,
        'angle_size': scn.lks_bevel_angle_size if hasattr(scn, 'lks_bevel_angle_size') else BEVEL_ANGLE_SIZE_DEFAULT,
        'cusp_angle': scn.lks_bevel_cusp_angle if hasattr(scn, 'lks_bevel_cusp_angle') else BEVEL_CUSP_ANGLE_DEFAULT,
    }


def clear_bevel_section_modifiers(obj: bpy.types.Object) -> int:
    removed = 0
    migrate_legacy_bevel_modifiers(obj)
    for mod_name in BEVEL_MANAGED_MOD_NAMES:
        mod = obj.modifiers.get(mod_name)
        if mod is not None:
            obj.modifiers.remove(mod)
            removed += 1
    for legacy_name in _LEGACY_TO_LKS_NAME:
        mod = obj.modifiers.get(legacy_name)
        if mod is not None:
            obj.modifiers.remove(mod)
            removed += 1
    return removed


__all__ = [
    'BEVEL_MANAGED_MOD_NAMES',
    'BEVEL_MODE_DYNA',
    'BEVEL_MODE_FWN',
    'BEVEL_MODE_SUBSURF',
    'apply_dynamesh_stack',
    'apply_fwn_stack',
    'apply_subsurf_stack',
    'bevel_mod_kwargs_from_scene',
    'bevel_wn_kwargs_from_scene',
    'clear_bevel_section_modifiers',
    'default_bevel_size_from_object',
    'default_dynamesh_voxel_size',
    'iter_mesh_selection',
    'set_bevel_managed_visibility',
    'toggle_bevel_managed_visibility',
]

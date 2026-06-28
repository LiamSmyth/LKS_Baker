import bpy

from .lks_constants import (
    LEGACY_MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    LEGACY_MOD_NAME_NORMALS_TRIANGULATE,
    LEGACY_MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    MOD_NAME_NORMALS_TRIANGULATE,
    MOD_NAME_NORMALS_WEIGHTED_NORMAL,
)
from .modifier_helpers import (
    ensure_modifiers_visible_on_apply,
    modifier_visibility_is_on,
    place_modifiers_at_tail_block,
    set_modifier_all_visibility,
    set_modifier_pin_to_last_safe,
)

from .mesh_mode_helpers import edit_mode_for_ops
from .shading_helpers import (
    _assign_modifier_name,
    consolidate_smooth_by_angle_modifiers,
    find_smooth_by_angle_modifier,
    is_smooth_by_angle_modifier,
)

NORMAL_MODIFIERS_STACK_NAMES = (
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    MOD_NAME_NORMALS_TRIANGULATE,
)

LEGACY_NORMAL_MOD_NAMES = (
    LEGACY_MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    LEGACY_MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    LEGACY_MOD_NAME_NORMALS_TRIANGULATE,
)

NORMAL_MODIFIERS_MANAGED_NAMES = NORMAL_MODIFIERS_STACK_NAMES + LEGACY_NORMAL_MOD_NAMES

SBA_MOD_NAMES = (
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    LEGACY_MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
)

# Backward-compatible alias used by visibility helpers.
SMART_NORMALS_MOD_NAMES = NORMAL_MODIFIERS_STACK_NAMES


def iter_mesh_selection(context: bpy.types.Context) -> list[bpy.types.Object]:
    return [obj for obj in context.selected_objects if obj.type == 'MESH']


def iter_scope_modifier_names(
    obj: bpy.types.Object,
    scope: str,
) -> list[str]:
    names: list[str] = []
    for mod in obj.modifiers:
        name = mod.name
        if scope == 'SBA':
            if name in SBA_MOD_NAMES:
                names.append(name)
            elif name == MOD_NAME_NORMALS_SMOOTH_BY_ANGLE and is_smooth_by_angle_modifier(mod):
                names.append(name)
        elif scope == 'SMART':
            if name in NORMAL_MODIFIERS_MANAGED_NAMES:
                names.append(name)
            elif name == MOD_NAME_NORMALS_SMOOTH_BY_ANGLE and is_smooth_by_angle_modifier(mod):
                names.append(name)
    return names


def get_live_modifier(
    obj: bpy.types.Object,
    mod_name: str,
) -> bpy.types.Modifier | None:
    if mod_name not in obj.modifiers:
        return None
    return obj.modifiers.get(mod_name)


def set_modifier_visibility(
    obj: bpy.types.Object,
    mod_name: str,
    visible: bool,
) -> bool:
    """Set all modifier visibility RNA props (viewport, render, edit mode, on cage, …)."""
    mod = get_live_modifier(obj, mod_name)
    if mod is None:
        return False
    set_modifier_all_visibility(mod, visible)
    return True


def set_scope_modifier_visibility(
    objects: list[bpy.types.Object],
    scope: str,
    visible: bool,
) -> int:
    count = 0
    for obj in objects:
        for mod_name in iter_scope_modifier_names(obj, scope):
            if set_modifier_visibility(obj, mod_name, visible):
                count += 1
    return count


def toggle_scope_modifier_visibility(
    objects: list[bpy.types.Object],
    scope: str,
) -> int:
    toggle_state = True
    for obj in objects:
        for mod_name in iter_scope_modifier_names(obj, scope):
            mod = get_live_modifier(obj, mod_name)
            if mod is not None:
                toggle_state = not modifier_visibility_is_on(mod)
                break
        else:
            continue
        break

    return set_scope_modifier_visibility(objects, scope, toggle_state)


def clear_custom_split_normals(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> bool:
    mesh = obj.data
    if not mesh.has_custom_normals:
        return False

    with edit_mode_for_ops(context, obj):
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    return True


def clear_sba_modifier(obj: bpy.types.Object) -> int:
    removed = 0
    for mod_name in SBA_MOD_NAMES:
        mod = obj.modifiers.get(mod_name)
        if mod is not None:
            obj.modifiers.remove(mod)
            removed += 1
    return removed


def _pick_modifier_by_preferred_names(
    obj: bpy.types.Object,
    candidates: list[bpy.types.Modifier],
    preferred_names: tuple[str, ...],
) -> bpy.types.Modifier | None:
    if not candidates:
        return None
    candidate_set = set(candidates)
    for name in preferred_names:
        mod = obj.modifiers.get(name)
        if mod is not None and mod in candidate_set:
            return mod
    return candidates[0]


def _rename_modifier_to_lks_name(
    obj: bpy.types.Object,
    mod: bpy.types.Modifier,
    lks_name: str,
) -> bpy.types.Modifier | None:
    if mod.name == lks_name:
        return mod
    existing = obj.modifiers.get(lks_name)
    if existing is not None and existing is not mod:
        if existing.type == mod.type:
            return existing
        existing.name = f"{existing.name}_bak"
    mod.name = lks_name
    return obj.modifiers.get(lks_name) or mod


def consolidate_weighted_normal_modifiers(
    obj: bpy.types.Object,
    *,
    keeper_name: str | None = None,
) -> bpy.types.WeightedNormalModifier | None:
    """Keep one Weighted Normal modifier on obj; remove extras."""
    candidates = [mod for mod in obj.modifiers if mod.type == 'WEIGHTED_NORMAL']
    if not candidates:
        return None

    preferred_names: list[str] = []
    if keeper_name:
        preferred_names.append(keeper_name)
    preferred_names.extend((
        MOD_NAME_NORMALS_WEIGHTED_NORMAL,
        LEGACY_MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    ))
    keeper = _pick_modifier_by_preferred_names(obj, candidates, tuple(preferred_names))
    if keeper is None:
        return None

    keeper_name_live = keeper.name
    for mod in list(obj.modifiers):
        if mod.type == 'WEIGHTED_NORMAL' and mod.name != keeper_name_live:
            obj.modifiers.remove(mod)

    live = obj.modifiers.get(keeper_name_live)
    if live is not None and live.type == 'WEIGHTED_NORMAL':
        return live
    for mod in obj.modifiers:
        if mod.type == 'WEIGHTED_NORMAL':
            return mod
    return None


def consolidate_triangulate_modifiers(
    obj: bpy.types.Object,
    *,
    keeper_name: str | None = None,
) -> bpy.types.TriangulateModifier | None:
    """Keep one Triangulate modifier on obj; remove extras."""
    candidates = [mod for mod in obj.modifiers if mod.type == 'TRIANGULATE']
    if not candidates:
        return None

    preferred_names: list[str] = []
    if keeper_name:
        preferred_names.append(keeper_name)
    preferred_names.extend((
        MOD_NAME_NORMALS_TRIANGULATE,
        LEGACY_MOD_NAME_NORMALS_TRIANGULATE,
    ))
    keeper = _pick_modifier_by_preferred_names(obj, candidates, tuple(preferred_names))
    if keeper is None:
        return None

    keeper_name_live = keeper.name
    for mod in list(obj.modifiers):
        if mod.type == 'TRIANGULATE' and mod.name != keeper_name_live:
            obj.modifiers.remove(mod)

    live = obj.modifiers.get(keeper_name_live)
    if live is not None and live.type == 'TRIANGULATE':
        return live
    for mod in obj.modifiers:
        if mod.type == 'TRIANGULATE':
            return mod
    return None


def find_lks_smooth_by_angle_modifier(
    obj: bpy.types.Object,
) -> bpy.types.Modifier | None:
    for name in SBA_MOD_NAMES:
        mod = find_smooth_by_angle_modifier(obj, name)
        if mod is not None:
            return mod
    return find_smooth_by_angle_modifier(obj)


def find_lks_weighted_normal_modifier(
    obj: bpy.types.Object,
) -> bpy.types.WeightedNormalModifier | None:
    for name in (
        MOD_NAME_NORMALS_WEIGHTED_NORMAL,
        LEGACY_MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    ):
        mod = obj.modifiers.get(name)
        if mod is not None and mod.type == 'WEIGHTED_NORMAL':
            return mod
    for mod in obj.modifiers:
        if mod.type == 'WEIGHTED_NORMAL':
            return mod
    return None


def find_lks_triangulate_modifier(
    obj: bpy.types.Object,
) -> bpy.types.TriangulateModifier | None:
    for name in (
        MOD_NAME_NORMALS_TRIANGULATE,
        LEGACY_MOD_NAME_NORMALS_TRIANGULATE,
    ):
        mod = obj.modifiers.get(name)
        if mod is not None and mod.type == 'TRIANGULATE':
            return mod
    for mod in obj.modifiers:
        if mod.type == 'TRIANGULATE':
            return mod
    return None


def apply_lks_normals_tail_pins(obj: bpy.types.Object) -> None:
    """Pin SBA, WN, and Triangulate to the stack tail when RNA allows.

    Pin in reverse eval order (Tri → WN → SBA). Blender inserts each newly
    pinned modifier above prior pinned entries, so forward pin would invert the
    trio to Tri, WN, SBA top-to-bottom in the UI.
    """
    for mod in (
        find_lks_triangulate_modifier(obj),
        find_lks_weighted_normal_modifier(obj),
        find_lks_smooth_by_angle_modifier(obj),
    ):
        if mod is not None:
            set_modifier_pin_to_last_safe(mod, True)


def ensure_lks_normals_tail_stack(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    use_triangulate: bool | None = None,
) -> tuple[dict[str, bpy.types.Modifier | None], int]:
    """Dedupe, rename, pin, and order the LKS normals tail trio (SBA → WN → Tri).

    Detects modifiers by type (not name). Non-LKS duplicates are removed; the
    keeper is renamed to LKS constants. Returns live modifier references for
    callers to update settings in place, plus count of stack moves performed.
    """
    smooth_mod = consolidate_smooth_by_angle_modifiers(
        obj,
        keeper_name=MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    )
    weighted_mod = consolidate_weighted_normal_modifiers(
        obj,
        keeper_name=MOD_NAME_NORMALS_WEIGHTED_NORMAL,
    )
    tri_mod = consolidate_triangulate_modifiers(
        obj,
        keeper_name=MOD_NAME_NORMALS_TRIANGULATE,
    )

    if use_triangulate is False and tri_mod is not None:
        obj.modifiers.remove(tri_mod)
        tri_mod = None

    if smooth_mod is not None:
        smooth_mod = _assign_modifier_name(
            obj,
            smooth_mod,
            MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
        )
    if weighted_mod is not None:
        weighted_mod = _rename_modifier_to_lks_name(
            obj,
            weighted_mod,
            MOD_NAME_NORMALS_WEIGHTED_NORMAL,
        )
    if tri_mod is not None:
        tri_mod = _rename_modifier_to_lks_name(
            obj,
            tri_mod,
            MOD_NAME_NORMALS_TRIANGULATE,
        )

    tail_names: list[str] = []
    if smooth_mod is not None:
        tail_names.append(smooth_mod.name)
    if weighted_mod is not None:
        tail_names.append(weighted_mod.name)
    if tri_mod is not None:
        tail_names.append(tri_mod.name)

    if tail_names:
        moved = place_modifiers_at_tail_block(context, obj, tail_names)
    else:
        moved = 0

    smooth_mod = find_lks_smooth_by_angle_modifier(obj)
    weighted_mod = find_lks_weighted_normal_modifier(obj)
    tri_mod = find_lks_triangulate_modifier(obj)

    apply_lks_normals_tail_pins(obj)
    ensure_modifiers_visible_on_apply(smooth_mod, weighted_mod, tri_mod)

    return {
        'smooth_by_angle': smooth_mod,
        'weighted_normal': weighted_mod,
        'triangulate': tri_mod,
    }, moved


def ensure_lks_normals_tail_order(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    use_triangulate: bool | None = None,
) -> int:
    """Backward-compatible wrapper; returns count of modifiers moved."""
    _, moved = ensure_lks_normals_tail_stack(context, obj, use_triangulate=use_triangulate)
    return moved


def clear_normal_modifiers_stack(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> int:
    clear_custom_split_normals(context, obj)

    removed = 0
    for mod_name in NORMAL_MODIFIERS_MANAGED_NAMES:
        mod = obj.modifiers.get(mod_name)
        if mod is not None:
            obj.modifiers.remove(mod)
            removed += 1
    return removed

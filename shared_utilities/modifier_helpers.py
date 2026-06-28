import bpy

from .mesh_mode_helpers import object_mode_for_ops

# Modifier RNA visibility flags (excludes show_expanded — UI fold state, not visibility).
MODIFIER_VISIBILITY_PROPS: tuple[str, ...] = (
    'show_viewport',
    'show_render',
    'show_in_editmode',
    'show_on_cage',
)

# NODES (Smooth by Angle): setting show_in_editmode has caused ACCESS_VIOLATION on some
# Blender 5.1 builds — skip that prop; viewport/render/on-cage are still set.
_MODIFIER_VISIBILITY_SKIP_PROPS: dict[str, tuple[str, ...]] = {
    'NODES': ('show_in_editmode',),
}


def set_modifier_all_visibility(
    mod: bpy.types.Modifier,
    visible: bool,
) -> list[str]:
    """Set every visibility RNA prop present on mod. Returns names that were written."""
    applied: list[str] = []
    skip = _MODIFIER_VISIBILITY_SKIP_PROPS.get(mod.type, ())
    for prop in MODIFIER_VISIBILITY_PROPS:
        if prop in skip:
            continue
        if not hasattr(mod, prop):
            continue
        try:
            setattr(mod, prop, visible)
            applied.append(prop)
        except (AttributeError, TypeError):
            pass
    return applied


def modifier_visibility_is_on(mod: bpy.types.Modifier) -> bool:
    """True when any visibility prop on mod is enabled; falls back to show_viewport."""
    saw_prop = False
    for prop in MODIFIER_VISIBILITY_PROPS:
        if not hasattr(mod, prop):
            continue
        try:
            saw_prop = True
            if bool(getattr(mod, prop)):
                return True
        except (AttributeError, TypeError):
            pass
    if saw_prop:
        return False
    return bool(getattr(mod, 'show_viewport', True))


def ensure_modifiers_visible_on_apply(
    *mods: bpy.types.Modifier | None,
) -> None:
    """Enable all visibility modes on modifiers after LKS create/update."""
    for mod in mods:
        if mod is not None:
            set_modifier_all_visibility(mod, True)


_TAIL_BEVEL_SUBSURF_TYPES: tuple[str, ...] = ('BEVEL', 'SUBSURF')


def modifier_is_pinned_to_last(mod: bpy.types.Modifier) -> bool:
    """True when the modifier is pinned to the stack tail."""
    return bool(getattr(mod, 'use_pin_to_last', False))


def is_bevel_or_subsurf_modifier(mod: bpy.types.Modifier) -> bool:
    """True for any bevel or subsurf modifier (including LKS-named stacks)."""
    return mod.type in _TAIL_BEVEL_SUBSURF_TYPES


def compute_insert_index_before_bevel_subsurf_tail(
    obj: bpy.types.Object,
    *,
    exclude_name: str | None = None,
) -> int:
    """Stack index for a new modifier before trailing bevel/subsurf and pinned blocks.

    Walks backwards through the non-pinned prefix, skipping a contiguous tail of
    BEVEL and SUBSURF modifiers. Pinned modifiers (``use_pin_to_last``) are never
    displaced. ``exclude_name`` omits the modifier being placed from the walk so a
    newly appended mirror does not anchor the trailing bevel/subsurf block.
    """
    mods = obj.modifiers
    count = len(mods)
    if count == 0:
        return 0

    first_pinned = count
    for i, mod in enumerate(mods):
        if exclude_name and mod.name == exclude_name:
            continue
        if modifier_is_pinned_to_last(mod):
            first_pinned = i
            break

    insert_idx = first_pinned
    i = first_pinned - 1
    while i >= 0:
        mod = mods[i]
        if exclude_name and mod.name == exclude_name:
            i -= 1
            continue
        if is_bevel_or_subsurf_modifier(mod):
            insert_idx = i
            i -= 1
        else:
            break

    return insert_idx


def place_modifier_before_bevel_subsurf_tail(
    context,
    obj: bpy.types.Object,
    modifier_name: str,
) -> bool:
    """Move ``modifier_name`` before trailing bevel/subsurf and pinned blocks."""
    index = compute_insert_index_before_bevel_subsurf_tail(
        obj,
        exclude_name=modifier_name,
    )
    return move_modifier_to_index(context, obj, modifier_name, index)


def set_modifier_pin_to_last_safe(mod: bpy.types.Modifier, pin: bool) -> bool:
    """Set use_pin_to_last; NODES (Smooth by Angle) is attempted inside try/except.

    On builds where pinning NODES modifiers crashes, this returns False and callers
    should rely on index reordering to keep the modifier at the stack tail.
    """
    if not hasattr(mod, 'use_pin_to_last'):
        return False
    try:
        mod.use_pin_to_last = pin
    except (AttributeError, RuntimeError, TypeError):
        return False
    return True


def move_modifier_to_index(context, obj, modifier_name: str, index: int) -> bool:
    """Move a modifier to a specific index in the stack.
    
    Args:
        context: The Blender context.
        obj: The object containing the modifier.
        modifier_name: Name of the modifier to move.
        index: Target index in the modifier stack.
        
    Returns:
        True if successful, False otherwise.
    """
    mods = obj.modifiers
    if modifier_name not in mods:
        return False
    
    mod = mods[modifier_name]
    
    set_modifier_pin_to_last_safe(mod, False)
    
    current_idx = mods.find(modifier_name)
    if current_idx < 0 or current_idx == index:
        return True  # Already at target or not found
    
    target_idx = max(0, min(index, len(mods) - 1))
    
    with object_mode_for_ops(context, obj):
        bpy.ops.object.modifier_move_to_index(modifier=modifier_name, index=target_idx)
    
    return True


def reorder_modifiers_before_type(context, obj, modifier_names: list, before_type: str) -> int:
    """Reorder a list of modifiers to appear before a specific modifier type.
    
    The modifiers will be placed in the order given, just before the first
    modifier of the specified type. If no modifier of that type exists,
    they will be placed at the end of the stack.
    
    Args:
        context: The Blender context.
        obj: The object containing the modifiers.
        modifier_names: List of modifier names to reorder, in desired order.
        before_type: Modifier type string (e.g., 'MIRROR', 'BOOLEAN') to place before.
        
    Returns:
        The number of modifiers successfully moved.
    """
    mods = obj.modifiers
    moved_count = 0
    
    # Filter to only existing modifiers
    existing_names = [name for name in modifier_names if name in mods]
    if not existing_names:
        return 0
    
    for name in existing_names:
        mod = mods.get(name)
        if mod is not None:
            set_modifier_pin_to_last_safe(mod, False)

    # Move each modifier to the position just before the first 'before_type' modifier
    # We process in order, and each move places the modifier at the correct relative position
    for name in existing_names:
        # Find current position of this modifier
        current_idx = mods.find(name)
        if current_idx < 0:
            continue
        
        # Find the target index: just before first modifier of before_type
        # (excluding our own modifiers from the search)
        target_idx = len(mods)
        for i, mod in enumerate(mods):
            if mod.type == before_type and mod.name not in existing_names:
                target_idx = i
                break
        
        # If current modifier is already at or after target, move it to target
        # If it's before target, we need to account for the fact that moving
        # removes it from its current position first
        if current_idx >= target_idx:
            # Modifier is after target position, move to target_idx
            with object_mode_for_ops(context, obj):
                bpy.ops.object.modifier_move_to_index(modifier=name, index=target_idx)
            moved_count += 1
        elif current_idx < target_idx - 1:
            # Modifier is before target, move to target_idx - 1
            # (because removing it will shift the target index down by 1)
            with object_mode_for_ops(context, obj):
                bpy.ops.object.modifier_move_to_index(modifier=name, index=target_idx - 1)
            moved_count += 1
        # else: modifier is at target_idx - 1, already in correct position
    
    # Now ensure they are in the correct internal order among themselves
    # Process from second to last, ensuring each is after the previous
    for i in range(1, len(existing_names)):
        prev_name = existing_names[i - 1]
        curr_name = existing_names[i]
        
        prev_idx = mods.find(prev_name)
        curr_idx = mods.find(curr_name)
        
        if prev_idx >= 0 and curr_idx >= 0 and curr_idx <= prev_idx:
            # Current is at or before previous, move it to just after previous
            with object_mode_for_ops(context, obj):
                bpy.ops.object.modifier_move_to_index(modifier=curr_name, index=prev_idx + 1)
            moved_count += 1
    
    return moved_count


def reorder_modifiers_to_end(context, obj, modifier_names: list) -> int:
    """Reorder a list of modifiers to the end of the stack.

    Prefer :func:`place_modifiers_at_tail_block` when pin-to-last will follow;
    sequential move-to-end is equivalent for unpinned stacks only.
    """
    return place_modifiers_at_tail_block(context, obj, modifier_names)


def place_modifiers_at_tail_block(
    context,
    obj,
    modifier_names: list[str],
) -> int:
    """Place modifiers contiguously at the stack tail in evaluation order.

    ``modifier_names`` is eval order (first entry = lowest tail index). Targets
    ``n-k .. n-1`` for ``k`` existing names. Unpins each modifier before moving.
    """
    mods = obj.modifiers
    existing_names = [name for name in modifier_names if name in mods]
    if not existing_names:
        return 0

    for name in existing_names:
        mod = mods.get(name)
        if mod is not None:
            set_modifier_pin_to_last_safe(mod, False)

    moved_count = 0
    tail_start = len(mods) - len(existing_names)
    for i, name in enumerate(reversed(existing_names)):
        target_idx = tail_start + (len(existing_names) - 1 - i)
        current_idx = mods.find(name)
        if current_idx < 0 or current_idx == target_idx:
            continue
        with object_mode_for_ops(context, obj):
            bpy.ops.object.modifier_move_to_index(modifier=name, index=target_idx)
        moved_count += 1

    return moved_count


def match_modifier_properties(source_modifier : bpy.types.Modifier, target_modifier : bpy.types.Modifier):
    """Matches properties of the target modifier to those of the source modifier.

    Args:
        source_modifier: The modifier to copy properties from.
        target_modifier: The modifier to copy properties to.
    """
    for prop in dir(source_modifier):
        # Check if the property exists in target and is writable
        if hasattr(target_modifier, prop) and not prop.startswith("_"):
            try:
                setattr(target_modifier, prop, getattr(source_modifier, prop))
            except AttributeError:
                # Handle read-only properties or other exceptions
                pass

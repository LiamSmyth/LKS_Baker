import bpy
import math
from pathlib import Path

from .geonodes_modifier_helpers import (
    get_nodes_modifier_input,
    resolve_modifier_input_identifier,
    set_nodes_modifier_input,
)
from .mesh_helpers import refresh_object_viewport
from .lks_constants import (
    LEGACY_MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
)
from .mesh_mode_helpers import object_mode_for_ops
from .modifier_helpers import (
    set_modifier_all_visibility,
    set_modifier_pin_to_last_safe,
)


SMOOTH_BY_ANGLE_NODE_GROUP_NAMES = ("Smooth by Angle", "SmoothByAngle")
SMOOTH_BY_ANGLE_NODE_GROUP_NAME = "Smooth by Angle"

KNOWN_SBA_MODIFIER_NAMES = (
    MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    LEGACY_MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    SMOOTH_BY_ANGLE_NODE_GROUP_NAME,
)

# Prefer the 5.1 essentials bundle path first; older builds used a standalone blend.
ESSENTIALS_SMOOTH_BY_ANGLE_IDS = (
    "nodes/geometry_nodes_essentials.blend/NodeTree/Smooth by Angle",
    "nodes\\geometry_nodes_essentials.blend\\NodeTree\\Smooth by Angle",
    "geometry_nodes/smooth_by_angle.blend/NodeTree/Smooth by Angle",
    "geometry_nodes\\smooth_by_angle.blend\\NodeTree\\Smooth by Angle",
)


def _node_group_looks_like_smooth_by_angle(node_group: bpy.types.NodeTree) -> bool:
    ng_name = node_group.name
    if ng_name in SMOOTH_BY_ANGLE_NODE_GROUP_NAMES:
        return True
    ng_lower = ng_name.lower()
    return "smooth" in ng_lower and "angle" in ng_lower


def is_smooth_by_angle_modifier(mod: bpy.types.Modifier) -> bool:
    """Return True if modifier is a Smooth by Angle geometry nodes modifier."""
    if mod.type != 'NODES':
        return False
    if mod.name in KNOWN_SBA_MODIFIER_NAMES:
        return True
    if mod.node_group is None:
        return False
    return _node_group_looks_like_smooth_by_angle(mod.node_group)


def find_smooth_by_angle_modifier(
    obj: bpy.types.Object,
    name: str | None = None,
) -> bpy.types.Modifier | None:
    """Find a Smooth by Angle modifier on obj, optionally matching a modifier name."""
    if name and name in obj.modifiers:
        mod = obj.modifiers[name]
        if is_smooth_by_angle_modifier(mod):
            return mod
    for mod in obj.modifiers:
        if is_smooth_by_angle_modifier(mod):
            return mod
    return None


def _live_smooth_by_angle_modifier(
    obj: bpy.types.Object,
    modifier_name: str | None = None,
) -> bpy.types.Modifier | None:
    """Re-fetch a Smooth by Angle modifier after stack mutations."""
    if modifier_name and modifier_name in obj.modifiers:
        mod = obj.modifiers[modifier_name]
        if is_smooth_by_angle_modifier(mod):
            return mod
    return find_smooth_by_angle_modifier(obj, modifier_name)


def consolidate_smooth_by_angle_modifiers(
    obj: bpy.types.Object,
    *,
    keeper_name: str | None = None,
) -> bpy.types.Modifier | None:
    """Keep one Smooth by Angle modifier on obj; remove extras only."""
    candidates = [mod for mod in obj.modifiers if is_smooth_by_angle_modifier(mod)]
    if not candidates:
        return None

    keeper: bpy.types.Modifier | None = None
    preferred_names: list[str] = []
    if keeper_name:
        preferred_names.append(keeper_name)
    preferred_names.extend((
        MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
        LEGACY_MOD_NAME_NORMALS_SMOOTH_BY_ANGLE,
    ))
    for name in preferred_names:
        mod = find_smooth_by_angle_modifier(obj, name)
        if mod is not None:
            keeper = mod
            break
    if keeper is None:
        keeper = candidates[0]

    keeper_name_live = keeper.name
    for mod in list(obj.modifiers):
        if is_smooth_by_angle_modifier(mod) and mod.name != keeper_name_live:
            obj.modifiers.remove(mod)

    return _live_smooth_by_angle_modifier(obj, keeper_name_live)


def _object_override(context: bpy.types.Context, obj: bpy.types.Object) -> dict:
    return {
        "active_object": obj,
        "object": obj,
        "selected_objects": [obj],
        "selected_editable_objects": [obj],
    }


def set_mesh_shade_smooth(obj: bpy.types.Object) -> None:
    """Enable smooth shading on all faces without bpy.ops (mode-safe)."""
    mesh = obj.data
    if not isinstance(mesh, bpy.types.Mesh):
        return

    poly_count = len(mesh.polygons)
    if poly_count == 0:
        return

    mesh.polygons.foreach_set("use_smooth", [True] * poly_count)
    mesh.update()


def _blender_install_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add_root(path: Path | str | None) -> None:
        if not path:
            return
        resolved = str(Path(path).resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(Path(resolved))

    try:
        add_root(Path(bpy.utils.resource_path('LOCAL')))
    except Exception:
        pass

    try:
        add_root(Path(bpy.app.binary_path).parent)
    except Exception:
        pass

    return roots


def _smooth_by_angle_blend_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()

    for root in _blender_install_roots():
        for rel in (
            Path("datafiles") / "assets" / "nodes" / "geometry_nodes_essentials.blend",
            Path("datafiles") / "assets" / "geometry_nodes" / "smooth_by_angle.blend",
        ):
            blend_path = (root / rel).resolve()
            key = str(blend_path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(blend_path)

    return paths


def _find_loaded_smooth_by_angle_node_group() -> bpy.types.NodeTree | None:
    group = bpy.data.node_groups.get(SMOOTH_BY_ANGLE_NODE_GROUP_NAME)
    if group is not None:
        return group

    for group in bpy.data.node_groups:
        if "smooth" in group.name.lower() and "angle" in group.name.lower():
            return group

    return None


def _pick_smooth_by_angle_name(available_names: list[str]) -> str | None:
    if SMOOTH_BY_ANGLE_NODE_GROUP_NAME in available_names:
        return SMOOTH_BY_ANGLE_NODE_GROUP_NAME

    for name in available_names:
        if "smooth" in name.lower() and "angle" in name.lower():
            return name

    return None


def _load_smooth_by_angle_via_libraries(blend_path: Path, *, assets_only: bool) -> bpy.types.NodeTree | None:
    with bpy.data.libraries.load(str(blend_path), assets_only=assets_only, link=False) as (data_from, data_to):
        group_name = _pick_smooth_by_angle_name(list(data_from.node_groups))
        if group_name is None:
            return None
        data_to.node_groups = [group_name]

    return _find_loaded_smooth_by_angle_node_group()


def _load_smooth_by_angle_via_append(blend_path: Path) -> bpy.types.NodeTree | None:
    blend_str = blend_path.as_posix()
    directory = f"{blend_str}/NodeTree/"
    bpy.ops.wm.append(
        filepath=f"{directory}{SMOOTH_BY_ANGLE_NODE_GROUP_NAME}",
        directory=directory,
        filename=SMOOTH_BY_ANGLE_NODE_GROUP_NAME,
    )
    return _find_loaded_smooth_by_angle_node_group()


def _load_smooth_by_angle_node_group() -> bpy.types.NodeTree | None:
    existing = _find_loaded_smooth_by_angle_node_group()
    if existing is not None:
        return existing

    for blend_path in _smooth_by_angle_blend_paths():
        if not blend_path.is_file():
            continue

        for loader in (
            lambda path=blend_path: _load_smooth_by_angle_via_libraries(path, assets_only=True),
            lambda path=blend_path: _load_smooth_by_angle_via_libraries(path, assets_only=False),
            lambda path=blend_path: _load_smooth_by_angle_via_append(path),
        ):
            try:
                group = loader()
            except Exception:
                group = None
            if group is not None:
                return group

    return None


def _smooth_by_angle_input_key(smooth_mod: bpy.types.Modifier) -> str | None:
    if smooth_mod.type != 'NODES' or smooth_mod.node_group is None:
        return None

    for item in smooth_mod.node_group.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == 'INPUT':
            if 'angle' in item.name.lower():
                return item.identifier

    for key in ("Input_1", "Socket_2", "Socket_1"):
        if resolve_modifier_input_identifier(smooth_mod, key):
            return key

    return None


def set_smooth_by_angle_angle(smooth_mod: bpy.types.Modifier, angle: float) -> bool:
    """Set the angle input on an existing Smooth by Angle modifier.

    Returns True when the stored angle value changed.
    """
    key = _smooth_by_angle_input_key(smooth_mod)
    if key is None:
        return False

    current = get_nodes_modifier_input(smooth_mod, key)
    if current is not None and abs(float(current) - angle) < 1e-7:
        return False

    return set_nodes_modifier_input(smooth_mod, key, angle)


def set_smooth_by_angle_ignore_sharps(smooth_mod: bpy.types.Modifier, ignore_sharps: bool) -> None:
    """Set the ignore-sharp-edges input on a Smooth by Angle modifier."""
    if smooth_mod.type != 'NODES' or smooth_mod.node_group is None:
        return

    for item in smooth_mod.node_group.interface.items_tree:
        if item.item_type != 'SOCKET' or item.in_out != 'INPUT':
            continue
        name_lower = item.name.lower()
        if 'ignore' in name_lower and 'sharp' in name_lower:
            set_nodes_modifier_input(smooth_mod, item.identifier, ignore_sharps)
            return


def _assign_modifier_name(
    obj: bpy.types.Object,
    mod: bpy.types.Modifier,
    target_name: str,
) -> bpy.types.Modifier:
    """Rename mod to target_name, clearing non-SBA blockers from the slot."""
    if mod.name == target_name:
        return mod

    blocker = obj.modifiers.get(target_name)
    if blocker is not None and blocker is not mod:
        if is_smooth_by_angle_modifier(blocker):
            obj.modifiers.remove(blocker)
        else:
            blocker.name = f"{blocker.name}_bak"

    mod.name = target_name
    return obj.modifiers.get(target_name) or mod


def _finalize_smooth_by_angle_modifier(
    smooth_mod: bpy.types.Modifier,
    angle: float,
    *,
    context: bpy.types.Context | None = None,
    modifier_name: str | None,
    pin_to_last: bool | None,
) -> bpy.types.Modifier:
    obj = smooth_mod.id_data
    if set_smooth_by_angle_angle(smooth_mod, angle):
        refresh_object_viewport(context, obj)

    if modifier_name:
        smooth_mod = _assign_modifier_name(obj, smooth_mod, modifier_name)
        live_mod = _live_smooth_by_angle_modifier(obj, modifier_name)
        if live_mod is not None:
            smooth_mod = live_mod

    if pin_to_last is not None:
        set_modifier_pin_to_last_safe(smooth_mod, pin_to_last)

    set_modifier_all_visibility(smooth_mod, True)

    return smooth_mod


def _try_manual_smooth_by_angle_modifier(
    obj: bpy.types.Object,
    *,
    modifier_name: str | None,
) -> bpy.types.Modifier | None:
    existing = consolidate_smooth_by_angle_modifiers(obj, keeper_name=modifier_name)
    if existing is not None:
        return existing

    node_group = _load_smooth_by_angle_node_group()
    if node_group is None:
        return None

    mod_name = modifier_name or SMOOTH_BY_ANGLE_NODE_GROUP_NAME
    if mod_name in obj.modifiers:
        occupied = obj.modifiers[mod_name]
        if is_smooth_by_angle_modifier(occupied):
            return _live_smooth_by_angle_modifier(obj, mod_name)
        if occupied.type == 'NODES':
            if occupied.node_group is None:
                occupied.node_group = node_group
                return _live_smooth_by_angle_modifier(obj, mod_name)
            if _node_group_looks_like_smooth_by_angle(occupied.node_group):
                return _live_smooth_by_angle_modifier(obj, mod_name)
        mod_name = SMOOTH_BY_ANGLE_NODE_GROUP_NAME
        if mod_name in obj.modifiers:
            return consolidate_smooth_by_angle_modifiers(obj, keeper_name=modifier_name)

    smooth_mod = obj.modifiers.new(mod_name, 'NODES')
    smooth_mod.node_group = node_group
    return _live_smooth_by_angle_modifier(obj, mod_name)


def _try_modifier_add_node_group_op(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> bpy.types.Modifier | None:
    if not hasattr(bpy.ops.object, "modifier_add_node_group"):
        return None

    with object_mode_for_ops(context, obj):
        for relative_asset_identifier in ESSENTIALS_SMOOTH_BY_ANGLE_IDS:
            try:
                result = bpy.ops.object.modifier_add_node_group(
                    asset_library_type='ESSENTIALS',
                    asset_library_identifier="",
                    relative_asset_identifier=relative_asset_identifier,
                )
            except RuntimeError:
                continue
            if 'FINISHED' in result:
                smooth_mod = find_smooth_by_angle_modifier(obj)
                if smooth_mod is not None:
                    return smooth_mod

    return None


def _try_shade_auto_smooth_op(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    angle: float,
) -> bpy.types.Modifier | None:
    """Add Smooth by Angle via Blender op only when none exists.

    shade_auto_smooth toggles auto smooth off when already enabled — never call
    it if any Smooth by Angle modifier is present; update angle in place instead.
    """
    existing = consolidate_smooth_by_angle_modifiers(obj)
    if existing is not None:
        if set_smooth_by_angle_angle(existing, angle):
            refresh_object_viewport(context, obj)
        return existing

    try:
        with object_mode_for_ops(context, obj):
            bpy.ops.object.shade_auto_smooth(use_auto_smooth=True, angle=angle)
    except RuntimeError:
        return None

    return find_smooth_by_angle_modifier(obj)


def apply_smooth_by_angle(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    angle: float,
    *,
    modifier_name: str | None = None,
    pin_to_last: bool | None = None,
) -> bpy.types.Modifier | None:
    """Apply Shade Auto Smooth (Smooth by Angle modifier) to a mesh object."""
    if obj.type != 'MESH':
        return None

    smooth_mod = consolidate_smooth_by_angle_modifiers(obj, keeper_name=modifier_name)
    if smooth_mod is not None:
        return _finalize_smooth_by_angle_modifier(
            smooth_mod,
            angle,
            context=context,
            modifier_name=modifier_name,
            pin_to_last=pin_to_last,
        )

    # Direct file load is most reliable on 5.1 builds where shade_auto_smooth's
    # ESSENTIALS lookup can fail even when geometry_nodes_essentials.blend exists.
    modifier_ids_before = {id(mod) for mod in obj.modifiers}
    smooth_mod = _try_manual_smooth_by_angle_modifier(
        obj,
        modifier_name=modifier_name or SMOOTH_BY_ANGLE_NODE_GROUP_NAME,
    )
    if smooth_mod is None:
        smooth_mod = _try_modifier_add_node_group_op(context, obj)
        if smooth_mod is not None:
            smooth_mod = _live_smooth_by_angle_modifier(obj)
        else:
            for mod in obj.modifiers:
                if id(mod) not in modifier_ids_before and is_smooth_by_angle_modifier(mod):
                    smooth_mod = mod
                    break
    if smooth_mod is None:
        smooth_mod = _try_shade_auto_smooth_op(context, obj, angle)
        if smooth_mod is not None:
            smooth_mod = _live_smooth_by_angle_modifier(obj)

    if smooth_mod is None:
        return None

    return _finalize_smooth_by_angle_modifier(
        smooth_mod,
        angle,
        context=context,
        modifier_name=modifier_name,
        pin_to_last=pin_to_last,
    )


def ensure_smooth_by_angle(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    angle: float = math.pi,
) -> bpy.types.Modifier | None:
    """Ensure obj has a Smooth by Angle modifier, adding one only if missing."""
    smooth_mod = consolidate_smooth_by_angle_modifiers(obj)
    if smooth_mod is not None:
        return smooth_mod
    return apply_smooth_by_angle(context, obj, angle)

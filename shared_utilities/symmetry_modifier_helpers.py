"""Helpers for adding / applying LKS symmetry mirror modifiers.

Isolated from operator scripts to satisfy one-operator-per-file guideline.
"""
from __future__ import annotations

import bpy
import bmesh
from mathutils import Vector

from .lks_constants import LEGACY_MOD_NAME_MIRROR, MOD_NAME_MIRROR
from .modifier_helpers import place_modifier_before_bevel_subsurf_tail

LKS_MIRROR_MOD_NAMES = (MOD_NAME_MIRROR, LEGACY_MOD_NAME_MIRROR)

__all__ = [
    'MOD_NAME_MIRROR',
    'LEGACY_MOD_NAME_MIRROR',
    'LKS_MIRROR_MOD_NAMES',
    'is_lks_mirror_name',
    'is_lks_mirror_modifier',
    'iter_lks_mirror_modifiers',
    'find_lks_mirror_modifier',
    'normalize_lks_mirror_name',
    'view_direction_world',
    'world_vector_from_screen_direction',
    'axis_letter_from_world_vector',
    'axis_letter_from_object_vector',
    'choose_object_axis_from_view',
    'choose_world_axis_from_view',
    'ensure_symmetry_modifier',
    'add_symmetry_modifier',
    'setup_mirror_object',
    'ensure_mirror_empty',
    'bisect_clear_half',
    'align_empty_to_vector',
]


def view_direction_world(context: bpy.types.Context) -> Vector:
    rv3d = context.region_data
    if not rv3d:
        return Vector((0, 0, -1))
    # View direction: negative Z axis of view rotation
    return (rv3d.view_rotation @ Vector((0, 0, -1))).normalized()


def world_vector_from_screen_direction(context: bpy.types.Context, screen_direction: str) -> Vector:
    """Map a screen direction token (UP/DOWN/LEFT/RIGHT/IN/OUT) to a world-space vector
    using the current 3D view rotation (same logic as flatten verts operator)."""
    rv3d = getattr(context, 'region_data', None)
    if not rv3d:
        return Vector((0, 0, 0))
    base = {
        'IN': Vector((0, 0, 1)),
        'OUT': Vector((0, 0, -1)),
        'LEFT': Vector((-1, 0, 0)),
        'RIGHT': Vector((1, 0, 0)),
        'UP': Vector((0, 1, 0)),
        'DOWN': Vector((0, -1, 0)),
    }.get(screen_direction, Vector((0, 0, 0)))
    return (rv3d.view_rotation @ base).normalized() if base.length else base


def axis_letter_from_world_vector(vec: Vector) -> str:
    """Return dominant world axis letter for given vector (abs dot test)."""
    if vec.length == 0:
        return 'X'
    vec_n = vec.normalized()
    axes = {
        'X': Vector((1, 0, 0)),
        'Y': Vector((0, 1, 0)),
        'Z': Vector((0, 0, 1)),
    }
    scores = {k: abs(vec_n.dot(a)) for k, a in axes.items()}
    return max(scores, key=scores.get)


def axis_letter_from_object_vector(obj: bpy.types.Object, vec_world: Vector) -> str:
    """Return dominant local axis letter for world vector relative to object's orientation."""
    if vec_world.length == 0:
        return 'X'
    mw3 = obj.matrix_world.to_3x3()
    # Transform world vector into object local space by inverse rotation
    local_vec = mw3.inverted() @ vec_world
    local_vec.normalize()
    comps = {'X': abs(local_vec.x), 'Y': abs(
        local_vec.y), 'Z': abs(local_vec.z)}
    return max(comps, key=comps.get)


def choose_object_axis_from_view(obj: bpy.types.Object, context: bpy.types.Context) -> str:
    """Heuristic: pick dominant perpendicular axis to view.
    If viewing along +/-Y => choose X; along +/-X => choose Y; along +/-Z => choose X.
    Returns one of 'X','Y','Z'."""
    vdir_w = view_direction_world(context)
    mw = obj.matrix_world.to_3x3()
    axes = {
        'X': (mw @ Vector((1, 0, 0))).normalized(),
        'Y': (mw @ Vector((0, 1, 0))).normalized(),
        'Z': (mw @ Vector((0, 0, 1))).normalized(),
    }
    scores = {k: abs(vdir_w.dot(vec)) for k, vec in axes.items()}
    primary = max(scores, key=scores.get)
    if primary == 'Y':
        return 'X'
    if primary == 'X':
        return 'Y'
    return 'X'


def choose_world_axis_from_view(context: bpy.types.Context) -> str:
    """Choose a world axis closest to being perpendicular to view (mirrors object heuristic)."""
    vdir_w = view_direction_world(context)
    axes = {
        'X': Vector((1, 0, 0)),
        'Y': Vector((0, 1, 0)),
        'Z': Vector((0, 0, 1)),
    }
    scores = {k: abs(vdir_w.dot(vec)) for k, vec in axes.items()}
    primary = max(scores, key=scores.get)
    if primary == 'Y':
        return 'X'
    if primary == 'X':
        return 'Y'
    return 'X'


def is_lks_mirror_name(name: str) -> bool:
    """True for primary, numbered stacks (LKS Mirror.001), and legacy names."""
    if name in LKS_MIRROR_MOD_NAMES:
        return True
    prefix = f"{MOD_NAME_MIRROR}."
    if name.startswith(prefix):
        suffix = name[len(prefix):]
        return suffix.isdigit()
    return False


def is_lks_mirror_modifier(modifier: bpy.types.Modifier) -> bool:
    return modifier.type == 'MIRROR' and is_lks_mirror_name(modifier.name)


def normalize_lks_mirror_name(modifier: bpy.types.MirrorModifier) -> None:
    """Migrate legacy name only; preserve numbered stack suffixes."""
    if modifier.name == LEGACY_MOD_NAME_MIRROR:
        modifier.name = MOD_NAME_MIRROR


def iter_lks_mirror_modifiers(
    obj: bpy.types.Object,
) -> list[bpy.types.MirrorModifier]:
    return [m for m in obj.modifiers if is_lks_mirror_modifier(m)]


def find_lks_mirror_modifier(obj: bpy.types.Object) -> bpy.types.MirrorModifier | None:
    """Return the primary LKS mirror (exact MOD_NAME_MIRROR), else legacy."""
    for m in obj.modifiers:
        if m.type == 'MIRROR' and m.name == MOD_NAME_MIRROR:
            return m
    for m in obj.modifiers:
        if m.type == 'MIRROR' and m.name == LEGACY_MOD_NAME_MIRROR:
            normalize_lks_mirror_name(m)
            return m
    return None


def ensure_symmetry_modifier(obj: bpy.types.Object) -> bpy.types.Modifier | None:
    return find_lks_mirror_modifier(obj)


def add_symmetry_modifier(
    obj: bpy.types.Object,
    context: bpy.types.Context | None = None,
) -> bpy.types.Modifier:
    mod = obj.modifiers.new(MOD_NAME_MIRROR, 'MIRROR')
    mod.use_clip = True
    mod.use_mirror_merge = True
    mod.merge_threshold = 0.0001
    if context is not None:
        place_modifier_before_bevel_subsurf_tail(context, obj, mod.name)
    return mod


def setup_mirror_object(context: bpy.types.Context, obj: bpy.types.Object, origin_mode: str, axis_letter: str) -> bpy.types.Object | None:
    """Create / reuse an empty for non-object-origin symmetry centers.
    origin_mode: OBJECT, WORLD, CURSOR
    Returns the empty or None if not needed."""
    if origin_mode == 'OBJECT':
        return None
    name = f"LKS_SymOrigin_{origin_mode}_{axis_letter}"
    empty = bpy.data.objects.get(name)
    if empty is None:
        empty = bpy.data.objects.new(name, None)
        context.collection.objects.link(empty)
    if origin_mode == 'WORLD':
        empty.location = Vector((0, 0, 0))
    elif origin_mode == 'CURSOR':
        empty.location = context.scene.cursor.location.copy()
    return empty


def ensure_mirror_empty(context: bpy.types.Context, obj: bpy.types.Object, origin_mode: str, orientation_mode: str) -> bpy.types.Object | None:
    """Create or reuse an empty used as mirror object based on origin & orientation modes.
    Rules:
      - If both origin & orientation are OBJECT -> return None (no empty needed)
      - Location:
          OBJECT: object's world origin
          WORLD: (0,0,0)
          CURSOR: scene cursor location
      - Orientation:
          WORLD: identity
          VIEW: +X aligned to view direction
          OBJECT: match object's rotation
    Returns the empty (linked) or None.
    """
    if origin_mode == 'OBJECT' and orientation_mode == 'OBJECT':
        return None
    name = f"LKS_SymMirror_{origin_mode}_{orientation_mode}"
    empty = bpy.data.objects.get(name)
    if empty is None:
        empty = bpy.data.objects.new(name, None)
        context.collection.objects.link(empty)
    # Set location
    if origin_mode == 'OBJECT':
        empty.location = obj.matrix_world.translation
    elif origin_mode == 'WORLD':
        empty.location = Vector((0, 0, 0))
    elif origin_mode == 'CURSOR':
        empty.location = context.scene.cursor.location.copy()
    # Set orientation
    if orientation_mode == 'WORLD':
        empty.rotation_euler = (0.0, 0.0, 0.0)
    elif orientation_mode == 'VIEW':
        align_empty_to_vector(empty, view_direction_world(context))
    elif orientation_mode == 'OBJECT':
        empty.matrix_world = obj.matrix_world.to_quaternion().to_matrix().to_4x4()
        empty.location = empty.location  # preserve location
    return empty


def align_empty_to_vector(empty: bpy.types.Object, normal: Vector):
    """Rotate empty so its local +X axis aligns with given normal vector."""
    if normal.length == 0:
        return
    normal = normal.normalized()
    # Construct orientation: X=normal; choose arbitrary up that isn't parallel
    up_guess = Vector((0, 0, 1)) if abs(normal.z) < 0.99 else Vector((0, 1, 0))
    y_axis = up_guess.cross(normal).normalized()
    z_axis = normal.cross(y_axis).normalized()
    mat = Vector((normal.x, y_axis.x, z_axis.x)), Vector(
        (normal.y, y_axis.y, z_axis.y)), Vector((normal.z, y_axis.z, z_axis.z))
    import mathutils
    empty.matrix_world = mathutils.Matrix((
        (normal.x, y_axis.x, z_axis.x, empty.location.x),
        (normal.y, y_axis.y, z_axis.y, empty.location.y),
        (normal.z, y_axis.z, z_axis.z, empty.location.z),
        (0, 0, 0, 1),
    ))


def bisect_clear_half(obj: bpy.types.Object, plane_point: Vector, plane_normal: Vector, clear_positive: bool):
    """True bisect cut along plane then delete one side.
    Uses mesh.bisect to ensure geometry is sliced exactly on plane before removal."""
    # Capture current active & mode (context.mode can be 'EDIT_MESH' while operator expects 'EDIT')
    prev_active = bpy.context.view_layer.objects.active
    prev_mode_raw = bpy.context.mode  # e.g. 'OBJECT', 'EDIT_MESH'
    prev_mode = 'EDIT' if prev_mode_raw.startswith('EDIT') else prev_mode_raw

    # Ensure target object is active
    if bpy.context.view_layer.objects.active != obj:
        bpy.context.view_layer.objects.active = obj

    # Enter edit mode if not already
    if obj.mode != 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')
    # Select all to ensure bisect operates over entire mesh
    bpy.ops.mesh.select_all(action='SELECT')

    # Determine which side Blender should clear.
    # clear_outer removes positive side; clear_inner removes negative side.
    clear_inner = False
    clear_outer = False
    if clear_positive:
        clear_outer = True
    else:
        clear_inner = True

    bpy.ops.mesh.bisect(
        plane_co=plane_point,
        plane_no=plane_normal,
        clear_inner=clear_inner,
        clear_outer=clear_outer,
        use_fill=False,
    )

    # Snap near-plane verts to plane to prevent tiny residual offsets
    try:
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        bm.verts.ensure_lookup_table()
        tol = 1e-6
        for v in bm.verts:
            world_co = obj.matrix_world @ v.co
            dist = (world_co - plane_point).dot(plane_normal)
            if abs(dist) < tol:
                world_snap = world_co - dist * plane_normal
                v.co = obj.matrix_world.inverted() @ world_snap
        bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
    except Exception:
        pass
    # Restore previous mode & active object
    if prev_mode != 'EDIT':
        try:
            bpy.ops.object.mode_set(mode=prev_mode)
        except Exception:
            pass
    else:
        # Already in edit previously; ensure still edit if user was multi-editing
        if bpy.context.mode != 'EDIT_MESH':  # safety
            try:
                bpy.ops.object.mode_set(mode='EDIT')
            except Exception:
                pass
    if prev_active and prev_active != obj:
        bpy.context.view_layer.objects.active = prev_active

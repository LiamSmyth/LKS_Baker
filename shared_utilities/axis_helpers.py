import bpy
from enum import Enum, auto
from mathutils import Vector, Matrix
from typing import List, Dict, Tuple
from .space_xform_helpers import world_vectors_to_local, object_world_axes


class Axis(Enum):
    X = auto()
    Y = auto()
    Z = auto()
    NEG_X = auto()
    NEG_Y = auto()
    NEG_Z = auto()


def coerce_axis(axis: Axis | str) -> Axis:
    """Return the current-module Axis member (reload-safe).

    Blender dev reload can leave stale Enum class objects whose members no longer
    match by identity in match/case or ``axis in (Axis.X, ...)`` checks.
    """
    if isinstance(axis, str):
        name = axis.split(".", 1)[-1] if axis.startswith("Axis.") else axis
        return Axis[name]
    name = getattr(axis, "name", None)
    if not name:
        raise ValueError(f"Cannot coerce axis: {axis!r}")
    return Axis[name]


AXIS_VECTORS = {
    Axis.X: Vector((1, 0, 0)),
    Axis.Y: Vector((0, 1, 0)),
    Axis.Z: Vector((0, 0, 1)),
    Axis.NEG_X: Vector((-1, 0, 0)),
    Axis.NEG_Y: Vector((0, -1, 0)),
    Axis.NEG_Z: Vector((0, 0, -1)),
}


def get_axis_vector(axis: Axis) -> Vector:
    """
    Given an Axis enum, return the corresponding unit vector.
    """
    return AXIS_VECTORS[coerce_axis(axis)]


def get_closest_world_axis(direction: Vector) -> Axis:
    """
    Given a direction vector, return the closest world axis (Axis enum).
    """
    direction = direction.normalized()
    max_dot = -1.0
    closest_axis = None

    for axis, vec in AXIS_VECTORS.items():
        dot = direction.dot(vec)
        if dot > max_dot:
            max_dot = dot
            closest_axis = axis

    return closest_axis


def get_closest_world_axis_vector(direction: Vector) -> Vector:
    """
    Given a direction vector, return the closest world axis as a unit vector.
    """
    closest_axis = get_closest_world_axis(direction)
    return get_axis_vector(closest_axis)


def negate_axis(axis: Axis) -> Axis:
    """
    Given an Axis enum, return the opposite axis.
    """
    match axis:
        case Axis.X:
            return Axis.NEG_X
        case Axis.Y:
            return Axis.NEG_Y
        case Axis.Z:
            return Axis.NEG_Z
        case Axis.NEG_X:
            return Axis.X
        case Axis.NEG_Y:
            return Axis.Y
        case Axis.NEG_Z:
            return Axis.Z
    raise ValueError("Invalid Axis enum value")


def get_negated_axis_vector(axis: Axis) -> Vector:
    """
    Given an Axis enum, return the corresponding negated unit vector.
    """
    negated_axis = negate_axis(axis)
    return get_axis_vector(negated_axis)


def get_closest_local_axis(obj: bpy.types.Object, direction: Vector) -> Axis:
    """
    Given an object and a direction vector in world space,
    return the closest local axis of the object (Axis enum).
    """
    local_dir = world_vectors_to_local([direction], obj)[0]
    return get_closest_world_axis(local_dir)


def get_closest_local_axis_vector(obj: bpy.types.Object, direction: Vector) -> Vector:
    """
    Given an object and a direction vector in world space,
    return the closest local axis of the object as a unit vector.
    """
    closest_axis = get_closest_local_axis(obj, direction)
    return get_axis_vector(closest_axis)


# ----------------------- Additional axis utilities ---------------------------

def axis_to_index(axis: Axis) -> int:
    """
    Map an Axis enum (positive or negative) to its base index (X=0, Y=1, Z=2).
    """
    name = coerce_axis(axis).name
    if name in ("X", "NEG_X"):
        return 0
    if name in ("Y", "NEG_Y"):
        return 1
    if name in ("Z", "NEG_Z"):
        return 2
    raise ValueError(f"Unhandled axis {axis}")


def axis_is_negative(axis: Axis) -> bool:
    """
    Return True if the axis is a negative direction.
    """
    return coerce_axis(axis).name.startswith("NEG_")


def axis_sign(axis: Axis) -> int:
    """
    Return +1 for positive axes, -1 for negative axes.
    """
    return -1 if axis_is_negative(axis) else 1


def index_to_axis(index: int, negative: bool = False) -> Axis:
    """
    Convert an index (0,1,2) plus sign flag to an Axis enum.
    """
    if index == 0:
        return Axis.NEG_X if negative else Axis.X
    if index == 1:
        return Axis.NEG_Y if negative else Axis.Y
    if index == 2:
        return Axis.NEG_Z if negative else Axis.Z
    raise ValueError(f"Invalid axis index {index}")


def axes_primary(positive_only: bool = True) -> List[Axis]:
    """
    Return list of primary axes. If positive_only=False include negatives.
    """
    return [Axis.X, Axis.Y, Axis.Z] if positive_only else [
        Axis.X, Axis.Y, Axis.Z, Axis.NEG_X, Axis.NEG_Y, Axis.NEG_Z
    ]


def scalar_component_on_axis(vec: Vector, axis: Axis) -> float:
    """
    Return signed scalar component of vec along the given world axis.
    """
    axis_vec: Vector = get_axis_vector(axis)
    return vec.dot(axis_vec)


def project_world_vector_onto_axis(vec: Vector, axis: Axis) -> Vector:
    """
    Project a world-space vector onto a world axis (returns the projected vector).
    """
    axis_vec: Vector = get_axis_vector(axis)
    return axis_vec * vec.dot(axis_vec)


def project_world_vector_onto_object_axis(vec: Vector, obj: bpy.types.Object, axis: Axis) -> Vector:
    """
    Project a world-space vector onto an object's oriented (local) axis in world space.
    """
    axis_vec: Vector = object_axis_world(obj, axis)
    return axis_vec * vec.dot(axis_vec)


def object_axis_world(obj: bpy.types.Object, axis: Axis) -> Vector:
    """
    Return the specified local axis of obj expressed as a unit vector in world space (respects object rotation).
    """
    # Use object_world_axes (gives positive X,Y,Z world-space) then apply sign
    x_axis, y_axis, z_axis = object_world_axes(obj)
    base_index: int = axis_to_index(axis)
    base_vec: Vector = (x_axis, y_axis, z_axis)[base_index]
    sig: int = axis_sign(axis)
    w: Vector = (base_vec * sig).normalized()
    return w


def object_axes_world(obj: bpy.types.Object, include_negative: bool = False) -> Dict[Axis, Vector]:
    """
    Return a dict mapping Axis enums to their world-space unit vectors for the object.
    """
    x_axis, y_axis, z_axis = object_world_axes(obj)
    result: Dict[Axis, Vector] = {
        Axis.X: x_axis.normalized(),
        Axis.Y: y_axis.normalized(),
        Axis.Z: z_axis.normalized(),
    }
    if include_negative:
        result[Axis.NEG_X] = (-x_axis).normalized()
        result[Axis.NEG_Y] = (-y_axis).normalized()
        result[Axis.NEG_Z] = (-z_axis).normalized()
    return result


def closest_object_axis(obj: bpy.types.Object, direction: Vector) -> Axis:
    """
    World-space direction -> closest oriented (signed) object axis.
    """
    axes_map: Dict[Axis, Vector] = object_axes_world(
        obj, include_negative=True)
    dir_n: Vector = direction.normalized()
    best_axis: Axis = Axis.X
    best_dot: float = -1.0
    for a, v in axes_map.items():
        d: float = dir_n.dot(v)
        if d > best_dot:
            best_dot = d
            best_axis = a
    return best_axis


def rotate_vector_onto_axis(vec: Vector, target_axis: Axis) -> Matrix:
    """
    Return a 3x3 rotation matrix that rotates the given (non-zero) vector onto the target world axis.
    Uses shortest arc rotation.
    """
    from math import acos
    src: Vector = vec.normalized()
    dst: Vector = get_axis_vector(target_axis)
    dot: float = max(-1.0, min(1.0, src.dot(dst)))
    if dot >= 0.999999:
        return Matrix.Identity(3)
    if dot <= -0.999999:
        # 180 deg: find arbitrary orthogonal axis
        ortho: Vector = Vector((1, 0, 0)) if abs(
            src.x) < 0.9 else Vector((0, 1, 0))
        axis_vec: Vector = src.cross(ortho).normalized()
        return Matrix.Rotation(3.141592653589793, 3, axis_vec)
    angle: float = acos(dot)
    axis_vec = src.cross(dst).normalized()
    return Matrix.Rotation(angle, 3, axis_vec)


def decompose_vector_world_axes(vec: Vector) -> Dict[Axis, float]:
    """
    Decompose a vector into scalar components along positive world axes (X,Y,Z).
    Negative values represent direction toward NEG_* axes.
    """
    return {
        Axis.X: vec.x,
        Axis.Y: vec.y,
        Axis.Z: vec.z,
    }


def normalize_safe(vec: Vector) -> Vector:
    """
    Return normalized copy; zero vector returns zero vector unchanged.
    """
    if vec.length_squared == 0.0:
        return vec.copy()
    return vec.normalized()

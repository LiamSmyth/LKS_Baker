import bpy
from mathutils import Vector, Matrix, Euler
from typing import Iterable, List, Tuple


def local_to_world_vector(local_vec: Vector, obj: bpy.types.Object) -> Vector:
    """
    Convert a vector from local space to world space using the object's transformation matrix.
    """
    return obj.matrix_world.to_3x3() @ local_vec


def world_to_local_vector(world_vec: Vector, obj: bpy.types.Object) -> Vector:
    """
    Convert a vector from world space to local space using the object's transformation matrix.
    """
    return obj.matrix_world.inverted().to_3x3() @ world_vec


def local_to_world_point(local_point: Vector, obj: bpy.types.Object) -> Vector:
    """
    Convert a point from local space to world space using the object's transformation matrix.
    """
    return obj.matrix_world @ local_point


def world_to_local_point(world_point: Vector, obj: bpy.types.Object) -> Vector:
    """
    Convert a point from world space to local space using the object's transformation matrix.
    """
    return obj.matrix_world.inverted() @ world_point


def local_to_local_vector(local_vec: Vector, from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> Vector:
    """
    Convert a vector from one object's local space to another object's local space.
    """
    world_vec = local_to_world_vector(local_vec, from_obj)
    return world_to_local_vector(world_vec, to_obj)


def local_to_local_point(local_point: Vector, from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> Vector:
    """
    Convert a point from one object's local space to another object's local space.
    """
    world_point = local_to_world_point(local_point, from_obj)
    return world_to_local_point(world_point, to_obj)

# ---------------------------------------------------------------------------
# Additional utility conversions & helpers (non-breaking extensions)
# ---------------------------------------------------------------------------


def matrix_local_to_local(from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> Matrix:
    """
    Return a 4x4 matrix that converts coordinates in from_obj local space directly
    into to_obj local space (point transform).
    Usage: p_in_to = matrix_local_to_local(a, b) @ p_in_a
    """
    return to_obj.matrix_world.inverted() @ from_obj.matrix_world


def matrix_local_vector_to_local(from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> Matrix:
    """
    3x3 rotation/scale component for converting a direction/vector in from_obj local
    space to to_obj local space.
    """
    return (to_obj.matrix_world.inverted() @ from_obj.matrix_world).to_3x3()


def transform_points(points: Iterable[Vector], matrix: Matrix) -> List[Vector]:
    """
    Apply a 4x4 matrix to an iterable of points (Vectors).
    Returns a new list of transformed points.
    """
    return [matrix @ p for p in points]


def local_points_to_world(points: Iterable[Vector], obj: bpy.types.Object) -> List[Vector]:
    """
    Batch convert iterable of local-space points to world space.
    Returns list of world-space points.
    """
    mw: Matrix = obj.matrix_world
    return [mw @ p for p in points]


def world_points_to_local(points: Iterable[Vector], obj: bpy.types.Object) -> List[Vector]:
    """
    Batch convert iterable of world-space points to the object's local space.
    Returns list of local-space points.
    """
    mwi: Matrix = obj.matrix_world.inverted()
    return [mwi @ p for p in points]


def local_vectors_to_world(vectors: Iterable[Vector], obj: bpy.types.Object) -> List[Vector]:
    """
    Batch convert iterable of local-space direction vectors to world space.
    Returns list of world-space vectors.
    """
    rot: Matrix = obj.matrix_world.to_3x3()
    return [rot @ v for v in vectors]


def world_vectors_to_local(vectors: Iterable[Vector], obj: bpy.types.Object) -> List[Vector]:
    """
    Batch convert iterable of world-space direction vectors to local space.
    Returns list of local-space vectors.
    """
    rot_i: Matrix = obj.matrix_world.inverted().to_3x3()
    return [rot_i @ v for v in vectors]


def local_points_to_other_local(points: Iterable[Vector], from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> List[Vector]:
    """
    Batch convert iterable of points from from_obj local space to to_obj local space.
    Returns list of points in to_obj local space.
    """
    rel: Matrix = matrix_local_to_local(from_obj, to_obj)
    return [rel @ p for p in points]


def local_vectors_to_other_local(vectors: Iterable[Vector], from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> List[Vector]:
    """
    Batch convert iterable of vectors from from_obj local space to to_obj local space.
    Returns list of vectors in to_obj local space.
    """
    rel3: Matrix = matrix_local_vector_to_local(from_obj, to_obj)
    return [rel3 @ v for v in vectors]


def local_matrix_to_world(local_matrix: Matrix, obj: bpy.types.Object) -> Matrix:
    """
    Convert a local-space transform matrix (4x4) to world space.
    """
    return obj.matrix_world @ local_matrix


def world_matrix_to_local(world_matrix: Matrix, obj: bpy.types.Object) -> Matrix:
    """
    Convert a world-space transform matrix (4x4) into the object's local space.
    """
    return obj.matrix_world.inverted() @ world_matrix


def object_world_axes(obj: bpy.types.Object) -> Tuple[Vector, Vector, Vector]:
    """
    Return (x_axis, y_axis, z_axis) unit vectors in world space.
    """
    rot: Matrix = obj.matrix_world.to_3x3()
    return rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0)), rot @ Vector((0, 0, 1))


def object_decomposed(obj: bpy.types.Object) -> Tuple[Vector, Euler, Vector]:
    """
    Return (location, rotation_euler, scale) copies of the object's transform.
    """
    return obj.location.copy(), obj.rotation_euler.copy(), obj.scale.copy()


def world_point_from_local_offset(obj: bpy.types.Object, local_offset: Vector) -> Vector:
    """
    Get a world-space point given an offset in local space from the object's origin.
    """
    return obj.matrix_world @ local_offset


def relative_offset_world(from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> Vector:
    """
    Vector from from_obj origin to to_obj origin in world space.
    """
    return to_obj.matrix_world.translation - from_obj.matrix_world.translation


def local_offset_between_objects(from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> Vector:
    """
    The vector from from_obj origin to to_obj origin expressed in from_obj local space.
    """
    return world_to_local_vector(relative_offset_world(from_obj, to_obj), from_obj)


def bounding_box_world_corners(obj: bpy.types.Object) -> List[Vector]:
    """
    Return list (len=8) of the object's bound_box corners in world space.
    """
    mw: Matrix = obj.matrix_world
    return [mw @ Vector(corner) for corner in obj.bound_box]


def precompute_local_space_mapping(from_obj: bpy.types.Object, to_obj: bpy.types.Object) -> Tuple[Matrix, Matrix]:
    """
    Precompute and return (point_matrix_4x4, vector_matrix_3x3) for repeated conversions.
    """
    rel: Matrix = matrix_local_to_local(from_obj, to_obj)
    return rel, rel.to_3x3()


def get_world_location_from_matrix(matrix: Matrix) -> Vector:
    """
    Extract the translation component from a 4x4 matrix as a Vector.
    """
    return matrix.to_translation()


def get_world_rotation_from_matrix(matrix: Matrix) -> Euler:
    """
    Extract the rotation component from a 4x4 matrix as an Euler (in radians).
    """
    return matrix.to_euler()


def get_world_location(obj: bpy.types.Object) -> Vector:
    """
    Get the object's world location as a Vector.
    """
    return obj.matrix_world.to_translation()


def get_world_rotation(obj: bpy.types.Object) -> Euler:
    """
    Get the object's world rotation as an Euler (in radians).
    """
    return obj.matrix_world.to_euler()


def get_world_scale(obj: bpy.types.Object) -> Vector:
    """
    Get the object's world scale as a Vector.
    """
    return obj.matrix_world.to_scale()


def set_world_location(obj: bpy.types.Object, world_pos: Vector):
    """
    Set the object's world location to the specified world_pos Vector.
    """
    obj.matrix_world.translation = world_pos


def set_world_rotation(obj: bpy.types.Object, world_rot: Euler):
    """
    Set the object's world rotation to the specified world_rot Euler (in radians).
    """
    loc = obj.matrix_world.to_translation()
    scale = obj.matrix_world.to_scale()
    rot_matrix = world_rot.to_matrix().to_4x4()
    scale_matrix = Matrix.Diagonal(scale).to_4x4()
    obj.matrix_world = Matrix.Translation(loc) @ rot_matrix @ scale_matrix


def set_world_scale(obj: bpy.types.Object, world_scale: Vector):
    """
    Set the object's world scale to the specified world_scale Vector.
    """
    loc = obj.matrix_world.to_translation()
    rot = obj.matrix_world.to_euler()
    rot_matrix = rot.to_matrix().to_4x4()
    scale_matrix = Matrix.Diagonal(world_scale).to_4x4()
    obj.matrix_world = Matrix.Translation(loc) @ rot_matrix @ scale_matrix

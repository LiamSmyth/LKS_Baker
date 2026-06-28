import bpy
from enum import Enum, auto
from mathutils import Vector, Matrix

# The screen directions for view-aligned operation


class ScreenDirection(Enum):
    """
    Enum for screen directions.
    """
    RIGHT = auto()
    DOWN = auto()
    LEFT = auto()
    UP = auto()


# Map screen directions to view-space unit vectors (keys are names — reload-safe).
SCREEN_DIRECTION_TO_VECTOR = {
    'RIGHT': Vector((1.0, 0.0, 0.0)),
    'DOWN': Vector((0.0, -1.0, 0.0)),
    'LEFT': Vector((-1.0, 0.0, 0.0)),
    'UP': Vector((0.0, 1.0, 0.0)),
}


def screen_direction_key(direction: ScreenDirection | str) -> str:
    """Normalize ScreenDirection enum / RNA string to RIGHT, LEFT, UP, DOWN."""
    if isinstance(direction, str):
        return direction.split(".")[-1].upper()
    name = getattr(direction, "name", None)
    if name:
        return str(name).upper()
    return str(direction).split(".")[-1].upper()


def coerce_screen_direction(direction: ScreenDirection | str) -> ScreenDirection:
    """Return the current-module ScreenDirection member (reload-safe)."""
    return ScreenDirection[screen_direction_key(direction)]


def get_screen_direction_vector_from_direction(direction: ScreenDirection | str) -> Vector:
    """
    Return the Vector corresponding to the given screen direction.
    """
    return SCREEN_DIRECTION_TO_VECTOR.get(
        screen_direction_key(direction), Vector((0.0, 0.0, 0.0)))


def get_current_region_3d(context: bpy.types.Context):
    """Return Region3D for the invoking viewport.

    Resolution order:
        1. context.region_data when region is WINDOW (active 3D viewport)
        2. VIEW_3D space.region_3d
        3. context.area VIEW_3D space.region_3d
        4. first VIEW_3D on screen (legacy fallback)
    """
    from .symmetry_mod_helpers import symmetry_axis_debug as sad

    region = getattr(context, "region", None)
    if region is not None and region.type == 'WINDOW':
        rv3d = getattr(context, "region_data", None)
        if rv3d is not None:
            sad.log_rv3d_source("context.region_data (WINDOW)", rv3d)
            return rv3d

    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == 'VIEW_3D':
        rv3d = getattr(space, "region_3d", None)
        if rv3d is not None:
            sad.log_rv3d_source("space.region_3d", rv3d)
            return rv3d

    area = getattr(context, "area", None)
    if area is not None and area.type == 'VIEW_3D':
        rv3d = area.spaces.active.region_3d
        if rv3d is not None:
            sad.log_rv3d_source("area.spaces.active.region_3d", rv3d)
            return rv3d

    screen = getattr(context, "screen", None)
    if screen is not None:
        for screen_area in screen.areas:
            if screen_area.type == 'VIEW_3D':
                rv3d = screen_area.spaces.active.region_3d
                if rv3d is not None:
                    sad.log_rv3d_source("screen.areas[VIEW_3D].region_3d", rv3d)
                    return rv3d

    rv3d = getattr(context, "region_data", None)
    if rv3d is not None:
        sad.log_rv3d_source("context.region_data (fallback)", rv3d)
        return rv3d

    sad.log("get_current_region_3d -> None")
    return None


def get_current_view_matrix(context: bpy.types.Context) -> Matrix:
    """
    Return the view matrix for the active 3D viewport when available.
    Falls back to the first VIEW_3D area, then identity.
    """
    rv3d = get_current_region_3d(context)
    if rv3d is not None:
        return rv3d.view_matrix.copy()

    return Matrix.Identity(4)


def get_current_camera_vector(context: bpy.types.Context) -> Vector:
    """
    Return the view (look) direction as a normalized Vector (world space).
    """
    view_matrix: Matrix = get_current_view_matrix(context)
    zcol: Vector = view_matrix.col[2].to_3d()
    view_direction: Vector = (-zcol).normalized()
    return view_direction


def get_current_camera_location(context: bpy.types.Context) -> Vector:
    """
    Return the camera/view location as a Vector (world space).
    """
    view_matrix: Matrix = get_current_view_matrix(context)
    loc: Vector = view_matrix.inverted().translation
    return loc


def get_current_camera_up_vector(context: bpy.types.Context) -> Vector:
    """
    Return the up direction (camera Y) as a normalized Vector (world space).
    """
    view_matrix: Matrix = get_current_view_matrix(context)
    ycol: Vector = view_matrix.col[1].to_3d()
    return ycol.normalized()


def get_screen_aligned_vector(context: bpy.types.Context, direction: ScreenDirection) -> Vector:
    """
    Return a world-space Vector corresponding to the view-aligned screen direction
    (RIGHT, LEFT, UP, DOWN).

    Uses view_rotation from the invoking viewport (legacy
    world_vector_from_screen_direction behavior).
    """
    from .symmetry_mod_helpers import symmetry_axis_debug as sad

    screen_vec: Vector = get_screen_direction_vector_from_direction(direction)
    sad.log_section(f"get_screen_aligned_vector direction={screen_direction_key(direction)}")
    sad.log_vector("screen_vec (view-space)", screen_vec)
    rv3d = get_current_region_3d(context)
    if rv3d is None:
        sad.log("rv3d is None -> returning zero vector")
        return Vector((0.0, 0.0, 0.0))
    world_vec = (rv3d.view_rotation @ screen_vec).normalized()
    sad.log_vector("world_vec (view_rotation @ screen_vec)", world_vec)
    return world_vec


def get_screen_direction_to_view_plane_normal(context: bpy.types.Context, direction: ScreenDirection) -> Vector:
    """
    Returns the normal vector of the view plane corresponding to the given screen direction.
    """
    return get_screen_aligned_vector(context, direction)

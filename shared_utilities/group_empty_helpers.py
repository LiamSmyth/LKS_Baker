"""World-space bounds and placement helpers for grouping objects under an empty."""

from __future__ import annotations

import statistics
from typing import Iterable, Sequence

import bpy
from mathutils import Vector

_GEOMETRY_TYPES = frozenset({
    'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'VOLUME', 'GPENCIL',
})

_TO_MESH_TYPES = frozenset({'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'})

PIVOT_GEOMETRY_MEDIAN = 'GEOMETRY_MEDIAN'
PIVOT_PIVOT_MEDIAN = 'PIVOT_MEDIAN'
PIVOT_WORLD_ORIGIN = 'WORLD_ORIGIN'
PIVOT_CURSOR = 'CURSOR'

PIVOT_MODE_ITEMS = (
    (PIVOT_GEOMETRY_MEDIAN, 'Geometry Median', 'Center of combined evaluated geometry bounds'),
    (PIVOT_PIVOT_MEDIAN, 'Pivot Median', 'Median of object world pivots'),
    (PIVOT_WORLD_ORIGIN, 'World Origin', 'World (0, 0, 0)'),
    (PIVOT_CURSOR, 'Cursor', '3D cursor location'),
)

JUSTIFY_NONE = 'NONE'
JUSTIFY_OBJECT_BBOX_MAX = 'OBJECT_BBOX_MAX'
JUSTIFY_OBJECT_BBOX_MIN = 'OBJECT_BBOX_MIN'
JUSTIFY_WORLD_BBOX_MAX = 'WORLD_BBOX_MAX'
JUSTIFY_WORLD_BBOX_MIN = 'WORLD_BBOX_MIN'

JUSTIFY_MODE_ITEMS = (
    (JUSTIFY_NONE, 'None', ''),
    (JUSTIFY_OBJECT_BBOX_MAX, 'Object BBox Max', ''),
    (JUSTIFY_OBJECT_BBOX_MIN, 'Object BBox Min', ''),
    (JUSTIFY_WORLD_BBOX_MAX, 'World BBox Max', ''),
    (JUSTIFY_WORLD_BBOX_MIN, 'World BBox Min', ''),
)


def _iter_geometry_objects(objects: Iterable[bpy.types.Object]) -> list[bpy.types.Object]:
    return [obj for obj in objects if obj.type in _GEOMETRY_TYPES]


def _accumulate_bounds(
    min_v: Vector | None,
    max_v: Vector | None,
    point: Vector,
) -> tuple[Vector, Vector]:
    if min_v is None or max_v is None:
        return point.copy(), point.copy()
    for axis in range(3):
        if point[axis] < min_v[axis]:
            min_v[axis] = point[axis]
        if point[axis] > max_v[axis]:
            max_v[axis] = point[axis]
    return min_v, max_v


def _bounds_from_bound_box(obj: bpy.types.Object) -> tuple[Vector | None, Vector | None]:
    """Fallback bounds from object bound_box corners transformed to world space."""
    min_v: Vector | None = None
    max_v: Vector | None = None
    mw = obj.matrix_world
    for corner in obj.bound_box:
        min_v, max_v = _accumulate_bounds(min_v, max_v, mw @ Vector(corner))
    return min_v, max_v


def _bounds_from_mesh_vertices(
    mesh: bpy.types.Mesh,
    matrix_world: bpy.types.Matrix,
) -> tuple[Vector | None, Vector | None]:
    min_v: Vector | None = None
    max_v: Vector | None = None
    for vertex in mesh.vertices:
        min_v, max_v = _accumulate_bounds(min_v, max_v, matrix_world @ vertex.co)
    return min_v, max_v


def _object_world_bounds(
    obj: bpy.types.Object,
    *,
    depsgraph: bpy.types.Depsgraph | None,
    evaluated: bool,
) -> tuple[Vector | None, Vector | None]:
    """World-space axis-aligned bounds from mesh vertices (preferred) or bound_box."""
    source = obj.evaluated_get(depsgraph) if evaluated and depsgraph is not None else obj
    temp_mesh: bpy.types.Mesh | None = None
    try:
        if source.type == 'MESH' and source.data is not None:
            if evaluated and depsgraph is not None and source is not obj:
                temp_mesh = source.to_mesh()
                return _bounds_from_mesh_vertices(temp_mesh, source.matrix_world)
            return _bounds_from_mesh_vertices(source.data, source.matrix_world)

        if evaluated and depsgraph is not None and source.type in _TO_MESH_TYPES:
            temp_mesh = source.to_mesh()
            if temp_mesh is not None:
                return _bounds_from_mesh_vertices(temp_mesh, source.matrix_world)
    finally:
        if temp_mesh is not None:
            source.to_mesh_clear()

    return _bounds_from_bound_box(source)


def _combined_geometry_bounds(
    objects: Sequence[bpy.types.Object],
    *,
    depsgraph: bpy.types.Depsgraph | None,
    evaluated: bool,
) -> tuple[Vector | None, Vector | None]:
    """Union of per-object world bounds.

    Object BBox (evaluated=False): original mesh vertices, no modifier eval.
    World BBox (evaluated=True): depsgraph-evaluated geometry vertices.
    """
    min_v: Vector | None = None
    max_v: Vector | None = None
    for obj in _iter_geometry_objects(objects):
        obj_min, obj_max = _object_world_bounds(obj, depsgraph=depsgraph, evaluated=evaluated)
        if obj_min is None or obj_max is None:
            continue
        if min_v is None or max_v is None:
            min_v, max_v = obj_min.copy(), obj_max.copy()
            continue
        for axis in range(3):
            min_v[axis] = min(min_v[axis], obj_min[axis])
            max_v[axis] = max(max_v[axis], obj_max[axis])
    return min_v, max_v


def _bbox_corners_from_min_max(
    min_v: Vector | None,
    max_v: Vector | None,
) -> list[Vector]:
    if min_v is None or max_v is None:
        return []
    return [
        Vector((min_v.x, min_v.y, min_v.z)),
        Vector((max_v.x, min_v.y, min_v.z)),
        Vector((min_v.x, max_v.y, min_v.z)),
        Vector((max_v.x, max_v.y, min_v.z)),
        Vector((min_v.x, min_v.y, max_v.z)),
        Vector((max_v.x, min_v.y, max_v.z)),
        Vector((min_v.x, max_v.y, max_v.z)),
        Vector((max_v.x, max_v.y, max_v.z)),
    ]


def bbox_min_max(corners: Sequence[Vector]) -> tuple[Vector | None, Vector | None]:
    """Axis-aligned min/max from world-space corner points."""
    if not corners:
        return None, None
    min_v = Vector((
        min(c.x for c in corners),
        min(c.y for c in corners),
        min(c.z for c in corners),
    ))
    max_v = Vector((
        max(c.x for c in corners),
        max(c.y for c in corners),
        max(c.z for c in corners),
    ))
    return min_v, max_v


def combined_world_bbox_corners(
    objects: Sequence[bpy.types.Object],
    depsgraph: bpy.types.Depsgraph,
) -> list[Vector]:
    """World AABB corners from depsgraph-evaluated geometry vertices."""
    min_v, max_v = _combined_geometry_bounds(objects, depsgraph=depsgraph, evaluated=True)
    return _bbox_corners_from_min_max(min_v, max_v)


def object_bbox_corners_world(objects: Sequence[bpy.types.Object]) -> list[Vector]:
    """World AABB corners from original mesh vertices (no modifier eval)."""
    min_v, max_v = _combined_geometry_bounds(objects, depsgraph=None, evaluated=False)
    return _bbox_corners_from_min_max(min_v, max_v)


def geometry_median_world(
    objects: Sequence[bpy.types.Object],
    depsgraph: bpy.types.Depsgraph,
) -> Vector:
    """Center of the combined evaluated-geometry world bbox."""
    min_v, max_v = _combined_geometry_bounds(objects, depsgraph=depsgraph, evaluated=True)
    if min_v is None or max_v is None:
        return pivot_median_world(objects)
    return (min_v + max_v) / 2


def pivot_median_world(objects: Sequence[bpy.types.Object]) -> Vector:
    """Per-axis median of selected object world pivots (matrix_world.translation)."""
    if not objects:
        return Vector((0.0, 0.0, 0.0))
    translations = [obj.matrix_world.translation for obj in objects]
    return Vector((
        statistics.median([t.x for t in translations]),
        statistics.median([t.y for t in translations]),
        statistics.median([t.z for t in translations]),
    ))


def _justify_axis_value(mode: str, axis: int, object_min: Vector, object_max: Vector,
                        world_min: Vector, world_max: Vector) -> float | None:
    if mode == JUSTIFY_NONE:
        return None
    if mode == JUSTIFY_OBJECT_BBOX_MIN:
        return object_min[axis]
    if mode == JUSTIFY_OBJECT_BBOX_MAX:
        return object_max[axis]
    if mode == JUSTIFY_WORLD_BBOX_MIN:
        return world_min[axis]
    if mode == JUSTIFY_WORLD_BBOX_MAX:
        return world_max[axis]
    return None


def apply_justify(
    position: Vector,
    objects: Sequence[bpy.types.Object],
    justify_x: str,
    justify_y: str,
    justify_z: str,
    depsgraph: bpy.types.Depsgraph,
) -> Vector:
    """Override position axes using combined selection bbox min/max after pivot placement."""
    result = position.copy()
    object_min, object_max = _combined_geometry_bounds(objects, depsgraph=None, evaluated=False)
    world_min, world_max = _combined_geometry_bounds(objects, depsgraph=depsgraph, evaluated=True)

    if object_min is None or object_max is None or world_min is None or world_max is None:
        return result

    for axis, mode in enumerate((justify_x, justify_y, justify_z)):
        value = _justify_axis_value(mode, axis, object_min, object_max, world_min, world_max)
        if value is not None:
            result[axis] = value
    return result


def empty_display_size_from_corners(corners: Sequence[Vector]) -> float:
    """Half of the largest combined bbox axis span, minimum 1.0."""
    min_v, max_v = bbox_min_max(corners)
    if min_v is None or max_v is None:
        return 1.0
    size = max_v - min_v
    return max(max(size.x, size.y, size.z) / 2, 1.0)


def _view_layer_visible_collections(
    layer_coll: bpy.types.LayerCollection,
) -> set[bpy.types.Collection]:
    """Collections whose objects are reachable in the active view layer."""
    visible: set[bpy.types.Collection] = set()

    def walk(lc: bpy.types.LayerCollection, parent_excluded: bool) -> None:
        excluded = parent_excluded or lc.exclude
        if not excluded:
            visible.add(lc.collection)
        for child in lc.children:
            walk(child, excluded)

    walk(layer_coll, False)
    return visible


def _collection_for_view_layer_object(
    obj: bpy.types.Object,
    context: bpy.types.Context,
) -> bpy.types.Collection:
    """Pick a collection that places *obj* in the active view layer."""
    visible = _view_layer_visible_collections(context.view_layer.layer_collection)
    for coll in obj.users_collection:
        if coll in visible:
            return coll
    return context.collection


def link_empty_to_anchor_collection(
    empty: bpy.types.Object,
    anchor: bpy.types.Object,
    context: bpy.types.Context,
) -> None:
    """Link empty to a collection that places it in the active view layer."""
    target = _collection_for_view_layer_object(anchor, context)
    target.objects.link(empty)


def suggest_group_empty_name(objects: Sequence[bpy.types.Object], active: bpy.types.Object | None) -> str:
    """Name for a group empty based on the active or sole selection."""
    anchor = active if active in objects else (objects[0] if objects else None)
    if anchor is None:
        return 'Empty'
    if len(objects) == 1:
        return anchor.name
    return f'{anchor.name}_grp'

"""Helpers for converting smooth-cusp angles, sharps, bevel, and crease weights."""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np

from .geonodes_modifier_helpers import get_nodes_modifier_input, resolve_modifier_input_identifier
from .shading_helpers import find_smooth_by_angle_modifier

DEFAULT_CUSP_ANGLE_RAD = math.radians(30.0)
_BEVEL_WEIGHT_ATTR = 'bevel_weight_edge'
_CREASE_ATTR = 'crease_edge'


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


def get_smooth_cusp_angle_radians(
    obj: bpy.types.Object,
    context: bpy.types.Context,
) -> float:
    """Read cusp angle from scene, object's Smooth by Angle modifier, else 30 degrees."""
    scn = context.scene
    if hasattr(scn, 'lks_bevel_cusp_angle'):
        return float(scn.lks_bevel_cusp_angle)

    mod = find_smooth_by_angle_modifier(obj)
    if mod is None:
        return DEFAULT_CUSP_ANGLE_RAD

    key = _smooth_by_angle_input_key(mod)
    if key is None:
        return DEFAULT_CUSP_ANGLE_RAD

    value = get_nodes_modifier_input(mod, key)
    if value is None:
        return DEFAULT_CUSP_ANGLE_RAD

    return float(value)


def autosmooth_to_bevel_weights(
    obj: bpy.types.Object,
    context: bpy.types.Context,
    *,
    weight: float = 1.0,
    selection_only: bool,
) -> int:
    """Mark sharps from autosmooth cusp angle, then set bevel weight on those edges."""
    angle_rad = get_smooth_cusp_angle_radians(obj, context)
    mark_sharps_from_angle(obj, context, angle_rad, selection_only)
    return set_bevel_weight_on_sharps(obj, context, weight, selection_only)


def selection_only_for_object(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> bool:
    """True when obj is the active mesh in edit mode."""
    return (
        context.mode == 'EDIT_MESH'
        and context.view_layer.objects.active is obj
    )


def _edge_in_selection(edge: bmesh.types.BMEdge, selection_only: bool) -> bool:
    if not selection_only:
        return True
    if edge.select:
        return True
    for vert in edge.verts:
        if vert.select:
            return True
    for face in edge.link_faces:
        if face.select:
            return True
    return False


def _ensure_edge_float_attr(mesh: bpy.types.Mesh, attr_name: str) -> None:
    if attr_name not in mesh.attributes:
        mesh.attributes.new(name=attr_name, type='FLOAT', domain='EDGE')


def has_sharp_edges(
    obj: bpy.types.Object,
    context: bpy.types.Context,
    selection_only: bool,
) -> bool:
    """Return True when any in-scope edge is marked sharp."""
    mesh = obj.data
    num_edges = len(mesh.edges)
    if num_edges == 0:
        return False

    sharp = np.empty(num_edges, dtype=np.bool_)
    mesh.edges.foreach_get("use_edge_sharp", sharp)

    if not selection_only:
        return bool(sharp.any())

    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(mesh)
        for edge in bm.edges:
            if not _edge_in_selection(edge, True):
                continue
            if not edge.smooth:
                return True
        return False

    selected = np.empty(num_edges, dtype=np.bool_)
    mesh.edges.foreach_get("select", selected)
    return bool((sharp & selected).any())


def mark_sharps_from_angle(
    obj: bpy.types.Object,
    context: bpy.types.Context,
    angle_rad: float,
    selection_only: bool,
) -> int:
    """Mark edges sharp where the dihedral angle exceeds angle_rad."""
    del context
    mesh = obj.data
    in_edit = obj.mode == 'EDIT'

    if in_edit:
        bm = bmesh.from_edit_mesh(mesh)
    else:
        bm = bmesh.new()
        bm.from_mesh(mesh)

    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    edges_to_sharp: list[bmesh.types.BMEdge] = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        if not _edge_in_selection(edge, selection_only):
            continue
        try:
            ang = edge.calc_face_angle()
        except ValueError:
            continue
        if ang is not None and ang > angle_rad:
            edges_to_sharp.append(edge)

    if edges_to_sharp:
        for edge in edges_to_sharp:
            edge.smooth = False

    if in_edit:
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    else:
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

    return len(edges_to_sharp)


def set_bevel_weight_on_sharps(
    obj: bpy.types.Object,
    context: bpy.types.Context,
    weight: float,
    selection_only: bool,
) -> int:
    """Set bevel weight on sharp edges in scope."""
    del context
    mesh = obj.data
    num_edges = len(mesh.edges)
    if num_edges == 0:
        return 0

    sharp = np.empty(num_edges, dtype=np.bool_)
    mesh.edges.foreach_get("use_edge_sharp", sharp)

    if selection_only and obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(mesh)
        mask = np.zeros(num_edges, dtype=np.bool_)
        for edge in bm.edges:
            if not edge.smooth and _edge_in_selection(edge, True):
                mask[edge.index] = True
        target = mask
    elif selection_only:
        selected = np.empty(num_edges, dtype=np.bool_)
        mesh.edges.foreach_get("select", selected)
        target = sharp & selected
    else:
        target = sharp

    if not target.any():
        return 0

    _ensure_edge_float_attr(mesh, _BEVEL_WEIGHT_ATTR)
    values = np.empty(num_edges, dtype=np.float32)
    mesh.attributes[_BEVEL_WEIGHT_ATTR].data.foreach_get("value", values)
    values[target] = weight
    mesh.attributes[_BEVEL_WEIGHT_ATTR].data.foreach_set("value", values)
    mesh.update()
    return int(target.sum())


def set_crease_on_sharps(
    obj: bpy.types.Object,
    context: bpy.types.Context,
    crease: float,
    selection_only: bool,
) -> int:
    """Set crease weight on sharp edges in scope."""
    del context
    mesh = obj.data
    num_edges = len(mesh.edges)
    if num_edges == 0:
        return 0

    sharp = np.empty(num_edges, dtype=np.bool_)
    mesh.edges.foreach_get("use_edge_sharp", sharp)

    if selection_only and obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(mesh)
        mask = np.zeros(num_edges, dtype=np.bool_)
        for edge in bm.edges:
            if not edge.smooth and _edge_in_selection(edge, True):
                mask[edge.index] = True
        target = mask
    elif selection_only:
        selected = np.empty(num_edges, dtype=np.bool_)
        mesh.edges.foreach_get("select", selected)
        target = sharp & selected
    else:
        target = sharp

    if not target.any():
        return 0

    _ensure_edge_float_attr(mesh, _CREASE_ATTR)
    values = np.empty(num_edges, dtype=np.float32)
    mesh.attributes[_CREASE_ATTR].data.foreach_get("value", values)
    values[target] = crease
    mesh.attributes[_CREASE_ATTR].data.foreach_set("value", values)
    mesh.update()
    return int(target.sum())


def clear_sharp_edges(
    obj: bpy.types.Object,
    context: bpy.types.Context,
    selection_only: bool,
) -> int:
    """Clear the sharp flag on edges in scope."""
    del context
    mesh = obj.data
    in_edit = obj.mode == 'EDIT'

    if in_edit:
        bm = bmesh.from_edit_mesh(mesh)
        edges_to_clear: list[bmesh.types.BMEdge] = []
        for edge in bm.edges:
            if edge.smooth:
                continue
            if not _edge_in_selection(edge, selection_only):
                continue
            edges_to_clear.append(edge)
        if edges_to_clear:
            for edge in edges_to_clear:
                edge.smooth = True
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        return len(edges_to_clear)

    num_edges = len(mesh.edges)
    if num_edges == 0:
        return 0

    sharp = np.empty(num_edges, dtype=np.bool_)
    mesh.edges.foreach_get("use_edge_sharp", sharp)

    if selection_only:
        selected = np.empty(num_edges, dtype=np.bool_)
        mesh.edges.foreach_get("select", selected)
        target = sharp & selected
    else:
        target = sharp

    if not target.any():
        return 0

    sharp[target] = False
    mesh.edges.foreach_set("use_edge_sharp", sharp)
    mesh.update()
    return int(target.sum())

"""Sync seam/sharp edge marks and mark UV island boundaries as seams."""

from __future__ import annotations

from collections.abc import Callable

import bmesh
import bpy

from .selection_preserve_helpers import SelectionSnapshot, capture_selection_state, restore_selection_by_name_map
from .smart_edge_toggle_helpers import (
    ResolvedTargetEdges,
    capture_element_selection,
    edges_at_indices,
    resolve_target_edges,
    restore_element_selection,
)

_UV_EPS = 1e-6


def get_uv_island_boundary_edges(
    bm: bmesh.types.BMesh,
    uv_layer: bmesh.types.BMLayerItem,
) -> set[bmesh.types.BMEdge]:
    """Edges at UV island boundaries (UV discontinuity or mesh boundary)."""
    boundary_edges: set[bmesh.types.BMEdge] = set()

    for edge in bm.edges:
        if len(edge.link_faces) < 2:
            boundary_edges.add(edge)
            continue

        uv_pairs: dict[bmesh.types.BMVert, list[tuple[float, float]]] = {}
        for face in edge.link_faces:
            for loop in face.loops:
                if loop.vert not in edge.verts:
                    continue
                vert = loop.vert
                uv = loop[uv_layer].uv
                uv_pairs.setdefault(vert, []).append((uv.x, uv.y))

        is_boundary = False
        for uvs in uv_pairs.values():
            if len(uvs) < 2:
                continue
            first_u, first_v = uvs[0]
            for other_u, other_v in uvs[1:]:
                if abs(first_u - other_u) > _UV_EPS or abs(first_v - other_v) > _UV_EPS:
                    is_boundary = True
                    break
            if is_boundary:
                break

        if is_boundary:
            boundary_edges.add(edge)

    return boundary_edges


def _scope_faces(
    bm: bmesh.types.BMesh,
    resolved: ResolvedTargetEdges,
    element_snap,
) -> set[bmesh.types.BMFace]:
    has_selection = bool(
        element_snap.vert_indices
        or element_snap.edge_indices
        or element_snap.face_indices
    )
    if not has_selection:
        return set(bm.faces)
    if resolved.face_boundary:
        return {face for face in bm.faces if face.select}

    faces: set[bmesh.types.BMFace] = set()
    bm.edges.ensure_lookup_table()
    for edge_index in resolved.edge_indices:
        if 0 <= edge_index < len(bm.edges):
            faces.update(bm.edges[edge_index].link_faces)
    return faces


def _uv_boundary_edges_in_scope(
    bm: bmesh.types.BMesh,
    uv_layer: bmesh.types.BMLayerItem,
    scope_faces: set[bmesh.types.BMFace],
) -> set[bmesh.types.BMEdge]:
    if not scope_faces:
        return set()

    uv_boundaries = get_uv_island_boundary_edges(bm, uv_layer)
    return {
        edge
        for edge in uv_boundaries
        if any(face in scope_faces for face in edge.link_faces)
    }


def _run_edit_mesh_op(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    apply_fn: Callable[..., int],
    *args,
    **kwargs,
) -> int:
    if obj.type != "MESH":
        return 0

    mesh = obj.data
    if not mesh.edges:
        return 0

    in_edit = context.mode == "EDIT_MESH" and context.view_layer.objects.active is obj
    object_snap: SelectionSnapshot | None = None
    if not in_edit:
        object_snap = capture_selection_state(context)

    if not in_edit:
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")

    try:
        bm = bmesh.from_edit_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        element_snap = capture_element_selection(context, bm)
        resolved = resolve_target_edges(bm, element_snap.mesh_select_mode)
        count = apply_fn(bm, mesh, element_snap, resolved, *args, **kwargs)
        restore_element_selection(context, bm, mesh, element_snap)
        return count
    finally:
        if not in_edit:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
            if object_snap is not None:
                restore_selection_by_name_map(context, object_snap, {})


def _sync_sharps_to_seams_on_edges(
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    target_edge_indices: set[int],
) -> int:
    if not target_edge_indices:
        return 0

    for edge in edges_at_indices(bm, target_edge_indices):
        edge.smooth = not edge.seam

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    return len(target_edge_indices)


def _mark_uv_boundaries_as_seams(
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    element_snap,
    resolved: ResolvedTargetEdges,
    *,
    and_sharps: bool,
) -> int:
    if not mesh.uv_layers:
        mesh.uv_layers.new()

    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        uv_layer = bm.loops.layers.uv.verify()

    scope_faces = _scope_faces(bm, resolved, element_snap)
    target_edges = _uv_boundary_edges_in_scope(bm, uv_layer, scope_faces)
    if not target_edges:
        return 0

    for edge in target_edges:
        edge.seam = True
        if and_sharps:
            edge.smooth = False

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    return len(target_edges)


def seams_to_sharps(context: bpy.types.Context, obj: bpy.types.Object) -> int:
    """Set sharp state to match seam state on resolved target edges."""

    def apply(bm, mesh, _element_snap, resolved, **_kwargs) -> int:
        return _sync_sharps_to_seams_on_edges(bm, mesh, resolved.edge_indices)

    return _run_edit_mesh_op(context, obj, apply)


def uv_boundaries_to_seams(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    and_sharps: bool = False,
) -> int:
    """Mark UV island boundary edges as seams within resolved scope."""

    def apply(bm, mesh, element_snap, resolved, **_kwargs) -> int:
        return _mark_uv_boundaries_as_seams(
            bm,
            mesh,
            element_snap,
            resolved,
            and_sharps=and_sharps,
        )

    return _run_edit_mesh_op(context, obj, apply, and_sharps=and_sharps)

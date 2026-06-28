"""Smart edge toggle: resolve selection, toggle bevel/crease/seam/sharp, restore state."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import bmesh
import bpy

from .lks_constants import ATTR_CREASE_EDGE
from .selection_preserve_helpers import SelectionSnapshot, capture_selection_state, restore_selection_by_name_map

_BEVEL_WEIGHT_ATTR = "bevel_weight_edge"
_ON_FLOAT = 1.0
_OFF_FLOAT = 0.0

_KIND_BEVEL_WEIGHT = "bevel_weight"
_KIND_CREASE = "crease"
_KIND_SEAM = "seam"
_KIND_SHARP = "sharp"


class EdgeToggleKind(Enum):
    BEVEL_WEIGHT = _KIND_BEVEL_WEIGHT
    CREASE = _KIND_CREASE
    SEAM = _KIND_SEAM
    SHARP = _KIND_SHARP


def edge_toggle_kind_value(kind: EdgeToggleKind | str) -> str:
    """Normalize kind to its string value (safe across module reload)."""
    if isinstance(kind, str):
        return kind
    return kind.value


@dataclass(frozen=True, slots=True)
class EditElementSnapshot:
    mesh_select_mode: tuple[bool, bool, bool]
    vert_indices: tuple[int, ...]
    edge_indices: tuple[int, ...]
    face_indices: tuple[int, ...]
    active_vert: int
    active_edge: int
    active_face: int


def _capture_element_selection(
    context: bpy.types.Context,
    bm: bmesh.types.BMesh,
) -> EditElementSnapshot:
    ts = context.tool_settings
    select_mode = tuple(ts.mesh_select_mode) if ts else (False, True, False)

    active_vert = active_edge = active_face = -1
    active = bm.select_history.active
    if isinstance(active, bmesh.types.BMVert):
        active_vert = active.index
    elif isinstance(active, bmesh.types.BMEdge):
        active_edge = active.index
    elif isinstance(active, bmesh.types.BMFace):
        active_face = active.index

    return EditElementSnapshot(
        mesh_select_mode=select_mode,
        vert_indices=tuple(v.index for v in bm.verts if v.select),
        edge_indices=tuple(e.index for e in bm.edges if e.select),
        face_indices=tuple(f.index for f in bm.faces if f.select),
        active_vert=active_vert,
        active_edge=active_edge,
        active_face=active_face,
    )


def _restore_element_selection(
    context: bpy.types.Context,
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    snap: EditElementSnapshot,
) -> None:
    for vert in bm.verts:
        vert.select = False
    for edge in bm.edges:
        edge.select = False
    for face in bm.faces:
        face.select = False

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    for index in snap.vert_indices:
        if 0 <= index < len(bm.verts):
            bm.verts[index].select = True
    for index in snap.edge_indices:
        if 0 <= index < len(bm.edges):
            bm.edges[index].select = True
    for index in snap.face_indices:
        if 0 <= index < len(bm.faces):
            bm.faces[index].select = True

    bm.select_history.clear()
    active_elem = None
    if snap.active_vert >= 0 and snap.active_vert < len(bm.verts):
        active_elem = bm.verts[snap.active_vert]
    elif snap.active_edge >= 0 and snap.active_edge < len(bm.edges):
        active_elem = bm.edges[snap.active_edge]
    elif snap.active_face >= 0 and snap.active_face < len(bm.faces):
        active_elem = bm.faces[snap.active_face]

    if active_elem is not None:
        # Last item in select_history is active (read-only .active property).
        bm.select_history.add(active_elem)

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    ts = context.tool_settings
    if ts is not None:
        ts.mesh_select_mode = snap.mesh_select_mode


def _face_boundary_edge_indices(bm: bmesh.types.BMesh) -> set[int]:
    boundary: set[int] = set()
    for edge in bm.edges:
        selected_faces = [face for face in edge.link_faces if face.select]
        if len(selected_faces) == 1:
            boundary.add(edge.index)
    return boundary


def _face_internal_edge_indices(bm: bmesh.types.BMesh) -> set[int]:
    internal: set[int] = set()
    for edge in bm.edges:
        selected_faces = [face for face in edge.link_faces if face.select]
        if len(selected_faces) == 2:
            internal.add(edge.index)
    return internal


def _verts_in_selection_order(bm: bmesh.types.BMesh) -> list[bmesh.types.BMVert]:
    verts: list[bmesh.types.BMVert] = []
    seen: set[int] = set()
    for elem in bm.select_history:
        if isinstance(elem, bmesh.types.BMVert) and elem.select and elem.index not in seen:
            verts.append(elem)
            seen.add(elem.index)
    if verts:
        return verts
    return [vert for vert in bm.verts if vert.select]


def _shortest_path_edges(
    bm: bmesh.types.BMesh,
    start: bmesh.types.BMVert,
    goal: bmesh.types.BMVert,
) -> list[bmesh.types.BMEdge]:
    if start == goal:
        return []

    dist: dict[bmesh.types.BMVert, float] = {vert: float("inf") for vert in bm.verts}
    prev: dict[bmesh.types.BMVert, tuple[bmesh.types.BMVert, bmesh.types.BMEdge]] = {}
    dist[start] = 0.0
    heap: list[tuple[float, int, bmesh.types.BMVert]] = [(0.0, start.index, start)]

    while heap:
        cost, _, vertex = heapq.heappop(heap)
        if vertex == goal:
            break
        if cost > dist[vertex]:
            continue
        for edge in vertex.link_edges:
            other = edge.other_vert(vertex)
            next_cost = cost + edge.calc_length()
            if next_cost < dist[other]:
                dist[other] = next_cost
                prev[other] = (vertex, edge)
                heapq.heappush(heap, (next_cost, other.index, other))

    if goal not in prev:
        return []

    path: list[bmesh.types.BMEdge] = []
    current = goal
    while current != start and current in prev:
        _, path_edge = prev[current]
        path.append(path_edge)
        current = path_edge.other_vert(current)
    path.reverse()
    return path


def _verts_to_path_edges(
    bm: bmesh.types.BMesh,
    verts: Iterable[bmesh.types.BMVert],
) -> set[bmesh.types.BMEdge]:
    ordered = list(verts)
    if not ordered:
        return set()
    if len(ordered) == 1:
        return set(ordered[0].link_edges)

    edges: set[bmesh.types.BMEdge] = set()
    for index in range(len(ordered) - 1):
        edges.update(_shortest_path_edges(bm, ordered[index], ordered[index + 1]))
    return edges


@dataclass(frozen=True, slots=True)
class ResolvedTargetEdges:
    edge_indices: set[int]
    face_boundary: bool


def _all_edge_indices(bm: bmesh.types.BMesh) -> set[int]:
    return {edge.index for edge in bm.edges}


def _edge_indices_from_edges(edges: Iterable[bmesh.types.BMEdge]) -> set[int]:
    return {edge.index for edge in edges}


def edges_at_indices(
    bm: bmesh.types.BMesh,
    indices: Iterable[int],
) -> list[bmesh.types.BMEdge]:
    bm.edges.ensure_lookup_table()
    result: list[bmesh.types.BMEdge] = []
    for index in indices:
        if 0 <= index < len(bm.edges):
            result.append(bm.edges[index])
    return result


def _resolve_target_edges(
    bm: bmesh.types.BMesh,
    mesh_select_mode: tuple[bool, bool, bool],
) -> ResolvedTargetEdges:
    vert_mode, edge_mode, face_mode = mesh_select_mode
    has_verts = any(vert.select for vert in bm.verts)
    has_edges = any(edge.select for edge in bm.edges)
    has_faces = any(face.select for face in bm.faces)

    if not has_verts and not has_edges and not has_faces:
        return ResolvedTargetEdges(_all_edge_indices(bm), face_boundary=False)

    if edge_mode and has_edges:
        return ResolvedTargetEdges(
            {edge.index for edge in bm.edges if edge.select},
            face_boundary=False,
        )

    if face_mode and has_faces:
        return ResolvedTargetEdges(_face_boundary_edge_indices(bm), face_boundary=True)

    if vert_mode and has_verts:
        return ResolvedTargetEdges(
            _edge_indices_from_edges(
                _verts_to_path_edges(bm, _verts_in_selection_order(bm)),
            ),
            face_boundary=False,
        )

    if has_edges:
        return ResolvedTargetEdges(
            {edge.index for edge in bm.edges if edge.select},
            face_boundary=False,
        )
    if has_faces:
        return ResolvedTargetEdges(_face_boundary_edge_indices(bm), face_boundary=True)
    if has_verts:
        return ResolvedTargetEdges(
            _edge_indices_from_edges(
                _verts_to_path_edges(bm, _verts_in_selection_order(bm)),
            ),
            face_boundary=False,
        )

    return ResolvedTargetEdges(_all_edge_indices(bm), face_boundary=False)


def _reference_edge_index(
    bm: bmesh.types.BMesh,
    target_indices: set[int],
    snap: EditElementSnapshot,
) -> int:
    if snap.active_edge >= 0 and snap.active_edge in target_indices:
        return snap.active_edge

    if snap.active_vert >= 0 and snap.active_vert < len(bm.verts):
        vert = bm.verts[snap.active_vert]
        linked = [edge.index for edge in vert.link_edges if edge.index in target_indices]
        if linked:
            return min(linked)

    return min(target_indices)


def _attr_name_for_kind(kind_v: str) -> str | None:
    if kind_v == _KIND_BEVEL_WEIGHT:
        return _BEVEL_WEIGHT_ATTR
    if kind_v == _KIND_CREASE:
        return ATTR_CREASE_EDGE
    return None


def _ensure_bmesh_float_layer(
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    attr_name: str,
) -> bmesh.types.BMLayerItem:
    """Return bmesh float layer synced to mesh.attributes (edit-mode safe)."""
    layer = bm.edges.layers.float.get(attr_name)
    if layer is not None:
        return layer

    if attr_name not in mesh.attributes:
        mesh.attributes.new(name=attr_name, type="FLOAT", domain="EDGE")

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    layer = bm.edges.layers.float.get(attr_name)
    if layer is not None:
        return layer

    return bm.edges.layers.float.new(attr_name)


def _edge_float_is_on(edge: bmesh.types.BMEdge, layer: bmesh.types.BMLayerItem) -> bool:
    return edge[layer] != 0.0


def _set_edge_float_on_edges(
    edges: Iterable[bmesh.types.BMEdge],
    layer: bmesh.types.BMLayerItem,
    *,
    turn_on: bool,
) -> None:
    value = _ON_FLOAT if turn_on else _OFF_FLOAT
    for edge in edges:
        edge[layer] = value


def _edge_is_on(
    kind_v: str,
    edge: bmesh.types.BMEdge,
    layers: dict[str, bmesh.types.BMLayerItem],
) -> bool:
    attr_name = _attr_name_for_kind(kind_v)
    if attr_name is not None:
        return _edge_float_is_on(edge, layers[attr_name])
    if kind_v == _KIND_SEAM:
        return bool(edge.seam)
    return not edge.smooth


def _set_edge_state(
    kind_v: str,
    edge: bmesh.types.BMEdge,
    layers: dict[str, bmesh.types.BMLayerItem],
    *,
    turn_on: bool,
) -> None:
    attr_name = _attr_name_for_kind(kind_v)
    if attr_name is not None:
        _set_edge_float_on_edges((edge,), layers[attr_name], turn_on=turn_on)
        return
    if kind_v == _KIND_SEAM:
        edge.seam = turn_on
        return
    edge.smooth = not turn_on


def _unfold_uv_on_face_patch(
    context: bpy.types.Context,
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    face_indices: tuple[int, ...],
) -> None:
    """Select face patch and run UV unwrap; caller restores selection."""
    if not face_indices:
        return

    if not mesh.uv_layers:
        mesh.uv_layers.new()

    for vert in bm.verts:
        vert.select = False
    for edge in bm.edges:
        edge.select = False
    for face in bm.faces:
        face.select = False

    bm.faces.ensure_lookup_table()
    for index in face_indices:
        if 0 <= index < len(bm.faces):
            bm.faces[index].select = True

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    ts = context.tool_settings
    if ts is not None:
        ts.mesh_select_mode = (False, False, True)

    try:
        bpy.ops.uv.unwrap()
    except RuntimeError:
        pass


def _toggle_edges(
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    target_edge_indices: set[int],
    snap: EditElementSnapshot,
    kind_v: str,
    *,
    clear_internal: bool = False,
    internal_edge_indices: set[int] | None = None,
    and_sharps: bool = False,
) -> int:
    if not target_edge_indices and not (clear_internal and internal_edge_indices):
        return 0

    attr_name = _attr_name_for_kind(kind_v)
    layers: dict[str, bmesh.types.BMLayerItem] = {}
    if attr_name is not None:
        layers[attr_name] = _ensure_bmesh_float_layer(bm, mesh, attr_name)

    bm.edges.ensure_lookup_table()

    if target_edge_indices:
        ref_index = _reference_edge_index(bm, target_edge_indices, snap)
        reference = bm.edges[ref_index]
        turn_on = not _edge_is_on(kind_v, reference, layers)
        target_edges = edges_at_indices(bm, target_edge_indices)
        if attr_name is not None:
            _set_edge_float_on_edges(target_edges, layers[attr_name], turn_on=turn_on)
        else:
            for edge in target_edges:
                _set_edge_state(kind_v, edge, layers, turn_on=turn_on)
                if and_sharps and kind_v == _KIND_SEAM:
                    _set_edge_state(_KIND_SHARP, edge, layers, turn_on=turn_on)

    if clear_internal and internal_edge_indices:
        internal_edges = edges_at_indices(bm, internal_edge_indices)
        if attr_name is not None:
            _set_edge_float_on_edges(internal_edges, layers[attr_name], turn_on=False)
        else:
            for edge in internal_edges:
                _set_edge_state(kind_v, edge, layers, turn_on=False)
                if and_sharps and kind_v == _KIND_SEAM:
                    _set_edge_state(_KIND_SHARP, edge, layers, turn_on=False)

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    affected = target_edge_indices
    if clear_internal and internal_edge_indices:
        affected = target_edge_indices | internal_edge_indices
    return len(affected)


def _clear_edges(
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    target_edge_indices: set[int],
    *,
    clear_internal: bool = False,
    internal_edge_indices: set[int] | None = None,
) -> int:
    affected = set(target_edge_indices)
    if clear_internal and internal_edge_indices:
        affected |= internal_edge_indices
    if not affected:
        return 0

    layers: dict[str, bmesh.types.BMLayerItem] = {}
    for attr_name in (_BEVEL_WEIGHT_ATTR, ATTR_CREASE_EDGE):
        layers[attr_name] = _ensure_bmesh_float_layer(bm, mesh, attr_name)

    bm.edges.ensure_lookup_table()
    target_edges = edges_at_indices(bm, affected)

    for attr_name in (_BEVEL_WEIGHT_ATTR, ATTR_CREASE_EDGE):
        _set_edge_float_on_edges(target_edges, layers[attr_name], turn_on=False)
    for edge in target_edges:
        edge.seam = False
        edge.smooth = True

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
    return len(affected)


def smart_edge_clear(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    clear_internal: bool = True,
) -> int:
    """Clear bevel weight, crease, seam, and sharp on resolved selection; restore state."""
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

        element_snap = _capture_element_selection(context, bm)
        resolved = _resolve_target_edges(bm, element_snap.mesh_select_mode)
        internal_edge_indices = (
            _face_internal_edge_indices(bm)
            if clear_internal and resolved.face_boundary
            else None
        )
        count = _clear_edges(
            bm,
            mesh,
            resolved.edge_indices,
            clear_internal=clear_internal and resolved.face_boundary,
            internal_edge_indices=internal_edge_indices,
        )
        _restore_element_selection(context, bm, mesh, element_snap)
        return count
    finally:
        if not in_edit:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
            if object_snap is not None:
                restore_selection_by_name_map(context, object_snap, {})


def smart_edge_toggle(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    kind: EdgeToggleKind | str,
    *,
    clear_internal: bool = True,
    and_sharps: bool = False,
    unfold_uv_after_seam: bool = False,
) -> int:
    """Toggle edge attribute on resolved selection; restore mode and selection."""
    kind_v = edge_toggle_kind_value(kind)
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

        element_snap = _capture_element_selection(context, bm)
        resolved = _resolve_target_edges(bm, element_snap.mesh_select_mode)
        internal_edge_indices = (
            _face_internal_edge_indices(bm)
            if clear_internal and resolved.face_boundary
            else None
        )
        count = _toggle_edges(
            bm,
            mesh,
            resolved.edge_indices,
            element_snap,
            kind_v,
            clear_internal=clear_internal and resolved.face_boundary,
            internal_edge_indices=internal_edge_indices,
            and_sharps=and_sharps,
        )
        if (
            unfold_uv_after_seam
            and kind_v == _KIND_SEAM
            and resolved.face_boundary
            and element_snap.face_indices
        ):
            _unfold_uv_on_face_patch(context, bm, mesh, element_snap.face_indices)
        _restore_element_selection(context, bm, mesh, element_snap)
        return count
    finally:
        if not in_edit:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
            if object_snap is not None:
                restore_selection_by_name_map(context, object_snap, {})


def capture_element_selection(
    context: bpy.types.Context,
    bm: bmesh.types.BMesh,
) -> EditElementSnapshot:
    return _capture_element_selection(context, bm)


def restore_element_selection(
    context: bpy.types.Context,
    bm: bmesh.types.BMesh,
    mesh: bpy.types.Mesh,
    snap: EditElementSnapshot,
) -> None:
    _restore_element_selection(context, bm, mesh, snap)


def resolve_target_edges(
    bm: bmesh.types.BMesh,
    mesh_select_mode: tuple[bool, bool, bool],
) -> ResolvedTargetEdges:
    return _resolve_target_edges(bm, mesh_select_mode)

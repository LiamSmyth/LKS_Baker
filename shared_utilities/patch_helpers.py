"""Per-face patch ID read/write for face sets and material indices."""

from __future__ import annotations

import bpy
import bmesh
import numpy as np
import random
from typing import List, Tuple

from .lks_constants import ATTR_SCULPT_FACE_SET

MODE_FACE_SETS = "FACE_SETS"
MODE_MATERIALS = "MATERIALS"

PATCH_MODE_ITEMS = [
    (MODE_FACE_SETS, "Face Sets", f"Operate on {ATTR_SCULPT_FACE_SET} attribute"),
    (MODE_MATERIALS, "Materials", "Operate on material_index per polygon"),
]

def read_patch_ids(obj: bpy.types.Object, mode: str) -> np.ndarray | None:
    """Return an int32 numpy array of per-face patch IDs, or *None*."""
    mesh = obj.data
    num_faces = len(mesh.polygons)
    if num_faces == 0:
        return None

    if mode == MODE_FACE_SETS:
        if ATTR_SCULPT_FACE_SET not in mesh.attributes:
            return None
        ids = np.empty(num_faces, dtype=np.int32)
        mesh.attributes[ATTR_SCULPT_FACE_SET].data.foreach_get("value", ids)
        return ids

    elif mode == MODE_MATERIALS:
        ids = np.empty(num_faces, dtype=np.int32)
        mesh.polygons.foreach_get("material_index", ids)
        return ids

    return None


def write_patch_ids(obj: bpy.types.Object, ids: np.ndarray, mode: str) -> None:
    """Write *ids* back to the mesh in the appropriate storage."""
    mesh = obj.data

    if mode == MODE_FACE_SETS:
        if ATTR_SCULPT_FACE_SET not in mesh.attributes:
            mesh.attributes.new(
                name=ATTR_SCULPT_FACE_SET, type="INT", domain="FACE")
        mesh.attributes[ATTR_SCULPT_FACE_SET].data.foreach_set("value", ids)
        mesh.update()

    elif mode == MODE_MATERIALS:
        _ensure_material_slots(obj, ids)
        mesh.polygons.foreach_set("material_index", ids)
        mesh.update()


def _find_principled_bsdf(mat: bpy.types.Material):
    """Return the Principled BSDF node from *mat*, or None.

    Searches by node type rather than name so it works across
    Blender versions where the default node name may differ.
    """
    if not mat.node_tree:
        return None
    for node in mat.node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node
    return None


def _set_bsdf_base_color(bsdf, r: float, g: float, b: float) -> None:
    """Set the Base Color input on a Principled BSDF node.

    Tries the socket name first, then falls back to index 0.
    """
    socket = bsdf.inputs.get("Base Color")
    if socket is None and len(bsdf.inputs) > 0:
        socket = bsdf.inputs[0]
    if socket is not None:
        socket.default_value = (r, g, b, 1.0)


def _make_random_color_material(name: str) -> bpy.types.Material:
    """Create a material with a random colour on both viewport and Principled BSDF."""
    mat = bpy.data.materials.new(name=name)
    r, g, b = random.random(), random.random(), random.random()
    mat.diffuse_color = (r, g, b, 1.0)
    bsdf = _find_principled_bsdf(mat)
    if bsdf:
        _set_bsdf_base_color(bsdf, r, g, b)
    return mat


def _ensure_material_slots(obj: bpy.types.Object, ids: np.ndarray) -> None:
    """Create material slots + random-colour materials for any new IDs."""
    mesh = obj.data
    unique_ids = np.unique(ids)
    max_id = int(unique_ids.max()) if len(unique_ids) else 0
    required = max_id + 1
    while len(mesh.materials) < required:
        mat_idx = len(mesh.materials)
        mat_name = f"Patch_{mat_idx}"
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            mat = _make_random_color_material(mat_name)
        mesh.materials.append(mat)


def ensure_contiguous_ids(ids: np.ndarray) -> np.ndarray:
    """Remap *ids* so they form a contiguous 0..N-1 range.

    Useful before writing to material_index where gaps waste slots.
    Returns the remapped array (same shape, dtype int32).
    """
    unique_sorted = np.unique(ids)
    remap = np.zeros(int(unique_sorted.max()) + 1, dtype=np.int32)
    for new_id, old_id in enumerate(unique_sorted):
        remap[old_id] = new_id
    return remap[ids]


# -- Adjacency helpers (bmesh-backed, read-only) ---------------------------

def build_adjacency_pairs(mesh: bpy.types.Mesh) -> List[Tuple[int, int]]:
    """Return a list of (face_idx_a, face_idx_b) for every internal edge."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()
    pairs = []
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            pairs.append((edge.link_faces[0].index, edge.link_faces[1].index))
    bm.free()
    return pairs


def boundary_vert_mask(
    mesh: bpy.types.Mesh,
    patch_ids: np.ndarray,
) -> np.ndarray:
    """Return a float64 array (len == num_verts) with 1.0 at boundary verts."""
    num_verts = len(mesh.vertices)
    mask = np.zeros(num_verts, dtype=np.float64)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            f1, f2 = edge.link_faces[0].index, edge.link_faces[1].index
            if patch_ids[f1] != patch_ids[f2]:
                mask[edge.verts[0].index] = 1.0
                mask[edge.verts[1].index] = 1.0
        elif len(edge.link_faces) == 1:
            mask[edge.verts[0].index] = 1.0
            mask[edge.verts[1].index] = 1.0
    bm.free()
    return mask


def boundary_edge_sharp_array(
    mesh: bpy.types.Mesh,
    patch_ids: np.ndarray,
) -> np.ndarray:
    """Return a bool numpy array marking edges on patch boundaries."""
    num_edges = len(mesh.edges)
    result = np.zeros(num_edges, dtype=np.bool_)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()
    for i, edge in enumerate(bm.edges):
        if len(edge.link_faces) == 2:
            f1, f2 = edge.link_faces[0].index, edge.link_faces[1].index
            if patch_ids[f1] != patch_ids[f2]:
                result[i] = True
    bm.free()
    return result


def dilate_vertex_weights(
    mesh: bpy.types.Mesh,
    weights: np.ndarray,
    rings: int,
) -> np.ndarray:
    """Max-propagate *weights* along edges for *rings* iterations."""
    if rings <= 0:
        return weights
    num_edges = len(mesh.edges)
    edge_verts = np.empty(num_edges * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edge_verts)
    edge_verts = edge_verts.reshape((num_edges, 2))

    w = weights.copy()
    for _ in range(rings):
        d = w.copy()
        np.maximum.at(d, edge_verts[:, 0], w[edge_verts[:, 1]])
        np.maximum.at(d, edge_verts[:, 1], w[edge_verts[:, 0]])
        w = d
    return w

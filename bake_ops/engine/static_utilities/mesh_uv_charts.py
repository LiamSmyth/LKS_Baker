"""Topology-correct UV chart IDs from mesh edge/UV seam analysis."""
from __future__ import annotations

import numpy as np

from .mesh_data import MeshData
from .uv_raster import _rasterize_one_triangle_scalar, uv_to_pixel


def triangle_uv_chart_ids(mesh: MeshData, *, uv_eps: float = 1e-5) -> np.ndarray:
    """Flood-fill triangle charts; split only at true UV seams."""
    faces = mesh.faces
    uvs = mesh.face_uvs.astype(np.float64)
    tri_count = len(faces)
    edge_entries: dict[tuple[int, int], list[tuple[int, np.ndarray, np.ndarray]]] = {}

    for tri_index, (i0, i1, i2) in enumerate(faces):
        for va, vb, ca, cb in ((i0, i1, 0, 1), (i1, i2, 1, 2), (i2, i0, 2, 0)):
            key = (min(va, vb), max(va, vb))
            edge_entries.setdefault(key, []).append(
                (tri_index, uvs[tri_index, ca], uvs[tri_index, cb]),
            )

    adjacency: list[list[int]] = [[] for _ in range(tri_count)]
    for entries in edge_entries.values():
        if len(entries) < 2:
            continue
        for left in range(len(entries)):
            tri_a, uva0, uva1 = entries[left]
            for right in range(left + 1, len(entries)):
                tri_b, uvb0, uvb1 = entries[right]
                matched = (
                    np.linalg.norm(uva0 - uvb0) <= uv_eps and np.linalg.norm(uva1 - uvb1) <= uv_eps
                ) or (
                    np.linalg.norm(uva0 - uvb1) <= uv_eps and np.linalg.norm(uva1 - uvb0) <= uv_eps
                )
                if not matched:
                    continue
                adjacency[tri_a].append(tri_b)
                adjacency[tri_b].append(tri_a)

    charts = np.full(tri_count, -1, dtype=np.int32)
    next_id = 0
    for start in range(tri_count):
        if charts[start] >= 0:
            continue
        stack = [start]
        charts[start] = next_id
        while stack:
            tri = stack.pop()
            for neighbor in adjacency[tri]:
                if charts[neighbor] < 0:
                    charts[neighbor] = next_id
                    stack.append(neighbor)
        next_id += 1
    return charts


def rasterize_triangle_chart_ids(
    mesh: MeshData,
    chart_ids: np.ndarray,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize per-triangle chart IDs into a texel island map."""
    island_id = np.full((image_size, image_size), -1, dtype=np.int32)
    raster_valid = np.zeros((image_size, image_size), dtype=bool)

    chart_image = np.full((image_size, image_size), -1.0, dtype=np.float32)
    counts = np.zeros((image_size, image_size), dtype=np.float32)
    for tri_uv, chart in zip(mesh.face_uvs, chart_ids):
        if chart < 0:
            continue
        tri_val = np.full(3, float(chart), dtype=np.float32)
        _rasterize_one_triangle_scalar(
            chart_image,
            raster_valid,
            counts,
            tri_uv,
            tri_val,
            image_size,
            accumulate=False,
        )
    painted = raster_valid
    island_id[painted] = chart_image[painted].astype(np.int32)
    return island_id, raster_valid


def island_id_from_mesh_charts(
    mesh: MeshData,
    image_size: int,
    valid: np.ndarray,
) -> np.ndarray:
    """Chart IDs for every valid texel; fall back to alpha CC elsewhere."""
    from .islands import _coalesce_island_ids, island_label_count, label_islands

    charts = triangle_uv_chart_ids(mesh)
    island_id, _ = rasterize_triangle_chart_ids(mesh, charts, image_size)
    fallback = label_islands(valid)
    missing = valid & (island_id < 0)
    island_id[missing] = fallback[missing]
    island_id[~valid] = -1
    if island_label_count(island_id) > 48:
        return fallback
    return _coalesce_island_ids(island_id, valid)

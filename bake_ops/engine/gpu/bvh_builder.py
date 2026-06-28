"""Linear BVH builder for GPU ray traversal (numpy only)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData
from lks_baker.bake_ops.engine.static_utilities.runtime_log import log, timed_step


@dataclass
class GPUBVH:
    """Packed node/triangle buffers for GPU textures."""

    nodes: np.ndarray
    tri_corners: np.ndarray
    tri_count: int
    node_count: int


def _choose_split(
    start: int,
    end: int,
    order: np.ndarray,
    centroids: np.ndarray,
    bmins: np.ndarray,
    bmaxs: np.ndarray,
) -> int:
    """Return split index strictly between start and end."""
    count = end - start
    if count <= 1:
        raise ValueError(f"cannot split range [{start}, {end})")

    box_min = bmins[order[start:end]].min(axis=0)
    box_max = bmaxs[order[start:end]].max(axis=0)
    extent = box_max - box_min
    cent_subset = centroids[order[start:end]]

    for axis in np.argsort(extent)[::-1]:
        coords = cent_subset[:, axis]
        spread = float(coords.max() - coords.min())
        if spread <= 1e-12:
            continue
        median = float(np.median(coords))
        split_rel = int(np.searchsorted(coords, median, side="left"))
        split_rel = min(max(split_rel, 1), count - 1)
        if 0 < split_rel < count:
            return start + split_rel

    return start + max(1, count // 2)


def build_gpu_bvh(high: MeshData, vertex_curvature: np.ndarray) -> GPUBVH:
    """Median-split BVH; one triangle per leaf. Iterative build avoids recursion blowup."""
    vertices = high.vertices
    faces = high.faces
    tri_count = len(faces)

    tri_corners = np.zeros((tri_count, 3, 4), dtype=np.float32)
    centroids = np.zeros((tri_count, 3), dtype=np.float64)
    bmins = np.zeros((tri_count, 3), dtype=np.float64)
    bmaxs = np.zeros((tri_count, 3), dtype=np.float64)

    for index, face in enumerate(faces):
        tri = vertices[face]
        centroids[index] = tri.mean(axis=0)
        bmins[index], bmaxs[index] = tri.min(axis=0), tri.max(axis=0)
        for corner in range(3):
            vi = int(face[corner])
            tri_corners[index, corner, :3] = vertices[vi].astype(np.float32)
            tri_corners[index, corner, 3] = float(vertex_curvature[vi])

    order = np.arange(tri_count, dtype=np.int32)
    nodes: list[tuple[np.ndarray, np.ndarray, int, int]] = []

    log(f"build_gpu_bvh: {tri_count} triangles")
    with timed_step("build_gpu_bvh median split"):
        work: list[tuple[int, int, int, int]] = [(0, tri_count, -1, -1)]
        while work:
            start, end, parent_idx, side = work.pop()
            count = end - start
            box_min = bmins[order[start:end]].min(axis=0)
            box_max = bmaxs[order[start:end]].max(axis=0)

            node_index = len(nodes)
            nodes.append((box_min, box_max, -1, -1))

            if parent_idx >= 0:
                pmin, pmax, pl, pr = nodes[parent_idx]
                if side == 0:
                    nodes[parent_idx] = (pmin, pmax, node_index, pr)
                else:
                    nodes[parent_idx] = (pmin, pmax, pl, node_index)

            if count <= 1:
                tri_index = int(order[start])
                nodes[node_index] = (box_min, box_max, tri_index, -1)
                continue

            split = _choose_split(start, end, order, centroids, bmins, bmaxs)
            if not (start < split < end):
                raise RuntimeError(f"BVH split failed to progress: [{start}, {end}) -> {split}")

            work.append((split, end, node_index, 1))
            work.append((start, split, node_index, 0))

    node_count = len(nodes)
    log(f"build_gpu_bvh: {node_count} nodes")
    packed = np.zeros((node_count, 2, 4), dtype=np.float32)
    for index, (bmin, bmax, left, right) in enumerate(nodes):
        packed[index, 0, :3] = bmin.astype(np.float32)
        packed[index, 0, 3] = float(left)
        packed[index, 1, :3] = bmax.astype(np.float32)
        packed[index, 1, 3] = float(right)

    return GPUBVH(
        nodes=packed,
        tri_corners=tri_corners,
        tri_count=tri_count,
        node_count=node_count,
    )

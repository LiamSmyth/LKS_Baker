"""Method 2: cotangent Laplacian mesh curvature + UV bake."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .uv_raster import rasterize_triangles


@dataclass
class MeshData:
    """CPU mesh arrays (vertices, faces, UVs) for bake methods.

    Attributes:
        vertices: ``np.ndarray`` value.
        faces: ``np.ndarray`` value.
        normals: ``np.ndarray`` value.
        face_uvs: ``np.ndarray`` value.
    """
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray
    face_uvs: np.ndarray
    face_int_ids: np.ndarray | None = None


def _cotangent(a: np.ndarray, b: np.ndarray) -> float:
    cos_theta = float(np.dot(a, b))
    sin_theta = float(np.linalg.norm(np.cross(a, b)))
    return cos_theta / max(sin_theta, 1e-8)


def cotangent_vertex_curvature(mesh: MeshData) -> np.ndarray:
    """Cotangent vertex curvature.

    Args:
        mesh: Triangulated ``MeshData`` for mesh-backed bakes.

    Returns:
        ``np.ndarray`` result.
    """
    vertices = mesh.vertices
    faces = mesh.faces
    normals = mesh.normals
    count = len(vertices)

    area = np.zeros(count, dtype=np.float64)
    laplacian = np.zeros((count, 3), dtype=np.float64)

    for i0, i1, i2 in faces:
        p0, p1, p2 = vertices[i0], vertices[i1], vertices[i2]
        tri_area = 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0))
        area[i0] += tri_area / 3.0
        area[i1] += tri_area / 3.0
        area[i2] += tri_area / 3.0

        e01, e02 = p1 - p0, p2 - p0
        e12 = p2 - p1

        cot0 = _cotangent(e01, e02)
        cot1 = _cotangent(-e01, e12)
        cot2 = _cotangent(-e02, -e12)

        laplacian[i0] += (p1 - p0) * cot2 + (p2 - p0) * cot1
        laplacian[i1] += (p0 - p1) * cot2 + (p2 - p1) * cot0
        laplacian[i2] += (p0 - p2) * cot1 + (p1 - p2) * cot0

    curvature = np.zeros(count, dtype=np.float32)
    for index in range(count):
        if area[index] <= 1e-8:
            continue
        mean_normal = laplacian[index] / (2.0 * area[index])
        curvature[index] = -0.5 * float(np.dot(mean_normal, normals[index]))
    return curvature


def bake_vertex_curvature_to_uv(
    mesh: MeshData,
    vertex_curvature: np.ndarray,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Bake vertex curvature to uv.

    Args:
        mesh: Triangulated ``MeshData`` for mesh-backed bakes.
        vertex_curvature: ``np.ndarray`` value.
        image_size: Square bake resolution (H = W).

    Returns:
        Tuple matching annotation ``tuple[np.ndarray, np.ndarray]``.
    """
    tri_vals = vertex_curvature[mesh.faces]
    image, valid, _ = rasterize_triangles(mesh.face_uvs, tri_vals, image_size, flat=0.0)
    return image.astype(np.float32), valid


def sample_vertex_field_at_valid_uv(
    mesh: MeshData,
    vertex_field: np.ndarray,
    valid: np.ndarray,
    image_size: int,
    island_id: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample per-vertex field at every ``valid`` texel via UV point-in-triangle."""
    from .islands import island_inpaint_gaps
    from .uv_raster import barycentric_all_tris, pixel_to_uv, rasterize_triangles

    tri_vals = vertex_field[mesh.faces]
    baked, raster_valid, _ = rasterize_triangles(
        mesh.face_uvs,
        tri_vals,
        image_size,
        flat=0.0,
    )
    baked = baked.astype(np.float32)
    missing = valid & (~raster_valid)
    if np.any(missing):
        tri_uv = mesh.face_uvs.astype(np.float64)
        ys, xs = np.nonzero(missing)
        # Cap fill work — remaining gaps use inpaint below.
        max_fill = min(len(xs), 8192)
        for y, x in zip(ys[:max_fill].tolist(), xs[:max_fill].tolist()):
            uv = pixel_to_uv(int(x), int(y), image_size)
            weights, inside = barycentric_all_tris(uv, tri_uv)
            if not np.any(inside):
                continue
            tri_index = int(np.flatnonzero(inside)[0])
            baked[y, x] = float(np.dot(weights[tri_index], tri_vals[tri_index]))
            raster_valid[y, x] = True

    if island_id is not None:
        known = raster_valid & valid
        still_missing = valid & (~known)
        if np.any(still_missing):
            baked = island_inpaint_gaps(baked, island_id, known)
            raster_valid = valid.copy()
    return baked, valid

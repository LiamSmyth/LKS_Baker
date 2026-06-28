"""Rasterize low-poly surface position/normal into UV atlas."""
from __future__ import annotations

import numpy as np

from .mesh_data import MeshData
from .uv_raster import rasterize_triangles, rasterize_triangles_vector


def rasterize_uv_coverage(mesh: MeshData, image_size: int) -> np.ndarray:
    """Return bool H×W mask of texels covered by ``mesh`` UV triangles."""
    tri_ones = np.ones((len(mesh.faces), 3), dtype=np.float32)
    _, coverage, _ = rasterize_triangles(mesh.face_uvs, tri_ones, image_size, flat=0.0)
    return coverage


def rasterize_low_surface(
    low: MeshData,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (position[H,W,3], normal[H,W,3], valid[H,W])."""
    pos_corners = low.vertices[low.faces].astype(np.float32)
    norm_corners = low.normals[low.faces].astype(np.float32)
    position, coverage, _ = rasterize_triangles_vector(
        low.face_uvs,
        pos_corners,
        image_size,
        channels=3,
        flat=0.0,
    )
    normal, _, _ = rasterize_triangles_vector(
        low.face_uvs,
        norm_corners,
        image_size,
        channels=3,
        flat=0.0,
    )
    lengths = np.linalg.norm(normal, axis=-1, keepdims=True)
    lengths = np.maximum(lengths, 1e-8)
    normal = normal / lengths
    return position, normal, coverage

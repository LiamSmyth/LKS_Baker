"""Rasterize per-vertex or per-edge values into UV atlas (OpenGL V -> PNG row)."""
from __future__ import annotations

import numpy as np


def uv_to_pixel(uv: np.ndarray, image_size: int) -> np.ndarray:
    """Map OpenGL UV (0..1, V up) to PNG pixel coordinates (origin top-left)."""
    px = uv[..., 0] * (image_size - 1)
    py = (1.0 - uv[..., 1]) * (image_size - 1)
    return np.stack([px, py], axis=-1)


def pixel_to_uv(x: int, y: int, image_size: int) -> np.ndarray:
    """Inverse of ``uv_to_pixel`` for a single texel center."""
    u = float(x) / max(image_size - 1, 1)
    v = 1.0 - float(y) / max(image_size - 1, 1)
    return np.array([u, v], dtype=np.float64)


def barycentric(point: np.ndarray, v0: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """Barycentric.

    Args:
        point: ``np.ndarray`` value.
        v0: ``np.ndarray`` value.
        v1: ``np.ndarray`` value.
        v2: ``np.ndarray`` value.

    Returns:
        ``np.ndarray`` result.
    """
    v0v1 = v1 - v0
    v0v2 = v2 - v0
    v0p = point - v0
    d00 = np.dot(v0v1, v0v1)
    d01 = np.dot(v0v1, v0v2)
    d11 = np.dot(v0v2, v0v2)
    d20 = np.dot(v0p, v0v1)
    d21 = np.dot(v0p, v0v2)
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-12:
        return np.array([-1.0, -1.0, -1.0])
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    return np.array([u, v, w])


def barycentric_points(
    points: np.ndarray,
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Barycentric weights for N UV points against one triangle."""
    v0v1 = v1 - v0
    v0v2 = v2 - v0
    v0p = points - v0
    d00 = float(np.dot(v0v1, v0v1))
    d01 = float(np.dot(v0v1, v0v2))
    d11 = float(np.dot(v0v2, v0v2))
    d20 = v0p @ v0v1
    d21 = v0p @ v0v2
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-12:
        count = len(points)
        return np.zeros((count, 3), dtype=np.float64), np.zeros(count, dtype=bool)
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    weights = np.stack([u, v, w], axis=1)
    inside = (u >= -1e-5) & (v >= -1e-5) & (w >= -1e-5)
    return weights, inside


def _triangle_pixel_bbox(px: np.ndarray, image_size: int) -> tuple[int, int, int, int] | None:
    min_x = max(0, int(np.floor(px[:, 0].min())))
    max_x = min(image_size - 1, int(np.ceil(px[:, 0].max())))
    min_y = max(0, int(np.floor(px[:, 1].min())))
    max_y = min(image_size - 1, int(np.ceil(px[:, 1].max())))
    if min_x > max_x or min_y > max_y:
        return None
    return min_x, max_x, min_y, max_y


def _rasterize_one_triangle_scalar(
    image: np.ndarray,
    valid: np.ndarray,
    counts: np.ndarray,
    tri_uv: np.ndarray,
    tri_val: np.ndarray,
    image_size: int,
    *,
    accumulate: bool,
) -> None:
    px = uv_to_pixel(tri_uv, image_size)
    bbox = _triangle_pixel_bbox(px, image_size)
    if bbox is None:
        return
    min_x, max_x, min_y, max_y = bbox
    xs = np.arange(min_x, max_x + 1, dtype=np.float64) + 0.5
    ys = np.arange(min_y, max_y + 1, dtype=np.float64) + 0.5
    grid_x, grid_y = np.meshgrid(xs, ys)
    points = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1)
    weights, inside = barycentric_points(points, px[0], px[1], px[2])
    if not np.any(inside):
        return
    values = weights @ tri_val.astype(np.float64)
    yy = grid_y.ravel()[inside].astype(np.intp)
    xx = grid_x.ravel()[inside].astype(np.intp)
    vals = values[inside].astype(np.float32)
    if accumulate:
        np.add.at(image, (yy, xx), vals)
        np.add.at(counts, (yy, xx), 1.0)
    else:
        image[yy, xx] = vals
    valid[yy, xx] = True


def _rasterize_one_triangle_vector(
    image: np.ndarray,
    valid: np.ndarray,
    counts: np.ndarray,
    tri_uv: np.ndarray,
    tri_val: np.ndarray,
    image_size: int,
    *,
    accumulate: bool,
) -> None:
    px = uv_to_pixel(tri_uv, image_size)
    bbox = _triangle_pixel_bbox(px, image_size)
    if bbox is None:
        return
    min_x, max_x, min_y, max_y = bbox
    xs = np.arange(min_x, max_x + 1, dtype=np.float64) + 0.5
    ys = np.arange(min_y, max_y + 1, dtype=np.float64) + 0.5
    grid_x, grid_y = np.meshgrid(xs, ys)
    points = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1)
    weights, inside = barycentric_points(points, px[0], px[1], px[2])
    if not np.any(inside):
        return
    corner_vals = tri_val.astype(np.float64)
    values = weights @ corner_vals
    yy = grid_y.ravel()[inside].astype(np.intp)
    xx = grid_x.ravel()[inside].astype(np.intp)
    vals = values[inside].astype(np.float32)
    if accumulate:
        np.add.at(image, (yy, xx), vals)
        np.add.at(counts, (yy, xx), 1.0)
    else:
        image[yy, xx] = vals
    valid[yy, xx] = True


def barycentric_all_tris(
    point: np.ndarray,
    tri_uv: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Barycentric weights for one UV point against all triangles.

    Returns (weights[T, 3], inside[T] bool).
    """
    v0 = tri_uv[:, 0, :]
    v1 = tri_uv[:, 1, :]
    v2 = tri_uv[:, 2, :]
    v0v1 = v1 - v0
    v0v2 = v2 - v0
    v0p = point - v0
    d00 = np.sum(v0v1 * v0v1, axis=1)
    d01 = np.sum(v0v1 * v0v2, axis=1)
    d11 = np.sum(v0v2 * v0v2, axis=1)
    d20 = np.sum(v0p * v0v1, axis=1)
    d21 = np.sum(v0p * v0v2, axis=1)
    denom = d00 * d11 - d01 * d01
    valid = np.abs(denom) >= 1e-12
    v = np.zeros_like(denom)
    w = np.zeros_like(denom)
    u = np.zeros_like(denom)
    v[valid] = (d11[valid] * d20[valid] - d01[valid] * d21[valid]) / denom[valid]
    w[valid] = (d00[valid] * d21[valid] - d01[valid] * d20[valid]) / denom[valid]
    u[valid] = 1.0 - v[valid] - w[valid]
    weights = np.stack([u, v, w], axis=1)
    inside = valid & (u >= -1e-5) & (v >= -1e-5) & (w >= -1e-5)
    return weights, inside


def rasterize_triangles(
    uvs: np.ndarray,
    values: np.ndarray,
    image_size: int,
    *,
    flat: float = 0.0,
    accumulate: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rasterize triangle list into image.

    uvs: (T, 3, 2) OpenGL UVs
    values: (T, 3) scalar per corner
    """
    image = np.full((image_size, image_size), flat, dtype=np.float32)
    valid = np.zeros((image_size, image_size), dtype=bool)
    counts = np.zeros((image_size, image_size), dtype=np.float32)

    for tri_uv, tri_val in zip(uvs, values):
        _rasterize_one_triangle_scalar(
            image,
            valid,
            counts,
            tri_uv,
            tri_val,
            image_size,
            accumulate=accumulate,
        )

    if accumulate:
        mask = counts > 0.0
        image[mask] /= counts[mask]
    return image, valid, counts


def rasterize_triangles_vector(
    uvs: np.ndarray,
    values: np.ndarray,
    image_size: int,
    channels: int,
    *,
    flat: float = 0.0,
    accumulate: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rasterize per-corner vector attributes into H×W×C (one pass over triangles)."""
    image = np.full((image_size, image_size, channels), flat, dtype=np.float32)
    valid = np.zeros((image_size, image_size), dtype=bool)
    counts = np.zeros((image_size, image_size), dtype=np.float32)

    for tri_uv, tri_val in zip(uvs, values):
        _rasterize_one_triangle_vector(
            image,
            valid,
            counts,
            tri_uv,
            tri_val,
            image_size,
            accumulate=accumulate,
        )

    if accumulate:
        mask = counts > 0.0
        image[mask] /= counts[mask, None]
    return image, valid, counts


def splat_edge_segment(
    image: np.ndarray,
    valid: np.ndarray,
    uv_a: np.ndarray,
    uv_b: np.ndarray,
    value: float,
    image_size: int,
    *,
    radius_texels: float = 4.0,
) -> None:
    """Add a soft line along a UV edge segment (for dihedral curvature)."""
    pa = uv_to_pixel(uv_a[None], image_size)[0]
    pb = uv_to_pixel(uv_b[None], image_size)[0]
    min_x = max(0, int(np.floor(min(pa[0], pb[0]) - radius_texels)))
    max_x = min(image_size - 1, int(np.ceil(max(pa[0], pb[0]) + radius_texels)))
    min_y = max(0, int(np.floor(min(pa[1], pb[1]) - radius_texels)))
    max_y = min(image_size - 1, int(np.ceil(max(pa[1], pb[1]) + radius_texels)))

    ab = pb - pa
    ab_len_sq = max(float(np.dot(ab, ab)), 1e-8)
    sigma_sq = 2.0 * radius_texels * radius_texels

    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            p = np.array([x + 0.5, y + 0.5], dtype=np.float64)
            t = np.clip(float(np.dot(p - pa, ab) / ab_len_sq), 0.0, 1.0)
            q = pa + t * ab
            dist_sq = float(np.dot(p - q, p - q))
            falloff = np.exp(-dist_sq / sigma_sq)
            image[y, x] += value * falloff
            if falloff > 1e-4:
                valid[y, x] = True

"""Island-aware texture sampling — internal OpenGL PNG neighbor layout."""
from __future__ import annotations

import numpy as np

from .coords import internal_v_neighbor_indices


def island_shift(
    field: np.ndarray,
    island_id: np.ndarray,
    *,
    dy: int = 0,
    dx: int = 0,
) -> np.ndarray:
    """Shift field by (dy, dx), zeroing samples that cross island boundaries."""
    out = np.zeros_like(field, dtype=np.float32)
    height, width = field.shape[:2]

    y_src = slice(max(0, -dy), height - max(0, dy))
    y_dst = slice(max(0, dy), height - max(0, -dy))
    x_src = slice(max(0, -dx), width - max(0, dx))
    x_dst = slice(max(0, dx), width - max(0, -dx))

    shifted_id = np.full_like(island_id, -2, dtype=np.int32)
    shifted_id[y_dst, x_dst] = island_id[y_src, x_src]

    same = island_id == shifted_id
    if field.ndim == 2:
        out[y_dst, x_dst] = field[y_src, x_src]
        out[~same] = 0.0
    else:
        out[y_dst, x_dst, :] = field[y_src, x_src, :]
        out[~same, :] = 0.0
    return out


def island_central_diff_x(field: np.ndarray, island_id: np.ndarray) -> np.ndarray:
    """Central difference along atlas U (PNG column axis)."""
    left = island_shift(field, island_id, dx=-1)
    right = island_shift(field, island_id, dx=1)
    return right - left


def island_central_diff_v(field: np.ndarray, island_id: np.ndarray) -> np.ndarray:
    """Central difference along atlas V (internal PNG row order: row 0 = UV top)."""
    plus_v, minus_v = internal_v_neighbor_indices()
    up = island_shift(field, island_id, dy=plus_v)
    down = island_shift(field, island_id, dy=minus_v)
    return up - down


def island_shift_mask(
    island_id: np.ndarray,
    *,
    dy: int = 0,
    dx: int = 0,
) -> np.ndarray:
    """True where ``island_shift`` would copy a same-island neighbor."""
    one = np.ones(island_id.shape[:2], dtype=np.float32)
    return island_shift(one, island_id, dy=dy, dx=dx) > 0.5


_POSITION_DERIV_MIN = 1e-5


def _safe_normalize_vectors(v: np.ndarray, *, axis: int = -1, eps: float = 1e-6) -> np.ndarray:
    length = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.maximum(length, eps)


def object_normal_uv_tangent_field(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    *,
    radius: int = 1,
) -> np.ndarray:
    """Project object-space normals into a UV-aligned tangent frame for divergence/height.

    Inputs must be internal canonical: ``InternalNormalSpace.OBJECT_BLENDER`` normals and
    ``PositionSpace.OBJECT_BLENDER`` position. Texels without usable position derivatives
    remain zero (no tangent-normal fallback).
    """
    height, width = valid.shape[:2]
    out = np.zeros((height, width, 3), dtype=np.float32)
    if not np.any(valid):
        return out

    sample_radius = max(1, int(radius))
    pv_plus, pv_minus = internal_v_neighbor_indices()
    scale = 2.0 * float(sample_radius)

    n_surface = _safe_normalize_vectors(object_normal.astype(np.float32))
    position_field = position.astype(np.float32)
    dpdu = (
        island_shift(position_field, island_id, dx=sample_radius)
        - island_shift(position_field, island_id, dx=-sample_radius)
    ) / scale
    dpdv = (
        island_shift(position_field, island_id, dy=pv_plus * sample_radius)
        - island_shift(position_field, island_id, dy=pv_minus * sample_radius)
    ) / scale

    len_u = np.linalg.norm(dpdu, axis=-1)
    len_v = np.linalg.norm(dpdv, axis=-1)
    cross_len = np.linalg.norm(np.cross(dpdu, dpdv, axis=-1), axis=-1)
    deriv_ok = (
        valid
        & (len_u > _POSITION_DERIV_MIN)
        & (len_v > _POSITION_DERIV_MIN)
        & (cross_len > _POSITION_DERIV_MIN)
    )
    if not np.any(deriv_ok):
        return out

    n_geom = _safe_normalize_vectors(np.cross(dpdu, dpdv, axis=-1))
    flip = np.sum(n_geom * n_surface, axis=-1, keepdims=True) < 0.0
    n_geom = np.where(flip, -n_geom, n_geom)

    tangent = dpdu - n_geom * np.sum(dpdu * n_geom, axis=-1, keepdims=True)
    tangent = _safe_normalize_vectors(tangent)
    bitangent = _safe_normalize_vectors(np.cross(n_geom, tangent, axis=-1))
    tangent = _safe_normalize_vectors(np.cross(bitangent, n_geom, axis=-1))

    projected = np.stack(
        (
            np.sum(n_surface * tangent, axis=-1),
            np.sum(n_surface * bitangent, axis=-1),
            np.sum(n_surface * n_geom, axis=-1),
        ),
        axis=-1,
    ).astype(np.float32)
    out[deriv_ok] = projected[deriv_ok]
    return out


def tangent_normal_divergence(
    normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    *,
    radius: int = 1,
) -> np.ndarray:
    """Divergence of tangent-plane normal components (internal OpenGL PNG layout).

    curvature ~= dNx/du + dNy/dv

    Uses island-aware central differences with a ``radius``-texel stencil. Unlike the
    legacy strict 4-neighbor mask, valid texels on each island receive a value whenever
    ``island_shift`` can form the wider stencil (boundary texels use one-sided pairs).
    """
    sample_radius = max(1, int(radius))
    nx = normal[..., 0].astype(np.float32, copy=False)
    ny = normal[..., 1].astype(np.float32, copy=False)
    pv_plus, pv_minus = internal_v_neighbor_indices()

    dnx = (
        island_shift(nx, island_id, dx=sample_radius)
        - island_shift(nx, island_id, dx=-sample_radius)
    )
    dny = (
        island_shift(ny, island_id, dy=pv_plus * sample_radius)
        - island_shift(ny, island_id, dy=pv_minus * sample_radius)
    )

    out = np.zeros(normal.shape[:2], dtype=np.float32)
    out[valid] = (dnx + dny)[valid]
    return out

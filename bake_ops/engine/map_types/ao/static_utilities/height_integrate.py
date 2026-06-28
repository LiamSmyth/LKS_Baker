"""Poisson height integration from object-normal UV tangent gradients."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.settings.ao_settings import HeightIntegrateSettings
from lks_baker.bake_ops.engine.static_utilities.islands import label_islands
from lks_baker.bake_ops.engine.static_utilities.sampling import (
    island_central_diff_x,
    island_central_diff_v,
    object_normal_uv_tangent_field,
)


def object_normal_to_gradients(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Frankot-Chellappa-style gradients from OSNM projected to UV tangent frame."""
    field = object_normal_uv_tangent_field(object_normal, position, island_id, valid)
    nz = np.maximum(np.abs(field[..., 2]), 0.05)
    grad_x = -field[..., 0] / nz
    grad_y = -field[..., 1] / nz
    grad_x[~valid] = 0.0
    grad_y[~valid] = 0.0
    return grad_x.astype(np.float32), grad_y.astype(np.float32)


def _fft_poisson_island(
    grad_x: np.ndarray,
    grad_y: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """FFT Poisson solve on a single island mask."""
    height, width = grad_x.shape
    gx = grad_x * mask
    gy = grad_y * mask
    island_labels = label_islands(mask)

    div = island_central_diff_x(gx, island_labels) * 0.5
    div += island_central_diff_v(gy, island_labels) * 0.5

    fy = np.fft.fftfreq(height)[:, None]
    fx = np.fft.fftfreq(width)[None, :]
    denom = (2.0 * np.pi) ** 2 * (fx * fx + fy * fy)
    denom[0, 0] = 1.0
    div_k = np.fft.fft2(div)
    h_k = div_k / np.maximum(denom, 1e-8)
    h_k[0, 0] = 0.0
    h = np.real(np.fft.ifft2(h_k)).astype(np.float32)
    h[~mask] = 0.0
    if np.any(mask):
        h[mask] -= float(np.mean(h[mask]))
    return h


def _jacobi_poisson(
    grad_x: np.ndarray,
    grad_y: np.ndarray,
    mask: np.ndarray,
    iterations: int,
) -> np.ndarray:
    island_id = label_islands(mask)
    div = island_central_diff_x(grad_x, island_id) * 0.5
    div += island_central_diff_v(grad_y, island_id) * 0.5
    h = np.zeros_like(grad_x, dtype=np.float32)
    for _ in range(max(1, iterations)):
        h_up = np.roll(h, -1, axis=0)
        h_down = np.roll(h, 1, axis=0)
        h_left = np.roll(h, -1, axis=1)
        h_right = np.roll(h, 1, axis=1)
        neighbor = h_up + h_down + h_left + h_right - div
        h = np.where(mask, 0.25 * neighbor, 0.0)
    return h.astype(np.float32)


def integrate_height_from_object_normal(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: HeightIntegrateSettings,
) -> np.ndarray:
    """Reconstruct height field from object normal + position (per-island FFT default)."""
    grad_x, grad_y = object_normal_to_gradients(object_normal, position, island_id, valid)
    scale = float(settings.height_scale)
    grad_x *= scale
    grad_y *= scale

    height = np.zeros(valid.shape, dtype=np.float32)
    labels = np.unique(island_id[valid])
    for label in labels:
        if label < 0:
            continue
        mask = valid & (island_id == label)
        if not np.any(mask):
            continue
        if settings.integration_solver == "jacobi":
            patch = _jacobi_poisson(grad_x, grad_y, mask, settings.jacobi_iterations)
        else:
            patch = _fft_poisson_island(grad_x, grad_y, mask)
        height[mask] = patch[mask]
    return height.astype(np.float32)

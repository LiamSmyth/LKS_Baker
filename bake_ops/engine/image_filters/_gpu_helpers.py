"""Shared GPU helpers for image filters."""
from __future__ import annotations

import numpy as np

_GAUSSIAN_TRUNCATE = 4.0
"""Match ``scipy.ndimage.gaussian_filter`` default truncation."""


def gaussian_1d_weights(sigma: float) -> np.ndarray:
    """Return normalized 1D Gaussian weights for *sigma* (scipy-compatible radius)."""
    if sigma <= 0.0:
        return np.array([1.0], dtype=np.float32)
    radius = int(_GAUSSIAN_TRUNCATE * sigma + 0.5)
    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
    weights = np.exp(-0.5 * (offsets / float(sigma)) ** 2)
    weights /= float(weights.sum())
    return weights.astype(np.float32)


def upload_kernel_texture(weights: np.ndarray):
    """Upload 1×N Gaussian weights as R32F lookup texture."""
    import gpu

    count = int(weights.size)
    table = weights.astype(np.float32).reshape(1, count)
    flat = np.ascontiguousarray(table.reshape(-1))
    buffer = gpu.types.Buffer("FLOAT", flat.size, flat)
    return gpu.types.GPUTexture(size=(count, 1), format="R32F", data=buffer)


def upload_scalar_texture(field: np.ndarray):
    """Upload H×W float field as R32F (PNG row 0 = top)."""
    import gpu

    upload = np.ascontiguousarray(np.flipud(field.astype(np.float32)))
    height, width = upload.shape[:2]
    buffer = gpu.types.Buffer("FLOAT", upload.size, upload)
    return gpu.types.GPUTexture(size=(width, height), format="R32F", data=buffer)


def upload_mask_texture(mask: np.ndarray):
    """Upload boolean/float mask as R32F (PNG row 0 = top)."""
    return upload_scalar_texture(mask.astype(np.float32))


def read_rg_field(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split RG channels from an RGBA32F readback in PNG layout."""
    red = rgba[..., 0].astype(np.float32, copy=False)
    green = rgba[..., 1].astype(np.float32, copy=False)
    return red, green

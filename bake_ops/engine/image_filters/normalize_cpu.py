"""Percentile normalization and unitization for masked float image fields."""
from __future__ import annotations

import numpy as np


def percentile_scale(
    values: np.ndarray,
    mask: np.ndarray,
    *,
    percentile: float = 95.0,
    floor: float = 1e-6,
) -> float:
    """Return a percentile scale from ``values[mask]``."""
    vals = values[mask]
    if vals.size == 0:
        return 1.0
    scale = float(np.percentile(vals, percentile))
    return max(scale, floor)


def filter_signed(
    signed: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    contrast: float = 1.0,
    flat: float = 0.5,
    amplitude: float | None = None,
) -> np.ndarray:
    """Unitize a signed scalar field to mid-gray grayscale in [0, 1]."""
    if amplitude is not None:
        return _signed_to_mid_gray(
            signed,
            valid,
            percentile=percentile,
            amplitude=amplitude,
            flat=flat,
        )

    out = np.full(signed.shape, flat, dtype=np.float32)
    scale = percentile_scale(np.abs(signed), valid, percentile=percentile)
    normalized = np.clip(signed / scale, -1.0, 1.0) * contrast
    gray = normalized * 0.5 + flat
    out[valid] = gray[valid]
    return np.clip(out, 0.0, 1.0)


def filter_positive(
    values: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    flat: float = 0.0,
) -> np.ndarray:
    """Unitize a non-negative scalar field to [0, 1] via percentile scaling."""
    out = np.full(values.shape, flat, dtype=np.float32)
    scale = percentile_scale(values, valid, percentile=percentile)
    out[valid] = np.clip(values[valid] / scale, 0.0, 1.0)
    return out


def _signed_to_mid_gray(
    signed: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    amplitude: float = 0.08,
    flat: float = 0.5,
) -> np.ndarray:
    """Map signed field to mid-gray with bounded amplitude (generic packing helper)."""
    out = np.full(signed.shape, flat, dtype=np.float32)
    scale = percentile_scale(np.abs(signed), valid, percentile=percentile)
    normalized = np.clip(signed / scale, -1.0, 1.0) * amplitude
    out[valid] = (flat + normalized)[valid]
    return np.clip(out, 0.0, 1.0)


unitize_signed = filter_signed
unitize_positive = filter_positive

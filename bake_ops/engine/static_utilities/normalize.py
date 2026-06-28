"""Curvature-specific gray packing (uses generic percentile helpers from image_filters)."""
from __future__ import annotations

import numpy as np

from ..image_filters.normalize_cpu import percentile_scale


def signed_to_target_gray(
    signed: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    amplitude: float = 0.08,
    flat: float = 0.5,
) -> np.ndarray:
    """Map signed curvature to mid-gray target convention (light convex, dark concave)."""
    out = np.full(signed.shape, flat, dtype=np.float32)
    scale = percentile_scale(np.abs(signed), valid, percentile=percentile)
    normalized = np.clip(signed / scale, -1.0, 1.0) * amplitude
    out[valid] = (flat + normalized)[valid]
    return np.clip(out, 0.0, 1.0)


def pack_signed_curvature(
    signed: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    strength: float = 0.5,
    flat: float = 0.5,
    scale_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Map signed curvature to packed gray: 0.5 flat, >0.5 convex, <0.5 concave."""
    out = np.full(signed.shape, flat, dtype=np.float32)
    write_mask = valid & np.isfinite(signed)
    if not np.any(write_mask):
        return out
    stats_mask = write_mask if scale_mask is None else (scale_mask & np.isfinite(signed))
    if not np.any(stats_mask):
        stats_mask = write_mask
    scale = percentile_scale(np.abs(signed), stats_mask, percentile=percentile)
    out[write_mask] = np.clip(flat + strength * signed[write_mask] / scale, 0.0, 1.0)
    return out

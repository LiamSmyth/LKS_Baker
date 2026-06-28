"""Blend base and detail AO maps into final grayscale AO."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.settings.ao_settings import CompositeBlendMode, CompositeSettings


def ao_composite(
    base_ao: np.ndarray,
    detail_ao: np.ndarray,
    valid: np.ndarray,
    settings: CompositeSettings,
) -> np.ndarray:
    """Combine macro base AO with detail AO using the configured blend mode."""
    active = np.clip(detail_ao, 0.0, 1.0).astype(np.float32)
    if settings.detail_contrast != 1.0:
        active = np.power(active, settings.detail_contrast)

    base = np.clip(base_ao, 0.0, 1.0).astype(np.float32)
    weight = float(np.clip(settings.detail_weight, 0.0, 1.0))
    mode = settings.blend_mode

    out = np.ones_like(base, dtype=np.float32)
    if mode is CompositeBlendMode.DETAIL_ONLY:
        out[valid] = active[valid]
    elif mode is CompositeBlendMode.MULTIPLY:
        out[valid] = base[valid] * active[valid]
    elif mode is CompositeBlendMode.MIN:
        out[valid] = np.minimum(base[valid], active[valid])
    else:
        lerped = np.where(weight >= 1.0, active, 1.0 + weight * (active - 1.0))
        out[valid] = base[valid] * lerped[valid]

    out[~valid] = 1.0
    return np.clip(out, 0.0, 1.0).astype(np.float32)

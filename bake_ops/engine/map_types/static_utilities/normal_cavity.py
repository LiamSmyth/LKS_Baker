"""Detail AO from tangent-space normal divergence (cavity approximation)."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.map_types.cavity.cavity_settings import CavitySettings
from lks_baker.bake_ops.engine.image_filters import island_gaussian_blur, percentile_scale
from lks_baker.bake_ops.engine.static_utilities.exclusive_channels import concave_from_signed
from lks_baker.bake_ops.engine.static_utilities.sampling import tangent_normal_divergence


def concavity_from_divergence(divergence: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Positive concavity from signed divergence (cavity = inward normal variation)."""
    return concave_from_signed(divergence, valid)


def normal_cavity_ao(
    tangent_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: CavitySettings,
) -> np.ndarray:
    """Map tangent normal to detail AO grayscale (1=open, 0=occluded).

    Input: internal ``InternalNormalSpace.TANGENT_OPENGL`` unit normals.
    """
    image_size = int(valid.shape[0])
    scale = max(1.0, image_size / 512.0)
    combined = np.zeros(tangent_normal.shape[:2], dtype=np.float32)

    radii = settings.multiscale.radii
    weights = settings.multiscale.weights
    for radius, weight in zip(radii, weights, strict=False):
        field = tangent_normal
        blur_radius = max(0.0, radius * scale)
        if blur_radius > 0.0:
            field = island_gaussian_blur(
                tangent_normal,
                island_id,
                blur_radius,
                sample_mask=valid,
            )
        div = tangent_normal_divergence(field, island_id, valid)
        combined += weight * concavity_from_divergence(div, valid)

    scale_val = percentile_scale(combined, valid, percentile=settings.pack.percentile)
    strength = settings.pack.strength * settings.intensity
    ao = np.ones(valid.shape, dtype=np.float32)
    ao[valid] = np.clip(1.0 - strength * combined[valid] / scale_val, 0.0, 1.0)
    ao[~valid] = 1.0
    return ao.astype(np.float32)

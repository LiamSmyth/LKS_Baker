"""Split signed curvature into exclusive convex / concave channels.

Signed fields use the bake convention: positive = convex, negative = concave.
Packed mid-gray curvature maps use 0.5 = flat, >0.5 convex, <0.5 concave.

Used by cavity and convexity derive paths, normal-map curvature helpers, and
test derive pipelines — not tied to a single map type.
"""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.image_filters import percentile_scale


def unpack_curvature_gray(curvature: np.ndarray) -> np.ndarray:
    """Convert packed mid-gray curvature (0.5 = flat) to signed -1..1."""
    return ((curvature - 0.5) * 2.0).astype(np.float32)


def convex_from_signed(signed: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Positive convexity magnitudes from a signed curvature field.

    Args:
        signed: HxW signed curvature (positive = convex).
        valid: HxW mask; invalid texels are zeroed in the output.

    Returns:
        HxW float32 convex channel in [0, inf); zero outside ``valid``.
    """
    convex = np.maximum(signed, 0.0)
    convex[~valid] = 0.0
    return convex.astype(np.float32)


def concave_from_signed(signed: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Positive concavity magnitudes from a signed curvature field.

    Args:
        signed: HxW signed curvature (negative = concave).
        valid: HxW mask; invalid texels are zeroed in the output.

    Returns:
        HxW float32 concave channel in [0, inf); zero outside ``valid``.
    """
    concave = np.maximum(-signed, 0.0)
    concave[~valid] = 0.0
    return concave.astype(np.float32)


def split_convexity_from_curvature_gray(curvature: np.ndarray) -> np.ndarray:
    """Derive convexity grayscale from packed mid-gray curvature.

    Args:
        curvature: HxW float32 in [0, 1] with 0.5 = flat.

    Returns:
        HxW float32 convex channel clipped to [0, 1].
    """
    signed = unpack_curvature_gray(curvature)
    return np.clip(np.maximum(0.0, signed), 0.0, 1.0).astype(np.float32)


def split_cavity_from_curvature_gray(curvature: np.ndarray) -> np.ndarray:
    """Derive cavity (concave) grayscale from packed mid-gray curvature.

    Args:
        curvature: HxW float32 in [0, 1] with 0.5 = flat.

    Returns:
        HxW float32 concave channel clipped to [0, 1].
    """
    signed = unpack_curvature_gray(curvature)
    return np.clip(np.maximum(0.0, -signed), 0.0, 1.0).astype(np.float32)


def unitize_convex_channel(
    signed: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    floor: float = 1e-6,
) -> np.ndarray:
    """Normalize signed convex magnitudes to [0, 1] via percentile scaling.

    Args:
        signed: HxW signed curvature field.
        valid: HxW mask for scale statistics and output write.

    Returns:
        HxW float32 convex channel in [0, 1]; zero outside ``valid``.
    """
    scale = percentile_scale(np.abs(signed), valid, percentile=percentile, floor=floor)
    convex = np.clip(signed / scale, 0.0, 1.0)
    convex[~valid] = 0.0
    return convex.astype(np.float32)


def unitize_concave_channel(
    signed: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    floor: float = 1e-6,
) -> np.ndarray:
    """Normalize signed concave magnitudes to [0, 1] via percentile scaling.

    Args:
        signed: HxW signed curvature field.
        valid: HxW mask for scale statistics and output write.

    Returns:
        HxW float32 concave channel in [0, 1]; zero outside ``valid``.
    """
    scale = percentile_scale(np.abs(signed), valid, percentile=percentile, floor=floor)
    concave = np.clip(-signed / scale, 0.0, 1.0)
    concave[~valid] = 0.0
    return concave.astype(np.float32)

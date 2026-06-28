"""Baker-matched convexity sign from object-space normals (no TBN required)."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.image_filters import island_gaussian_blur

GEOM_ALIGN_THRESHOLD = 0.85
FINEST_SIGN_EPS = 0.02
MAGNITUDE_GAIN = 2.5
MACRO_GEOM_RADIUS = 16
MULTISCALE_RADII = (1, 2, 4)


def _blur_radius_to_sigma(radius: float) -> float:
    return max(radius * 0.5, 0.6)


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(length, 1e-8)


def _angular_deviation(center: np.ndarray, blurred: np.ndarray) -> np.ndarray:
    dot = np.sum(center * blurred, axis=-1)
    dot = np.clip(dot, -1.0, 1.0)
    return np.arccos(dot)


def _snap_axis_geometry_normal(normal: np.ndarray) -> np.ndarray:
    """Piecewise-constant face normal (low-poly proxy) by dominant axis snap."""
    snapped = np.zeros_like(normal, dtype=np.float32)
    axis = np.argmax(np.abs(normal), axis=-1)
    for index in range(3):
        mask = axis == index
        if not np.any(mask):
            continue
        snapped[..., index][mask] = np.sign(normal[..., index][mask])
    return _normalize_vectors(snapped)


def _macro_geometry_normal(
    object_normal: np.ndarray,
    island_id: np.ndarray,
    *,
    radius: int = MACRO_GEOM_RADIUS,
) -> np.ndarray:
    """Low-frequency macro normal for convexity sign (SD geometry-normal proxy)."""
    return _normal_at_radius(object_normal, island_id, radius)


def _normal_at_radius(
    center: np.ndarray,
    island_id: np.ndarray,
    radius: int,
) -> np.ndarray:
    if radius <= 0:
        return _normalize_vectors(center)
    sigma = _blur_radius_to_sigma(float(radius))
    return _normalize_vectors(island_gaussian_blur(center, island_id, sigma))


def _convexity_field(center: np.ndarray, blurred: np.ndarray, geom: np.ndarray) -> np.ndarray:
    lap = blurred - center
    geom_align = np.abs(np.sum(center * geom, axis=-1))
    lap_proj = np.sum(lap * center, axis=-1)
    geom_delta = np.sum(center * geom, axis=-1) - np.sum(blurred * geom, axis=-1)
    grazing = geom_align < GEOM_ALIGN_THRESHOLD
    convexity = np.where(grazing, -lap_proj, geom_delta)
    return convexity.astype(np.float32)


def _signed_from_blur(
    center: np.ndarray,
    blurred: np.ndarray,
    geom: np.ndarray,
    *,
    magnitude_gain: float,
) -> np.ndarray:
    magnitude = np.minimum(1.0, _angular_deviation(center, blurred) * magnitude_gain)
    convexity = _convexity_field(center, blurred, geom)
    signed = np.zeros(center.shape[:2], dtype=np.float32)
    valid_mag = magnitude > 1e-12
    valid_sign = np.abs(convexity) > 1e-12
    mask = valid_mag & valid_sign
    signed[mask] = magnitude[mask] * np.where(convexity[mask] > 0.0, 1.0, -1.0)
    return signed


def _dominant_finest_sign(scale: np.ndarray, island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Majority vote on same-island neighbors when finest-scale sign is ambiguous."""
    pos = np.zeros(scale.shape, dtype=np.int32)
    neg = np.zeros(scale.shape, dtype=np.int32)
    radius = 1
    padded_scale = np.pad(scale, ((radius, radius), (radius, radius)), mode="constant", constant_values=0.0)
    padded_island = np.pad(island_id, ((radius, radius), (radius, radius)), mode="edge")
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            shifted = padded_scale[
                radius + dy : radius + dy + scale.shape[0],
                radius + dx : radius + dx + scale.shape[1],
            ]
            same_island = island_id == padded_island[
                radius + dy : radius + dy + scale.shape[0],
                radius + dx : radius + dx + scale.shape[1],
            ]
            use = valid & same_island & (shifted != 0.0)
            pos[use & (shifted > 0.0)] += 1
            neg[use & (shifted < 0.0)] += 1
    out = np.ones(scale.shape, dtype=np.float32)
    out[valid & (neg > pos)] = -1.0
    return out


def multiscale_magnitude_from_object_normal(
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    *,
    radii: tuple[int, ...] = MULTISCALE_RADII,
    magnitude_gain: float = MAGNITUDE_GAIN,
) -> np.ndarray:
    """Unsigned max-pooled angular deviation across blur radii."""
    center = object_normal
    pooled = np.zeros(center.shape[:2], dtype=np.float32)
    for radius in radii:
        blurred = _normal_at_radius(center, island_id, radius)
        magnitude = np.minimum(1.0, _angular_deviation(center, blurred) * magnitude_gain)
        pooled = np.maximum(pooled, magnitude)
    pooled[~valid] = 0.0
    return pooled


def signed_from_magnitude_and_convexity(
    magnitude: np.ndarray,
    convexity: np.ndarray,
    valid: np.ndarray,
    *,
    eps: float = 1e-6,
) -> np.ndarray:
    """Signed from magnitude and convexity."""
    signed = np.zeros_like(magnitude, dtype=np.float32)
    mask = valid & (magnitude > eps) & (np.abs(convexity) > eps)
    signed[mask] = magnitude[mask] * np.where(convexity[mask] > 0.0, 1.0, -1.0)
    return signed


def multiscale_signed_from_object_normal(
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    *,
    radii: tuple[int, ...] = MULTISCALE_RADII,
    magnitude_gain: float = MAGNITUDE_GAIN,
) -> np.ndarray:
    """Max-pool multiscale magnitudes; sign locked to finest blur scale (radius 1)."""
    center = object_normal
    geom = _macro_geometry_normal(center, island_id)
    combined: np.ndarray | None = None
    finest: np.ndarray | None = None
    finest_sign: np.ndarray | None = None

    for radius in radii:
        blurred = _normal_at_radius(center, island_id, radius)
        scale = _signed_from_blur(center, blurred, geom, magnitude_gain=magnitude_gain)

        if radius == radii[0]:
            finest = scale
            combined = scale.copy()
            finest_sign = np.ones_like(scale, dtype=np.float32)
            confident = (np.abs(scale) >= FINEST_SIGN_EPS) & valid
            finest_sign[confident & valid] = np.where(scale[confident & valid] > 0.0, 1.0, -1.0)
            uncertain = valid & (~confident)
            if np.any(uncertain):
                dom = _dominant_finest_sign(scale, island_id, valid)
                finest_sign[uncertain] = dom[uncertain]
            continue

        assert combined is not None and finest is not None and finest_sign is not None
        same_sign = ((scale > 0.0) == (finest_sign > 0.0))
        weak_finest_neg = (scale < 0.0) & (finest < 0.0) & (np.abs(finest) < FINEST_SIGN_EPS)
        replace = valid & (scale != 0.0) & same_sign & (~weak_finest_neg)
        replace &= np.abs(scale) > np.abs(combined)
        combined[replace] = scale[replace]

    assert combined is not None
    combined[~valid] = 0.0
    return combined

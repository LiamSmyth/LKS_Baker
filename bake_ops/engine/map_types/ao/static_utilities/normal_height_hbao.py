"""Object-normal height integrate → texture HBAO detail AO pipeline."""
from __future__ import annotations

import math

import numpy as np

from lks_baker.bake_ops.engine.settings.ao_settings import AoSettings, TextureHbaoSettings
from lks_baker.bake_ops.engine.static_utilities.coords import internal_v_neighbor_indices
from lks_baker.bake_ops.engine.static_utilities.sampling import island_shift

from .height_integrate import integrate_height_from_object_normal


def _texture_hbao(
    height: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: TextureHbaoSettings,
) -> np.ndarray:
    """Island-safe horizon AO from a height map."""
    pv_plus, _ = internal_v_neighbor_indices()
    directions = max(4, int(settings.directions))
    steps = max(1, int(settings.steps_per_direction))
    radius = float(settings.ao_radius_texels)
    bias = float(settings.bias)
    strength = float(settings.strength)

    h, w = valid.shape[:2]
    ao_sum = np.zeros((h, w), dtype=np.float32)

    for d_idx in range(directions):
        theta = (2.0 * math.pi * d_idx) / float(directions)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        horizon = np.zeros((h, w), dtype=np.float32)

        for step in range(1, steps + 1):
            t = float(step) / float(steps)
            dx = int(round(cos_t * radius * t))
            dy = int(round(sin_t * radius * t * (1.0 if pv_plus < 0 else -1.0)))
            if dx == 0 and dy == 0:
                dx = 1 if cos_t >= 0 else -1

            h_off = island_shift(height, island_id, dy=dy, dx=dx)
            same = island_shift(
                np.ones(valid.shape, dtype=np.float32),
                island_id,
                dy=dy,
                dx=dx,
            ) > 0.5
            delta = h_off - height
            dist = math.sqrt(float(dx * dx + dy * dy))
            slope = delta / max(dist, 1.0) - bias
            sample = np.maximum(slope, 0.0)
            sample[~same | ~valid] = 0.0
            horizon = np.maximum(horizon, sample.astype(np.float32))

        ao_sum += horizon

    ao = 1.0 - strength * (ao_sum / float(directions))
    ao = np.clip(ao, 0.0, 1.0).astype(np.float32)
    ao[~valid] = 1.0
    return ao


def normal_height_hbao(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: AoSettings,
) -> np.ndarray:
    """Full detail AO pipeline: OSNM → Poisson height → texture HBAO."""
    height = integrate_height_from_object_normal(
        object_normal,
        position,
        island_id,
        valid,
        settings.height_integrate,
    )
    return _texture_hbao(height, island_id, valid, settings.texture_hbao)


def height_map_hbao(
    height: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: AoSettings,
) -> np.ndarray:
    """Direct height-map HBAO (skip normal integration)."""
    return _texture_hbao(height, island_id, valid, settings.texture_hbao)

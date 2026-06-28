"""UV-atlas horizon-based AO using world position + object normal atlases."""
from __future__ import annotations

import math

import numpy as np

from lks_baker.bake_ops.engine.settings.ao_settings import AtlasHbaoSettings
from lks_baker.bake_ops.engine.static_utilities.coords import internal_v_neighbor_indices
from lks_baker.bake_ops.engine.static_utilities.sampling import island_shift


def _safe_normalize(v: np.ndarray, axis: int = -1, eps: float = 1e-6) -> np.ndarray:
    length = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.maximum(length, eps)


def _world_metric(position: np.ndarray, island_id: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Estimate |dP/du| and |dP/dv| in world units per texel."""
    p_l = island_shift(position, island_id, dx=-1)
    p_r = island_shift(position, island_id, dx=1)
    pv_plus, pv_minus = internal_v_neighbor_indices()
    p_vp = island_shift(position, island_id, dy=pv_plus)
    p_vm = island_shift(position, island_id, dy=pv_minus)
    du = 0.5 * np.linalg.norm(p_r - p_l, axis=-1)
    dv = 0.5 * np.linalg.norm(p_vp - p_vm, axis=-1)
    return du.astype(np.float32), dv.astype(np.float32)


def atlas_hbao(
    position: np.ndarray,
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: AtlasHbaoSettings,
) -> np.ndarray:
    """Horizon AO in UV atlas space with world-aware stepping."""
    pv_plus, _ = internal_v_neighbor_indices()
    normal = _safe_normalize(object_normal)
    du_world, dv_world = _world_metric(position, island_id)
    du_world = np.maximum(du_world, 1e-6)
    dv_world = np.maximum(dv_world, 1e-6)

    height, width = valid.shape[:2]
    ao_sum = np.zeros((height, width), dtype=np.float32)
    directions = max(4, int(settings.directions))
    steps = max(1, int(settings.steps_per_direction))
    radius = float(settings.radius_world)
    bias = float(settings.bias)
    strength = float(settings.strength)

    for d_idx in range(directions):
        theta = (2.0 * math.pi * d_idx) / float(directions)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        horizon = np.zeros((height, width), dtype=np.float32)

        for step in range(1, steps + 1):
            world_dist = radius * (float(step) / float(steps))
            dx = int(round(cos_t * world_dist / du_world.mean()))
            dy = int(round(sin_t * world_dist / dv_world.mean() * (1.0 if pv_plus < 0 else -1.0)))
            if dx == 0 and dy == 0:
                dx = 1 if cos_t >= 0 else -1

            p_off = island_shift(position, island_id, dy=dy, dx=dx)
            n_off = island_shift(normal, island_id, dy=dy, dx=dx)
            same = island_shift(
                np.ones(valid.shape, dtype=np.float32),
                island_id,
                dy=dy,
                dx=dx,
            ) > 0.5

            vec = p_off - position
            dist = np.linalg.norm(vec, axis=-1)
            dir_n = _safe_normalize(vec)
            facing = np.sum(normal * dir_n, axis=-1) - bias
            facing = np.maximum(facing, 0.0)
            attenuation = np.clip(1.0 - dist / max(radius, 1e-6), 0.0, 1.0)
            sample = facing * attenuation
            sample[~same | ~valid | (dist > radius)] = 0.0
            horizon = np.maximum(horizon, sample.astype(np.float32))

        ao_sum += horizon

    ao = 1.0 - strength * (ao_sum / float(directions))
    ao = np.clip(ao, 0.0, 1.0).astype(np.float32)
    ao[~valid] = 1.0
    return ao

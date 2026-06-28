"""Object-space bent normal from position + object-normal atlases."""
from __future__ import annotations

import math

import numpy as np

from lks_baker.bake_ops.engine.settings.bent_normal_settings import (
    BentNormalObjectSettings,
)
from lks_baker.bake_ops.engine.static_utilities.coords import internal_v_neighbor_indices
from lks_baker.bake_ops.engine.static_utilities.sampling import island_shift


def _safe_normalize(v: np.ndarray, axis: int = -1, eps: float = 1e-6) -> np.ndarray:
    length = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.maximum(length, eps)


def _vector_atlas_xyz(field: np.ndarray) -> np.ndarray:
    """Return ``H×W×3`` float32 from RGB or RGBA atlas vector fields."""
    arr = field.astype(np.float32, copy=False)
    if arr.ndim < 3 or arr.shape[-1] < 3:
        raise ValueError(f'expected H×W×3 vector atlas, got shape {arr.shape!r}')
    return arr[..., :3] if arr.shape[-1] != 3 else arr


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


def build_local_hemisphere_directions(count: int, spread_angle_deg: float) -> np.ndarray:
    """Return ``(count, 3)`` unit vectors on +Z hemisphere before TBN rotation."""
    directions = max(4, int(count))
    spread = math.radians(float(spread_angle_deg))
    cos_cap = math.cos(min(spread, math.pi * 0.5))
    golden = math.pi * (3.0 - math.sqrt(5.0))
    out = np.zeros((directions, 3), dtype=np.float32)
    for idx in range(directions):
        t = (float(idx) + 0.5) / float(directions)
        z = (1.0 - t) + t * cos_cap
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        theta = golden * float(idx)
        out[idx, 0] = math.cos(theta) * radius
        out[idx, 1] = math.sin(theta) * radius
        out[idx, 2] = z
    return _safe_normalize(out, axis=-1)


def surface_tangent_frames(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build per-texel orthonormal T/B/N frames from atlas position gradients."""
    object_normal = _vector_atlas_xyz(object_normal)
    position = _vector_atlas_xyz(position)
    normal = _safe_normalize(object_normal)
    p_l = island_shift(position, island_id, dx=-1)
    p_r = island_shift(position, island_id, dx=1)
    tangent = _safe_normalize(p_r - p_l)
    bitangent = _safe_normalize(np.cross(normal, tangent, axis=-1))
    tangent = _safe_normalize(np.cross(bitangent, normal, axis=-1))
    return tangent.astype(np.float32), bitangent.astype(np.float32), normal.astype(np.float32)


def world_direction_from_local(
    local_dir: np.ndarray,
    tangent: np.ndarray,
    bitangent: np.ndarray,
    normal: np.ndarray,
) -> np.ndarray:
    """Rotate one local hemisphere direction to world/object space per texel."""
    return (
        local_dir[0] * tangent
        + local_dir[1] * bitangent
        + local_dir[2] * normal
    ).astype(np.float32)


def direction_occluded_for_local_dir(
    position: np.ndarray,
    normal: np.ndarray,
    sample_dir: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: BentNormalObjectSettings,
    du_world: np.ndarray,
    dv_world: np.ndarray,
    *,
    uv_theta: float,
) -> np.ndarray:
    """Return ``HxW`` bool — True when the hemisphere sample is atlas-occluded."""
    pv_plus, _ = internal_v_neighbor_indices()
    steps = max(1, int(settings.steps_per_direction))
    radius = float(settings.radius_world)
    bias = float(settings.bias)

    du_mean = max(float(np.mean(du_world[valid])) if np.any(valid) else 1.0, 1e-6)
    dv_mean = max(float(np.mean(dv_world[valid])) if np.any(valid) else 1.0, 1e-6)
    cos_t = math.cos(uv_theta)
    sin_t = math.sin(uv_theta)

    facing = np.sum(sample_dir * normal, axis=-1) > 1e-4
    occluded = np.zeros(valid.shape[:2], dtype=bool)

    for step in range(1, steps + 1):
        world_dist = radius * (float(step) / float(steps))
        dx = int(round(cos_t * world_dist / du_mean))
        dy = int(round(sin_t * world_dist / dv_mean * (1.0 if pv_plus < 0 else -1.0)))
        if dx == 0 and dy == 0:
            dx = 1 if cos_t >= 0 else -1

        p_off = island_shift(position, island_id, dy=dy, dx=dx)
        same = island_shift(
            np.ones(valid.shape, dtype=np.float32),
            island_id,
            dy=dy,
            dx=dx,
        ) > 0.5

        vec = p_off - position
        dist = np.linalg.norm(vec, axis=-1)
        dir_n = _safe_normalize(vec)
        align = np.sum(dir_n * sample_dir, axis=-1)
        block = (
            same
            & valid
            & facing
            & (dist <= radius)
            & (dist > 1e-6)
            & (align > (1.0 - bias))
        )
        occluded |= block

    return occluded


def pack_bent_normal_rgb(bent: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Encode unit ``HxWx3`` directions as ``HxWx4`` RGBA (0.5 + 0.5 * n)."""
    rgba = np.zeros((*bent.shape[:2], 4), dtype=np.float32)
    rgb = bent * 0.5 + 0.5
    rgba[..., :3] = np.clip(rgb, 0.0, 1.0)
    rgba[..., 3] = 1.0
    rgba[~valid] = 0.0
    return rgba


def bent_normal_object(
    position: np.ndarray,
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: BentNormalObjectSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute object-space bent normals and packed RGBA.

    Inputs are post-ingest world/object-space ``position`` and ``object_normal`` atlases
    (OpenGL PNG row order, float32 unit normals).

    Returns:
        ``(bent_unit HxWx3, rgba HxWx4)``.
    """
    object_normal = _vector_atlas_xyz(object_normal)
    position = _vector_atlas_xyz(position)
    tangent, bitangent, normal = surface_tangent_frames(object_normal, position, island_id)
    du_world, dv_world = _world_metric(position, island_id)
    local_dirs = build_local_hemisphere_directions(settings.directions, settings.spread_angle_deg)

    height, width = valid.shape[:2]
    sum_dir = np.zeros((height, width, 3), dtype=np.float32)
    weight = np.zeros((height, width), dtype=np.float32)

    for local_dir in local_dirs:
        sample_dir = world_direction_from_local(local_dir, tangent, bitangent, normal)
        sample_dir = _safe_normalize(sample_dir)
        uv_theta = math.atan2(float(local_dir[1]), float(local_dir[0]))
        blocked = direction_occluded_for_local_dir(
            position,
            normal,
            sample_dir,
            island_id,
            valid,
            settings,
            du_world,
            dv_world,
            uv_theta=uv_theta,
        )
        unoccluded = valid & ~blocked & (np.sum(sample_dir * normal, axis=-1) > 0.0)
        sum_dir += np.where(unoccluded[..., None], sample_dir, 0.0)
        weight += unoccluded.astype(np.float32)

    fallback = normal
    bent = np.where(weight[..., None] > 0.0, sum_dir / np.maximum(weight[..., None], 1e-6), fallback)
    bent = _safe_normalize(bent)
    bent[~valid] = 0.0
    rgba = pack_bent_normal_rgb(bent, valid)
    return bent.astype(np.float32), rgba

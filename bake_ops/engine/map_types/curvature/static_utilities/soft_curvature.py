"""Multi-scale soft curvature from low-poly position shell + object-space normals."""
from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from lks_baker.bake_ops.engine.settings.curvature_settings import (
    PackSettings,
    SoftCurvatureSettings,
)
from lks_baker.bake_ops.engine.static_utilities.low_surface_atlas import (
    rasterize_low_surface,
    rasterize_uv_coverage,
)
from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData
from lks_baker.bake_ops.engine.static_utilities.mesh_uv_charts import (
    island_id_from_mesh_charts,
)
from lks_baker.bake_ops.engine.static_utilities.normalize import (
    pack_signed_curvature,
)
from lks_baker.bake_ops.engine.static_utilities.runtime_log import timed_step
from lks_baker.bake_ops.engine.map_types.curvature.static_utilities.soft_curvature_debug import (
    soft_curvature_debug,
    soft_curvature_timebox,
)


def mip_chain_radii(height: int, width: int) -> tuple[int, ...]:
    """Pixel radii covering the full mip chain up to half the shorter map edge."""
    limit = max(1, min(height, width) // 2)
    radii: list[int] = []
    radius = 1
    while radius <= limit:
        radii.append(radius)
        radius <<= 1
    return tuple(radii) if radii else (1,)


def circle_offsets(radius: int, samples: int | None = None) -> list[tuple[int, int]]:
    """Integer (dy, dx) offsets on a ring; deduplicated."""
    if radius <= 0:
        return []
    if samples is None:
        samples = max(8, int(math.ceil(2.0 * math.pi * radius)))
    offsets: list[tuple[int, int]] = []
    for index in range(samples):
        angle = 2.0 * math.pi * float(index) / float(samples)
        dx = int(round(math.cos(angle) * radius))
        dy = int(round(math.sin(angle) * radius))
        if dx == 0 and dy == 0:
            continue
        offsets.append((dy, dx))
    return list(dict.fromkeys(offsets))


def _safe_normalize_vectors(v: np.ndarray, *, axis: int = -1, eps: float = 1e-8) -> np.ndarray:
    length = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.maximum(length, eps)


def _normalize_scale_curvature(
    scale_curvature: np.ndarray,
    mask: np.ndarray,
    percentile: float,
) -> np.ndarray:
    samples = scale_curvature[mask]
    samples = samples[np.isfinite(samples)]
    if samples.size == 0:
        return np.zeros_like(scale_curvature, dtype=np.float32)
    scale = float(np.percentile(np.abs(samples), percentile))
    scale = max(scale, 1e-8)
    out = np.zeros_like(scale_curvature, dtype=np.float32)
    out[mask] = scale_curvature[mask] / scale
    return out


def _curvature_at_radius(
    position: np.ndarray,
    normal: np.ndarray,
    island_id: np.ndarray,
    coverage: np.ndarray,
    radius: int,
    *,
    samples_per_radius: int | None,
) -> np.ndarray:
    """Island-aware finite-difference curvature averaged over a ring."""
    height, width = coverage.shape
    offsets = circle_offsets(radius, samples_per_radius)
    soft_curvature_debug(
        f"radius={radius}: {len(offsets)} ring offsets on {width}x{height}",
    )
    scale_sum = np.zeros((height, width), dtype=np.float32)
    sample_count = np.zeros((height, width), dtype=np.float32)
    if not offsets:
        return scale_sum

    for index, (dy, dx) in enumerate(offsets):
        if index == 0 or (index + 1) % 512 == 0 or index + 1 == len(offsets):
            soft_curvature_debug(
                f"radius={radius}: offset {index + 1}/{len(offsets)} (dy={dy}, dx={dx})",
            )
        y_src = slice(max(0, -dy), height - max(0, dy))
        y_dst = slice(max(0, dy), height - max(0, -dy))
        x_src = slice(max(0, -dx), width - max(0, dx))
        x_dst = slice(max(0, dx), width - max(0, -dx))

        island_dst = island_id[y_dst, x_dst]
        same = island_dst == island_id[y_src, x_src]
        cov = coverage[y_dst, x_dst] & coverage[y_src, x_src] & same

        pos_dst = position[y_dst, x_dst]
        pos_src = position[y_src, x_src]
        nrm_dst = normal[y_dst, x_dst]
        nrm_src = normal[y_src, x_src]
        d_pos = pos_src - pos_dst
        d_nrm = nrm_src - nrm_dst
        dist2 = np.sum(d_pos * d_pos, axis=-1)
        cov &= dist2 > 1e-20
        if not np.any(cov):
            continue

        curvature = -np.sum(d_nrm * d_pos, axis=-1) / np.maximum(dist2, 1e-20)
        scale_sum[y_dst, x_dst][cov] += curvature[cov]
        sample_count[y_dst, x_dst][cov] += 1.0

    scale_valid = sample_count > 0.0
    scale_curvature = np.zeros((height, width), dtype=np.float32)
    scale_curvature[scale_valid] = scale_sum[scale_valid] / sample_count[scale_valid]
    soft_curvature_debug(f"radius={radius}: done")
    return scale_curvature


def _prepare_fields(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    coverage: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Zero background fields and detach island labels outside coverage."""
    normal = _safe_normalize_vectors(object_normal.astype(np.float32))
    position_field = position.astype(np.float32)
    work_islands = np.where(coverage, island_id, -1).astype(np.int32)
    normal[~coverage] = 0.0
    position_field[~coverage] = 0.0
    return normal, position_field, work_islands


def prepare_soft_curvature_shell(
    mesh: MeshData,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Prepass: UV-rasterize low-poly position shell, coverage, and chart island ids."""
    soft_curvature_debug(f"prepare_shell: rasterize low surface {image_size}x{image_size}")
    with timed_step("soft_curvature rasterize_low_surface"):
        position, _, coverage = rasterize_low_surface(mesh, image_size)
    soft_curvature_debug("prepare_shell: island_id_from_mesh_charts")
    with timed_step("soft_curvature island_id_from_mesh_charts"):
        island_id = island_id_from_mesh_charts(mesh, image_size, coverage)
    soft_curvature_debug(
        f"prepare_shell: done valid={int(coverage.sum())} verts={len(mesh.vertices)} tris={len(mesh.faces)}",
    )
    return position.astype(np.float32), coverage, island_id


def signed_soft_curvature(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    coverage: np.ndarray,
    settings: SoftCurvatureSettings,
    *,
    curvature_at_radius: Callable[[int], np.ndarray] | None = None,
) -> np.ndarray:
    """Integrate multi-scale curvature over mip-chain radii.

    Inputs (internal, post-ingest):
        object_normal: H×W×3 float32 world/object unit normals (OpenGL PNG row order).
        position: H×W×3 float32 object/world positions from the low-poly UV shell prepass.
        coverage: H×W bool texels inside the low-poly UV raster (authoritative shell mask).
    """
    height, width = coverage.shape
    radii = settings.radii if settings.radii is not None else mip_chain_radii(height, width)
    if not radii:
        radii = (1,)

    if settings.scale_weights is None:
        weights = np.ones(len(radii), dtype=np.float32)
    else:
        weights = np.asarray(settings.scale_weights, dtype=np.float32)
        if len(weights) != len(radii):
            raise ValueError("scale_weights must match radii length")

    normal, position_field, work_islands = _prepare_fields(
        object_normal,
        position,
        island_id,
        coverage,
    )
    soft_curvature_debug(
        f"signed_soft_curvature: {width}x{height} radii={list(radii)} normalize_each={settings.normalize_each_scale}",
    )

    accumulated = np.zeros((height, width), dtype=np.float32)
    weight_sum = 0.0

    for radius_index, (radius, weight) in enumerate(zip(radii, weights)):
        if weight <= 0.0:
            continue
        soft_curvature_debug(f"mip {radius_index + 1}/{len(radii)}: radius={radius} weight={weight}")
        if curvature_at_radius is not None:
            with timed_step(f"soft_curvature gpu/cpu radius={radius}"):
                scale_curvature = curvature_at_radius(int(radius))
        else:
            with timed_step(f"soft_curvature cpu radius={radius}"):
                scale_curvature = _curvature_at_radius(
                    position_field,
                    normal,
                    work_islands,
                    coverage,
                    int(radius),
                    samples_per_radius=settings.samples_per_radius,
                )
        if settings.normalize_each_scale:
            with timed_step(f"soft_curvature normalize radius={radius}"):
                scale_curvature = _normalize_scale_curvature(
                    scale_curvature,
                    coverage,
                    settings.normalize_percentile,
                )
        accumulated[coverage] += scale_curvature[coverage] * float(weight)
        weight_sum += float(weight)
        soft_curvature_debug(f"mip {radius_index + 1}/{len(radii)}: radius={radius} integrated")

    signed = np.zeros((height, width), dtype=np.float32)
    if weight_sum > 0.0:
        signed[coverage] = accumulated[coverage] / weight_sum

    if settings.convex_is_white:
        signed = -signed
    signed[~coverage] = 0.0
    return signed.astype(np.float32)


def pack_soft_curvature(
    signed: np.ndarray,
    coverage: np.ndarray,
    pack: PackSettings,
) -> np.ndarray:
    """Percentile-pack signed curvature to grayscale."""
    return pack_signed_curvature(
        signed,
        coverage,
        percentile=pack.percentile,
        strength=pack.strength,
        flat=pack.flat,
    )


def bake_soft_curvature(
    object_normal: np.ndarray,
    mesh: MeshData,
    settings: SoftCurvatureSettings,
    *,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(packed_gray, signed, coverage)`` at float32 internal precision."""
    with soft_curvature_timebox(f"bake_soft_curvature {image_size}x{image_size}"):
        soft_curvature_debug(f"bake_soft_curvature: image_size={image_size}")
        position, coverage, island_id = prepare_soft_curvature_shell(mesh, image_size)
        with timed_step("soft_curvature signed_soft_curvature"):
            signed = signed_soft_curvature(
                object_normal,
                position,
                island_id,
                coverage,
                settings,
            )
        with timed_step("soft_curvature pack"):
            packed = pack_soft_curvature(signed, coverage, settings.pack)
        soft_curvature_debug("bake_soft_curvature: done")
    return packed, signed, coverage

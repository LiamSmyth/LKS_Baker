"""Static config for the ``soft_curvature`` bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lks_baker.bake_ops.engine.map_types.curvature.static_utilities.soft_curvature import (
    mip_chain_radii,
)
from lks_baker.bake_ops.engine.settings.curvature_settings import (
    Backend,
    CurvatureSettings,
    PackSettings,
    SoftCurvatureSettings,
)

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class SoftCurvatureConfig:
    """RNA-backed soft curvature tuning."""

    normalize_each_scale: bool = True
    normalize_percentile: float = 95.0
    convex_is_white: bool = True
    samples_per_radius: int = 0
    max_radius: int = 0
    pack_strength: float = 0.5
    pack_percentile: float = 95.0
    pack_flat: float = 0.5
    device: str = 'AUTO'


def config_from_entry(
    entry: LKS_PG_BakeMapEntry,
    *,
    image_size: int | None = None,
) -> SoftCurvatureConfig:
    """Build config dataclass from map-entry RNA."""
    soft = entry.lks_curvature_soft
    return SoftCurvatureConfig(
        normalize_each_scale=bool(soft.normalize_each_scale),
        normalize_percentile=float(soft.normalize_percentile),
        convex_is_white=bool(soft.convex_is_white),
        samples_per_radius=int(soft.samples_per_radius),
        max_radius=int(soft.max_radius),
        pack_strength=float(soft.pack_strength),
        pack_percentile=float(soft.pack_percentile),
        pack_flat=float(soft.pack_flat),
        device=str(entry.lks_curvature_device),
    )


def soft_curvature_settings_from_config(
    config: SoftCurvatureConfig,
    *,
    image_size: int | None = None,
) -> SoftCurvatureSettings:
    """Convert ``SoftCurvatureConfig`` to engine ``SoftCurvatureSettings``."""
    samples = config.samples_per_radius
    max_radius = config.max_radius

    radii: tuple[int, ...] | None = None
    if max_radius > 0:
        size = image_size if image_size is not None else max_radius
        radii = tuple(r for r in mip_chain_radii(size, size) if r <= max_radius)

    return SoftCurvatureSettings(
        radii=radii,
        samples_per_radius=None if samples <= 0 else samples,
        normalize_each_scale=config.normalize_each_scale,
        normalize_percentile=config.normalize_percentile,
        convex_is_white=config.convex_is_white,
        pack=PackSettings(
            percentile=config.pack_percentile,
            strength=config.pack_strength,
            flat=config.pack_flat,
        ),
    )


def build_curvature_settings(
    entry: LKS_PG_BakeMapEntry,
    *,
    backend: str = 'cpu',
    image_size: int | None = None,
    tangent_strength: float = 0.5,
    world_strength: float = 0.1,
) -> CurvatureSettings:
    """Merge soft-curvature RNA into ``CurvatureSettings`` for execution."""
    settings = CurvatureSettings()
    backend_upper = backend.upper()
    if backend_upper == 'AUTO':
        settings.backend = Backend.AUTO
    elif backend_upper == 'GPU':
        settings.backend = Backend.GPU
    else:
        settings.backend = Backend.CPU

    settings.tangent.pack.strength = tangent_strength
    settings.world.pack.strength = world_strength

    config = config_from_entry(entry, image_size=image_size)
    settings.soft = soft_curvature_settings_from_config(config, image_size=image_size)
    return settings

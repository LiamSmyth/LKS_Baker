"""Static config for the ``emit_raster`` specular bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry

DEFAULT_EMIT_RASTER_CAGE_EXTRUSION = 0.01
DEFAULT_EMIT_RASTER_MAX_RAY_DISTANCE = 0.0


@dataclass
class EmitRasterConfig:
    """H→L emit raster raycast tuning (project cage props override defaults)."""

    cage_extrusion: float = DEFAULT_EMIT_RASTER_CAGE_EXTRUSION
    max_ray_distance: float = DEFAULT_EMIT_RASTER_MAX_RAY_DISTANCE


def config_from_entry(entry: LKS_PG_BakeMapEntry, **kwargs: Any) -> EmitRasterConfig:
    """Build config from map-entry RNA and optional project bake settings."""
    project = kwargs.get("project")
    cage = DEFAULT_EMIT_RASTER_CAGE_EXTRUSION
    max_ray = DEFAULT_EMIT_RASTER_MAX_RAY_DISTANCE
    if project is not None:
        cage = float(getattr(project, "cage_extrusion", cage))
        max_ray = float(getattr(project, "max_ray_distance", max_ray))
    _ = entry
    return EmitRasterConfig(cage_extrusion=cage, max_ray_distance=max_ray)

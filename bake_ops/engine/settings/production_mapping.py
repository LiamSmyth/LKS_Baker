"""Map LKS production constants and map-entry RNA to bake_engine CurvatureSettings."""
from __future__ import annotations

from .curvature_map_entry import (
    curvature_settings_from_map_entry,
    legacy_curvature_derive_kwargs,
    soft_curvature_settings_from_entry,
)
from .curvature_settings import Backend, CurvatureSettings


def curvature_settings_from_constants(
    *,
    backend: str = "cpu",
    tangent_strength: float = 0.5,
    world_strength: float = 0.1,
    method_id: str | None = None,
    map_entry=None,
    image_size: int | None = None,
) -> CurvatureSettings:
    """Build ``CurvatureSettings`` from globals and optional per-map RNA."""
    if map_entry is not None:
        return curvature_settings_from_map_entry(
            map_entry,
            backend=backend,
            method_id=method_id,
            image_size=image_size,
            tangent_strength=tangent_strength,
            world_strength=world_strength,
        )

    settings = CurvatureSettings()
    if backend.upper() == "AUTO":
        settings.backend = Backend.AUTO
    elif backend.upper() == "GPU":
        settings.backend = Backend.GPU
    else:
        settings.backend = Backend.CPU
    settings.tangent.pack.strength = tangent_strength
    settings.world.pack.strength = world_strength
    if method_id == "soft_curvature":
        settings.soft.pack.strength = 0.5
    return settings


__all__ = (
    "CurvatureSettings",
    "curvature_settings_from_constants",
    "curvature_settings_from_map_entry",
    "legacy_curvature_derive_kwargs",
    "soft_curvature_settings_from_entry",
)

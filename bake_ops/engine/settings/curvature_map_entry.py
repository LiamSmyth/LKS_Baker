"""Map ``LKS_PG_BakeMapEntry`` RNA to bake-engine ``CurvatureSettings``."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lks_baker.bake_ops.engine.map_types.curvature.soft_curvature_cfg import (
    build_curvature_settings,
    config_from_entry as soft_curvature_config_from_entry,
    soft_curvature_settings_from_config,
)
from lks_baker.bake_ops.engine.settings.curvature_settings import (
    Backend,
    CurvatureSettings,
    SoftCurvatureSettings,
)
from lks_baker.shared_utilities.lks_constants import (
    BAKE_CURVATURE_CONVEXITY_SIGN,
    BAKE_CURVATURE_MAGNITUDE_GAIN,
    BAKE_CURVATURE_RELATIVE_TO_BBOX,
    BAKE_CURVATURE_SAMPLING_RADIUS,
)

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


def _get(entry: Any, name: str, default: object) -> object:
    return getattr(entry, name, default)


def soft_curvature_settings_from_entry(
    entry: LKS_PG_BakeMapEntry,
    *,
    image_size: int | None = None,
) -> SoftCurvatureSettings:
    """Build ``SoftCurvatureSettings`` from map-entry RNA."""
    config = soft_curvature_config_from_entry(entry, image_size=image_size)
    return soft_curvature_settings_from_config(config, image_size=image_size)


def curvature_settings_from_map_entry(
    entry: LKS_PG_BakeMapEntry | None,
    *,
    backend: str = "cpu",
    method_id: str | None = None,
    image_size: int | None = None,
    tangent_strength: float = 0.5,
    world_strength: float = 0.1,
) -> CurvatureSettings:
    """Merge production map-entry overrides into ``CurvatureSettings``."""
    settings = CurvatureSettings()
    backend_upper = backend.upper()
    if backend_upper == "AUTO":
        settings.backend = Backend.AUTO
    elif backend_upper == "GPU":
        settings.backend = Backend.GPU
    else:
        settings.backend = Backend.CPU

    settings.tangent.pack.strength = tangent_strength
    settings.world.pack.strength = world_strength

    if entry is None:
        if method_id == "soft_curvature":
            settings.soft.pack.strength = 0.5
        return settings

    legacy = entry.lks_curvature_legacy
    settings.sd.magnitude_gain = float(legacy.magnitude_gain)
    settings.sd.convexity_sign = float(legacy.convexity_sign)

    ui_method = _get(entry, "lks_curvature_method", "SD")
    if ui_method == "SOFT_CURVATURE" or method_id == "soft_curvature":
        return build_curvature_settings(
            entry,
            backend=backend,
            image_size=image_size,
            tangent_strength=tangent_strength,
            world_strength=world_strength,
        )

    return settings


def legacy_curvature_derive_kwargs(entry: LKS_PG_BakeMapEntry | None) -> dict[str, object]:
    """Keyword args for ``derive_curvature_from_normal`` from map-entry RNA."""
    if entry is None:
        return {
            "magnitude_gain": BAKE_CURVATURE_MAGNITUDE_GAIN,
            "sampling_radius": BAKE_CURVATURE_SAMPLING_RADIUS,
            "relative_to_bbox": BAKE_CURVATURE_RELATIVE_TO_BBOX,
        }
    legacy = entry.lks_curvature_legacy
    return {
        "magnitude_gain": float(legacy.magnitude_gain),
        "sampling_radius": float(legacy.sampling_radius),
        "relative_to_bbox": bool(legacy.relative_to_bbox),
    }

"""Static config for the ``bent_normal_object`` bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lks_baker.bake_ops.engine.settings.bent_normal_settings import (
    BentNormalObjectSettings,
)

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class BentNormalObjectConfig:
    """RNA-backed bent-normal tuning."""

    directions: int = 12
    steps_per_direction: int = 8
    radius_world: float = 0.35
    spread_angle_deg: float = 90.0
    bias: float = 0.02


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> BentNormalObjectConfig:
    """Build config from map-entry RNA."""
    props = entry.lks_bent_normal_object
    return BentNormalObjectConfig(
        directions=int(props.directions),
        steps_per_direction=int(props.steps_per_direction),
        radius_world=float(props.radius_world),
        spread_angle_deg=float(props.spread_angle_deg),
        bias=float(props.bias),
    )


def bent_normal_settings_from_config(config: BentNormalObjectConfig) -> BentNormalObjectSettings:
    """Convert ``BentNormalObjectConfig`` to engine settings."""
    return BentNormalObjectSettings(
        directions=config.directions,
        steps_per_direction=config.steps_per_direction,
        radius_world=config.radius_world,
        spread_angle_deg=config.spread_angle_deg,
        bias=config.bias,
    )

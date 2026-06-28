"""Static config for the ``hemisphere_trace`` bent-normal bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lks_baker.bake_ops.engine.settings.bent_normal_settings import (
    BentNormalSettings,
    HemisphereTraceSettings,
)

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry

DEFAULT_BENT_NORMAL_SAMPLE_COUNT = 16
DEFAULT_BENT_NORMAL_STEPS = 8
DEFAULT_BENT_NORMAL_RADIUS = 0.35
DEFAULT_BENT_NORMAL_BIAS = 0.02
DEFAULT_BENT_NORMAL_SPREAD = 1.0


@dataclass
class HemisphereTraceConfig:
    """Atlas hemisphere bent-normal tuning."""

    sample_count: int = DEFAULT_BENT_NORMAL_SAMPLE_COUNT
    steps_per_direction: int = DEFAULT_BENT_NORMAL_STEPS
    radius_world: float = DEFAULT_BENT_NORMAL_RADIUS
    bias: float = DEFAULT_BENT_NORMAL_BIAS
    spread: float = DEFAULT_BENT_NORMAL_SPREAD


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> HemisphereTraceConfig:
    """Build config from map-entry RNA."""
    props = entry.lks_bent_normal
    return HemisphereTraceConfig(
        sample_count=int(props.sample_count),
        steps_per_direction=int(props.steps_per_direction),
        radius_world=float(props.radius_world),
        bias=float(props.bias),
        spread=float(props.spread),
    )


def bent_normal_settings_from_config(config: HemisphereTraceConfig) -> BentNormalSettings:
    """Convert gear-popup config into engine ``BentNormalSettings``."""
    return BentNormalSettings(
        hemisphere_trace=HemisphereTraceSettings(
            sample_count=config.sample_count,
            steps_per_direction=config.steps_per_direction,
            radius_world=config.radius_world,
            bias=config.bias,
            spread=config.spread,
        ),
    )

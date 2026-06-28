"""Static config for Cycles COMBINED lighting bakes (``blender`` method)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass(frozen=True)
class LightingBakeConfig:
    """Per-map Cycles lighting bake overrides."""

    max_bounce_override: int
    clamp_direct: float
    clamp_indirect: float


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> LightingBakeConfig:
    """Read lighting bake settings from map-entry RNA."""
    settings = entry.lks_lighting
    return LightingBakeConfig(
        max_bounce_override=int(settings.max_bounce_override),
        clamp_direct=float(settings.clamp_direct),
        clamp_indirect=float(settings.clamp_indirect),
    )

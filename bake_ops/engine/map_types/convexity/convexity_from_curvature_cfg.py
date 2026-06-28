"""Static config for the ``convexity_from_curvature`` bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class ConvexityFromCurvatureConfig:
    """Engine defaults until per-method RNA is wired."""

    pass


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> ConvexityFromCurvatureConfig:
    """Build config from map entry (defaults only for now)."""
    _ = entry
    return ConvexityFromCurvatureConfig()

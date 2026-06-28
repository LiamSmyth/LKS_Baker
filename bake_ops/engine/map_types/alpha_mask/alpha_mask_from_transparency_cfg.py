"""Static config for the ``alpha_mask_from_transparency`` bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class AlphaMaskFromTransparencyConfig:
    """Engine defaults until per-method RNA is wired."""

    threshold: float = 0.5


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> AlphaMaskFromTransparencyConfig:
    """Build config from map entry (defaults only for now)."""
    _ = entry
    return AlphaMaskFromTransparencyConfig()

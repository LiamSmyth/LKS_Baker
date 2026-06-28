"""Static config for the ``normal_height_hbao`` bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class NormalHeightHbaoConfig:
    """Engine defaults until per-method RNA is wired."""

    pass


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> NormalHeightHbaoConfig:
    """Build config from map entry (defaults only for now)."""
    _ = entry
    return NormalHeightHbaoConfig()

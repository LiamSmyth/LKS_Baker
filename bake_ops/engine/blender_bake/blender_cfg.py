"""Static config for the shared ``blender`` Cycles bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class BlenderBakeConfig:
    """Per-map settings for Cycles / emit bakes (method-specific; post-process is map-level)."""


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> BlenderBakeConfig:
    """Read blender-method settings from map-entry RNA."""
    _ = entry
    return BlenderBakeConfig()

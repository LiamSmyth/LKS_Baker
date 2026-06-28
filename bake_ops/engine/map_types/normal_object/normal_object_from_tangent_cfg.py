"""Static config for ``normal_object_from_tangent`` derive method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class NormalObjectFromTangentConfig:
    """No tunable params today — TBN + tangent normal required."""

    pass


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> NormalObjectFromTangentConfig:
    """Build config from map entry (defaults only for now)."""
    _ = entry
    return NormalObjectFromTangentConfig()

"""Bent-normal map base class."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMap


class BentNormalObjectMap(BakeMap):
    """Base class for object-space bent normal ``BakeMap`` implementations."""

    map_type: ClassVar[str] = "bent_normal_object"

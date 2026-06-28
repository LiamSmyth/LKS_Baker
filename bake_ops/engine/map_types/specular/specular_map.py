"""Specular PBR map base class."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMap


class SpecularMap(BakeMap):
    """Base class for specular ``BakeMap`` implementations."""

    map_type: ClassVar[str] = "specular"

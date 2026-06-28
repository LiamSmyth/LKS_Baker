"""Cavity map base class."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMap


class CavityMap(BakeMap):
    """Base class for cavity/AO ``BakeMap`` implementations (``map_type="cavity"``)."""

    map_type: ClassVar[str] = "cavity"

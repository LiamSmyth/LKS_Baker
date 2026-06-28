"""AO map base class."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMap


class AoMap(BakeMap):
    """Base class for ambient-occlusion ``BakeMap`` implementations (``map_type="ao"``)."""

    map_type: ClassVar[str] = "ao"

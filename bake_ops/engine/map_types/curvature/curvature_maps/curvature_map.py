"""Curvature map base class."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMap


class CurvatureMap(BakeMap):
    """Base class for curvature ``BakeMap`` implementations (``map_type="curvature"``)."""

    map_type: ClassVar[str] = "curvature"

"""Curvature-specific BakeMap helpers."""
from __future__ import annotations

from lks_baker.bake_ops.engine.bake_maps.bake_map_implementation import BakeMapImplementation


class CurvatureMapImplementation(BakeMapImplementation):
    """Curvature-specific helpers mixed into CPU/GPU bake map classes."""

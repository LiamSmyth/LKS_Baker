"""Collect registered curvature ``BakeMap`` implementations."""
from __future__ import annotations

from typing import Type

from lks_baker.bake_ops.engine.bake_map import BakeMap
from lks_baker.bake_ops.engine.map_types.curvature.soft_curvature_cpu import SoftCurvatureCpu
from lks_baker.bake_ops.engine.map_types.curvature.soft_curvature_gpu import SoftCurvatureGpu

CURVATURE_BAKE_MAPS: tuple[Type[BakeMap], ...] = (
    SoftCurvatureCpu,
    SoftCurvatureGpu,
)

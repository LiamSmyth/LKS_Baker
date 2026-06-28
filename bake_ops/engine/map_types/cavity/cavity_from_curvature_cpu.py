"""Split cavity channel from packed curvature (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.cavity.cavity_map import CavityMap
from lks_baker.bake_ops.engine.static_utilities.exclusive_channels import (
    split_cavity_from_curvature_gray,
)


class CavityFromCurvatureCpu(CavityMap):
    """Concave cavity split from a packed curvature map."""

    method_id: ClassVar[str] = "cavity_from_curvature"
    device: ClassVar[str] = "cpu"
    produces: ClassVar[str] = "cavity"
    requires_textures: ClassVar[frozenset[str]] = frozenset({"curvature"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        packed_curv = inputs.extra.get("curvature_packed")
        if packed_curv is None:
            raise ValueError("cavity_from_curvature requires curvature_packed in inputs.extra")
        cavity = split_cavity_from_curvature_gray(packed_curv.astype("float32", copy=False))
        cavity[~inputs.valid] = 0.0
        return BakeMapOutput(packed=cavity, valid=inputs.valid)

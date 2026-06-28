"""Split convexity channel from packed curvature (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.static_utilities.exclusive_channels import (
    split_convexity_from_curvature_gray,
)


class ConvexityFromCurvatureCpu(BakeMap):
    """Positive curvature split from a packed curvature map."""

    map_type: ClassVar[str] = "convexity"
    method_id: ClassVar[str] = "convexity_from_curvature"
    device: ClassVar[str] = "cpu"
    requires_textures: ClassVar[frozenset[str]] = frozenset({"curvature"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        packed_curv = inputs.extra.get("curvature_packed")
        if packed_curv is None:
            raise ValueError("convexity_from_curvature requires curvature_packed in inputs.extra")
        convex = split_convexity_from_curvature_gray(packed_curv.astype("float32", copy=False))
        convex[~inputs.valid] = 0.0
        return BakeMapOutput(packed=convex, valid=inputs.valid)

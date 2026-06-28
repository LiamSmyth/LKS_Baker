"""CPU soft curvature — multi-scale integration over mip-chain radii."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.curvature.curvature_maps.curvature_map import CurvatureMap
from lks_baker.bake_ops.engine.map_types.curvature.curvature_maps.curvature_map_implementation import (
    CurvatureMapImplementation,
)
from lks_baker.bake_ops.engine.map_types.curvature.static_utilities.soft_curvature import (
    bake_soft_curvature,
)


class SoftCurvatureCpu(CurvatureMap, CurvatureMapImplementation):
    """Soft curvature from low-poly UV shell positions + object-space normal map."""

    method_id: ClassVar[str] = "soft_curvature"
    device: ClassVar[str] = "cpu"
    requires_textures = frozenset({"normal_object"})
    requires_meshes = frozenset({"mesh"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        if inputs.object_normal is None:
            raise ValueError("soft_curvature requires object_normal texture")

        mesh = inputs.low_mesh or inputs.mesh
        if mesh is None:
            mesh = self.require_mesh(inputs)

        image_size = self.image_size(inputs)
        packed, signed, coverage = bake_soft_curvature(
            inputs.object_normal,
            mesh,
            inputs.settings.soft,
            image_size=image_size,
        )
        return self.output(packed, signed=signed, valid=coverage)

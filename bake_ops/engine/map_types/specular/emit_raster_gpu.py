"""H→L specular emit raster (GPU).

Uses the validated CPU raycast core until a dedicated GPU BVH shader ships.
"""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput
from lks_baker.bake_ops.engine.map_types.specular.emit_raster_cpu import EmitRasterCpu
from lks_baker.bake_ops.engine.map_types.specular.specular_map import SpecularMap
from lks_baker.bake_ops.engine.map_types.specular.specular_map_implementation import (
    SpecularMapImplementation,
)


class EmitRasterGpu(SpecularMap, SpecularMapImplementation):
    """GPU registry slot for emit_raster — dispatches CPU core for pixel parity."""

    method_id: ClassVar[str] = "emit_raster"
    device: ClassVar[str] = "gpu"
    execution_kind: ClassVar[str] = "derive_mesh"
    cost_tier: ClassVar[int] = 2
    requires_meshes: ClassVar[frozenset[str]] = frozenset({"low", "high"})

    def bake(self, inputs: BakeMapInput):
        return EmitRasterCpu().bake(inputs)

"""Normal cavity detail AO (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.ao.ao_map import AoMap
from lks_baker.bake_ops.engine.map_types.ao.ao_map_implementation import AoMapImplementation
from lks_baker.bake_ops.engine.map_types.static_utilities.normal_cavity import normal_cavity_ao


class NormalCavityCpu(AoMap, AoMapImplementation):
    """Multiscale detail AO from tangent normal divergence."""

    method_id: ClassVar[str] = "normal_cavity"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 1
    produces: ClassVar[str] = "ao"
    requires_textures_or: ClassVar[tuple[frozenset[str], ...]] = (frozenset({"normal"}),)

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        if inputs.tangent_normal is None:
            raise ValueError("normal_cavity requires tangent normal (TSNM) texture")
        settings = self.ao_settings(inputs)
        ao = normal_cavity_ao(
            inputs.tangent_normal,
            inputs.island_id,
            inputs.valid,
            settings.cavity,
        )
        return self.output(ao, valid=inputs.valid)

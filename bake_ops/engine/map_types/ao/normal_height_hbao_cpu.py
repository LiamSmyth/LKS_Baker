"""Normal-height integrated texture HBAO detail AO (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.ao.ao_map import AoMap
from lks_baker.bake_ops.engine.map_types.ao.ao_map_implementation import AoMapImplementation
from lks_baker.bake_ops.engine.map_types.ao.static_utilities.normal_height_hbao import (
    normal_height_hbao,
)


class NormalHeightHbaoCpu(AoMap, AoMapImplementation):
    """OSNM → Poisson height → texture-space HBAO detail AO."""

    method_id: ClassVar[str] = "normal_height_hbao"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 3
    produces: ClassVar[str] = "ao"
    requires_textures_or: ClassVar[tuple[frozenset[str], ...]] = (
        frozenset({"position", "normal_object"}),
    )

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        self.require_object_normal_and_position(inputs)
        settings = self.ao_settings(inputs)
        ao = normal_height_hbao(
            inputs.object_normal,
            inputs.position,
            inputs.island_id,
            inputs.valid,
            settings,
        )
        return self.output(ao, valid=inputs.valid)

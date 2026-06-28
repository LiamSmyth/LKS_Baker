"""Atlas horizon-based AO (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.ao.ao_map import AoMap
from lks_baker.bake_ops.engine.map_types.ao.ao_map_implementation import AoMapImplementation
from lks_baker.bake_ops.engine.map_types.ao.static_utilities.atlas_hbao import atlas_hbao


class AtlasHbaoCpu(AoMap, AoMapImplementation):
    """UV-atlas horizon AO from world position + object normal atlases."""

    method_id: ClassVar[str] = "atlas_hbao"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 2
    produces: ClassVar[str] = "ao"
    requires_textures_or: ClassVar[tuple[frozenset[str], ...]] = (
        frozenset({"position", "normal_object"}),
    )

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        self.require_object_normal_and_position(inputs)
        settings = self.ao_settings(inputs)
        ao = atlas_hbao(
            inputs.position,
            inputs.object_normal,
            inputs.island_id,
            inputs.valid,
            settings.atlas_hbao,
        )
        return self.output(ao, valid=inputs.valid)

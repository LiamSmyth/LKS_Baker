"""Composite macro + detail AO (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.ao.ao_map import AoMap
from lks_baker.bake_ops.engine.map_types.ao.ao_map_implementation import AoMapImplementation
from lks_baker.bake_ops.engine.map_types.ao.static_utilities.ao_composite import ao_composite
from lks_baker.bake_ops.engine.map_types.ao.static_utilities.atlas_hbao import atlas_hbao
from lks_baker.bake_ops.engine.map_types.ao.static_utilities.normal_height_hbao import (
    normal_height_hbao,
)


class AoCompositeCpu(AoMap, AoMapImplementation):
    """Blend atlas macro AO with normal-height detail AO."""

    method_id: ClassVar[str] = "ao_composite"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 1
    produces: ClassVar[str] = "ao"
    requires_textures_or: ClassVar[tuple[frozenset[str], ...]] = (
        frozenset({"position", "normal_object"}),
    )

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        self.require_object_normal_and_position(inputs)
        settings = self.ao_settings(inputs)
        base = atlas_hbao(
            inputs.position,
            inputs.object_normal,
            inputs.island_id,
            inputs.valid,
            settings.atlas_hbao,
        )
        detail = normal_height_hbao(
            inputs.object_normal,
            inputs.position,
            inputs.island_id,
            inputs.valid,
            settings,
        )
        ao = ao_composite(base, detail, inputs.valid, settings.composite)
        return self.output(ao, valid=inputs.valid)

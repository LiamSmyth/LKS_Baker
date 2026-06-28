"""Direct height-map texture HBAO detail AO (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.ao.ao_map import AoMap
from lks_baker.bake_ops.engine.map_types.ao.ao_map_implementation import AoMapImplementation
from lks_baker.bake_ops.engine.map_types.ao.static_utilities.height_integrate import (
    integrate_height_from_object_normal,
)
from lks_baker.bake_ops.engine.map_types.ao.static_utilities.normal_height_hbao import (
    height_map_hbao,
)


class HeightHbaoCpu(AoMap, AoMapImplementation):
    """Integrate height from OSNM then run texture-space HBAO."""

    method_id: ClassVar[str] = "height_hbao"
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
        height = integrate_height_from_object_normal(
            inputs.object_normal,
            inputs.position,
            inputs.island_id,
            inputs.valid,
            settings.height_integrate,
        )
        ao = height_map_hbao(height, inputs.island_id, inputs.valid, settings)
        return self.output(ao, valid=inputs.valid)

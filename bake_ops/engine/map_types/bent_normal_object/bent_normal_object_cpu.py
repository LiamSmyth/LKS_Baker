"""Object-space bent normal atlas baker (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput
from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_map import (
    BentNormalObjectMap,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_map_implementation import (
    BentNormalObjectMapImplementation,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.static_utilities.bent_normal_object import (
    bent_normal_object,
)


class BentNormalObjectCpu(BentNormalObjectMap, BentNormalObjectMapImplementation):
    """UV-atlas hemisphere bent normals in object/world space."""

    method_id: ClassVar[str] = "bent_normal_object"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 2
    requires_textures: ClassVar[frozenset[str]] = frozenset({"position", "normal_object"})

    def bake(self, inputs: BakeMapInput):
        self.require_object_normal_and_position(inputs)
        settings = self.bent_normal_settings(inputs)
        _bent, rgba = bent_normal_object(
            inputs.position,
            inputs.object_normal,
            inputs.island_id,
            inputs.valid,
            settings,
        )
        return self.rgb_output(rgba, inputs.valid)

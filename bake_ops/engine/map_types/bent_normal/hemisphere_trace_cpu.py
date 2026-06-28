"""Atlas hemisphere bent-normal trace (CPU).

Inputs: internal object-space ``position`` and ``normal_object`` atlases.
Output: tangent-space bent normal RGB (OpenGL tangent, row 0 = UV top).
"""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput
from lks_baker.bake_ops.engine.map_types.bent_normal.bent_normal_map import BentNormalMap
from lks_baker.bake_ops.engine.map_types.bent_normal.bent_normal_map_implementation import (
    BentNormalMapImplementation,
)
from lks_baker.bake_ops.engine.map_types.bent_normal.static_utilities.atlas_hemisphere_bent_normal import (
    atlas_hemisphere_bent_normal,
)


class HemisphereTraceCpu(BentNormalMap, BentNormalMapImplementation):
    """UV-atlas hemisphere bent-normal from world position + object normal atlases."""

    method_id: ClassVar[str] = "hemisphere_trace"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 2
    requires_textures_or: ClassVar[tuple[frozenset[str], ...]] = (
        frozenset({"position", "normal_object"}),
    )

    def bake(self, inputs: BakeMapInput):
        self.require_object_normal_and_position(inputs)
        settings = self.bent_normal_settings(inputs)
        rgba, bent_tangent = atlas_hemisphere_bent_normal(
            inputs.position,
            inputs.object_normal,
            inputs.island_id,
            inputs.valid,
            settings.hemisphere_trace,
        )
        return self.rgb_output(rgba, valid=inputs.valid, bent_tangent=bent_tangent)

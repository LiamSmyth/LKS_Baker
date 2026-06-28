"""Shared helpers for bent-normal ``BakeMap`` implementations."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.bake_maps.bake_map_implementation import BakeMapImplementation
from lks_baker.bake_ops.engine.settings.bent_normal_settings import (
    BentNormalObjectSettings,
    BentNormalSettings,
    hemisphere_trace_to_object_settings,
)


class BentNormalObjectMapImplementation(BakeMapImplementation):
    """Shared helpers mixed into bent-normal CPU/GPU bake map classes."""

    @staticmethod
    def bent_normal_settings(inputs: BakeMapInput) -> BentNormalObjectSettings:
        """Return per-invocation bent-normal settings from ``inputs.extra``."""
        settings = inputs.extra.get("bent_normal_settings")
        if isinstance(settings, BentNormalObjectSettings):
            return settings
        if isinstance(settings, BentNormalSettings):
            return hemisphere_trace_to_object_settings(settings.hemisphere_trace)
        return BentNormalObjectSettings()

    @staticmethod
    def require_object_normal_and_position(inputs: BakeMapInput) -> None:
        """Raise when object-space normal or position textures are missing."""
        if inputs.object_normal is None or inputs.position is None:
            raise ValueError("bent_normal_object requires normal_object and position textures")

    @staticmethod
    def rgb_output(bent_rgba, valid) -> BakeMapOutput:
        """Pack RGB bent-normal map into ``BakeMapOutput``."""
        gray = bent_rgba[..., 0].astype(np.float32, copy=False)
        return BakeMapOutput(packed=gray, valid=valid, meta={"rgba": bent_rgba})

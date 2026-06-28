"""Bent-normal-specific ``BakeMap`` helpers."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.bake_maps.bake_map_implementation import BakeMapImplementation
from lks_baker.bake_ops.engine.settings.bent_normal_settings import (
    BentNormalObjectSettings,
    BentNormalSettings,
    HemisphereTraceSettings,
    hemisphere_trace_to_object_settings,
)


class BentNormalMapImplementation(BakeMapImplementation):
    """Shared helpers mixed into bent-normal CPU/GPU bake map classes."""

    @staticmethod
    def bent_normal_settings(inputs: BakeMapInput) -> BentNormalSettings:
        """Return per-invocation bent-normal settings from ``inputs.extra``."""
        settings = inputs.extra.get("bent_normal_settings")
        if isinstance(settings, BentNormalSettings):
            return settings
        if isinstance(settings, BentNormalObjectSettings):
            return BentNormalSettings(
                hemisphere_trace=HemisphereTraceSettings(
                    sample_count=settings.directions,
                    steps_per_direction=settings.steps_per_direction,
                    radius_world=settings.radius_world,
                    bias=settings.bias,
                    spread=min(1.0, max(0.05, settings.spread_angle_deg / 90.0)),
                ),
            )
        return BentNormalSettings()

    @staticmethod
    def require_object_normal_and_position(inputs: BakeMapInput) -> None:
        """Raise when object-space normal or position textures are missing."""
        if inputs.object_normal is None or inputs.position is None:
            raise ValueError("bent_normal method requires normal_object and position textures")

    @staticmethod
    def rgb_output(
        rgba: np.ndarray,
        *,
        valid: np.ndarray | None = None,
        bent_tangent: np.ndarray | None = None,
    ) -> BakeMapOutput:
        """Build output for tangent bent-normal RGB maps."""
        gray = rgba[..., 2].astype(np.float32, copy=False)
        meta: dict[str, np.ndarray] = {"rgba": rgba}
        if bent_tangent is not None:
            meta["bent_tangent"] = bent_tangent
        return BakeMapOutput(packed=gray, valid=valid, meta=meta)

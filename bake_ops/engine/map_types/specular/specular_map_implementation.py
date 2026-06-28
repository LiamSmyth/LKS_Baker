"""Specular-specific ``BakeMap`` helpers."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.bake_maps.bake_map_implementation import BakeMapImplementation
from lks_baker.bake_ops.engine.map_types.specular.emit_raster_cfg import EmitRasterConfig


class SpecularMapImplementation(BakeMapImplementation):
    """Shared helpers for specular CPU/GPU bake map classes."""

    @staticmethod
    def emit_raster_config(inputs: BakeMapInput) -> EmitRasterConfig:
        """Return emit-raster config from ``inputs.extra``."""
        config = inputs.extra.get("emit_raster_config")
        if isinstance(config, EmitRasterConfig):
            return config
        return EmitRasterConfig()

    @staticmethod
    def rgb_output(rgba: np.ndarray, *, valid: np.ndarray | None = None) -> BakeMapOutput:
        """Build grayscale-packed output for specular RGB bakes."""
        gray = rgba[..., 0].astype(np.float32, copy=False)
        return BakeMapOutput(packed=gray, valid=valid, meta={"rgba": rgba})

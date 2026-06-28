"""Rasterize low-mesh triangle edges in UV space (CPU)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.map_types.wireframe.static_utilities.wireframe_raster import (
    rasterize_wireframe_uv,
)
from lks_baker.bake_ops.engine.map_types.wireframe.wireframe_uv_raster_cfg import (
    WireframeUvRasterConfig,
)


class WireframeUvRasterCpu(BakeMap):
    """Colored wireframe lines from low-poly mesh UV edges."""

    map_type: ClassVar[str] = "wireframe"
    method_id: ClassVar[str] = "wireframe_uv_raster"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_mesh"
    requires_meshes: ClassVar[frozenset[str]] = frozenset({"low"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        mesh = inputs.low_mesh or inputs.mesh
        if mesh is None:
            raise ValueError("wireframe_uv_raster requires low mesh in BakeMapInput")
        image_size = inputs.image_size
        if image_size is None:
            raise ValueError("wireframe_uv_raster requires image_size")

        config = inputs.extra.get("wireframe_config")
        if not isinstance(config, WireframeUvRasterConfig):
            config = WireframeUvRasterConfig()

        rgba, valid = rasterize_wireframe_uv(
            mesh,
            image_size,
            color=config.color,
            line_thickness_px=config.line_thickness_px,
            aa_quality=config.aa_quality,
        )
        if (
            inputs.valid is not None
            and inputs.valid.shape == valid.shape
            and np.any(inputs.valid)
        ):
            valid = valid & inputs.valid
            rgba[~valid] = 0.0

        gray = rgba[..., 0].astype(np.float32, copy=False)
        return BakeMapOutput(packed=gray, valid=valid, meta={"rgba": rgba})

"""Flood-fill UV islands to stable pseudo-random RGB colors (CPU)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.static_utilities.island_colors import paint_island_id_rgba
from lks_baker.bake_ops.engine.static_utilities.mesh_uv_charts import (
    rasterize_triangle_chart_ids,
    triangle_uv_chart_ids,
)


class UvIslandFromMeshCpu(BakeMap):
    """UV island visualization from low-poly mesh chart ids."""

    map_type: ClassVar[str] = "uv_island"
    method_id: ClassVar[str] = "uv_island_from_mesh"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_mesh"
    requires_meshes: ClassVar[frozenset[str]] = frozenset({"low"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        mesh = inputs.low_mesh or inputs.mesh
        if mesh is None:
            raise ValueError("uv_island_from_mesh requires low mesh in BakeMapInput")
        image_size = inputs.image_size
        if image_size is None:
            raise ValueError("uv_island_from_mesh requires image_size")

        charts = triangle_uv_chart_ids(mesh)
        island_id, raster_valid = rasterize_triangle_chart_ids(mesh, charts, image_size)
        valid = raster_valid.astype(bool, copy=False)
        if (
            inputs.valid is not None
            and inputs.valid.shape == valid.shape
            and np.any(inputs.valid)
        ):
            valid = valid & inputs.valid

        rgba = paint_island_id_rgba(island_id, valid)
        gray = rgba[..., 0].astype(np.float32, copy=False)
        return BakeMapOutput(packed=gray, valid=valid, meta={"rgba": rgba})

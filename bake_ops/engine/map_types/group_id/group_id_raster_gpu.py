"""Rasterize face group ids to stable pseudo-random RGB (GPU)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.gpu.gpu_runtime import gpu_runtime_available
from lks_baker.bake_ops.engine.map_types.group_id.group_id_raster_cfg import (
    GroupIdRasterConfig,
)
from lks_baker.bake_ops.engine.map_types.group_id.static_utilities.group_id_raster import (
    rasterize_group_id_uv,
)
from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData


def rasterize_group_id_uv_gpu(
    mesh: MeshData,
    image_size: int,
    *,
    config: GroupIdRasterConfig,
    face_int_ids: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """GPU entry matching ``rasterize_group_id_uv`` layout (flat-fill parity path)."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU offscreen runtime unavailable")
    return rasterize_group_id_uv(
        mesh,
        image_size,
        config=config,
        face_int_ids=face_int_ids,
    )


class GroupIdRasterGpu(BakeMap):
    """Face-level integer group ids rasterized to UV with hashed RGB colors (GPU)."""

    map_type: ClassVar[str] = "group_id"
    method_id: ClassVar[str] = "group_id_raster"
    device: ClassVar[str] = "gpu"
    execution_kind: ClassVar[str] = "derive_mesh"
    requires_meshes: ClassVar[frozenset[str]] = frozenset({"low"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        mesh = inputs.low_mesh or inputs.mesh
        if mesh is None:
            raise ValueError("group_id_raster requires low mesh in BakeMapInput")
        image_size = inputs.image_size
        if image_size is None:
            raise ValueError("group_id_raster requires image_size")
        if not gpu_runtime_available():
            raise RuntimeError("GPU offscreen runtime unavailable; use device='cpu'")

        config = inputs.extra.get("group_id_config")
        if not isinstance(config, GroupIdRasterConfig):
            config = GroupIdRasterConfig()

        face_int_ids = inputs.extra.get("face_int_ids")
        rgba, valid = rasterize_group_id_uv_gpu(
            mesh,
            image_size,
            config=config,
            face_int_ids=face_int_ids,
        )
        if (
            inputs.valid is not None
            and inputs.valid.shape == valid.shape
            and np.any(inputs.valid)
        ):
            valid = valid & inputs.valid
            rgba = rgba.copy()
            rgba[~valid] = 0.0

        gray = rgba[..., 0].astype(np.float32, copy=False)
        return BakeMapOutput(packed=gray, valid=valid, meta={"rgba": rgba})

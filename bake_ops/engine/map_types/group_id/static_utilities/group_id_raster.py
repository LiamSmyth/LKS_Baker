"""Rasterize per-face integer group ids into UV atlas pseudo-random RGB."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.map_types.group_id.group_id_raster_cfg import (
    GroupIdRasterConfig,
)
from lks_baker.bake_ops.engine.map_types.group_id.static_utilities.face_group_ids import (
    resolve_mesh_face_int_ids,
)
from lks_baker.bake_ops.engine.static_utilities.island_colors import paint_island_id_rgba
from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData
from lks_baker.bake_ops.engine.static_utilities.mesh_uv_charts import (
    rasterize_triangle_chart_ids,
)


def rasterize_face_group_ids(
    mesh: MeshData,
    face_int_ids: np.ndarray,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize per-triangle group ids to an H×W int32 label map."""
    ids = np.asarray(face_int_ids, dtype=np.int32)
    if len(ids) != len(mesh.faces):
        raise ValueError(
            f"face_int_ids length {len(ids)} != triangle count {len(mesh.faces)}",
        )
    group_id, raster_valid = rasterize_triangle_chart_ids(mesh, ids, image_size)
    return group_id, raster_valid.astype(bool, copy=False)


def rasterize_group_id_uv(
    mesh: MeshData,
    image_size: int,
    *,
    config: GroupIdRasterConfig,
    face_int_ids: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Paint stable pseudo-random RGBA from face group ids in UV space."""
    ids = (
        np.asarray(face_int_ids, dtype=np.int32)
        if face_int_ids is not None
        else resolve_mesh_face_int_ids(mesh)
    )
    group_id, raster_valid = rasterize_face_group_ids(mesh, ids, image_size)
    valid = raster_valid.copy()
    if config.treat_zero_as_background:
        valid &= group_id != 0
        group_id = group_id.copy()
        group_id[~valid] = -1

    rgba = paint_island_id_rgba(group_id, valid)
    return rgba, valid

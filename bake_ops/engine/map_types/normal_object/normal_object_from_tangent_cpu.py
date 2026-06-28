"""Transform tangent-space normal + per-texel TBN into object-space normals (CPU)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput


def _tangent_to_object_normals(
    tangent_normal: np.ndarray,
    tbn_tangent: np.ndarray,
    tbn_bitangent: np.ndarray,
    tbn_normal: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """Return H×W×4 RGBA object-space normal map colors."""
    height, width = tangent_normal.shape[:2]
    out = np.zeros((height, width, 4), dtype=np.float32)
    if not np.any(valid):
        return out

    nt = tangent_normal.astype(np.float32, copy=False)
    tx, ty, tz = (tbn_tangent[..., 0], tbn_tangent[..., 1], tbn_tangent[..., 2])
    bx, by, bz = (tbn_bitangent[..., 0], tbn_bitangent[..., 1], tbn_bitangent[..., 2])
    nx, ny, nz = (tbn_normal[..., 0], tbn_normal[..., 1], tbn_normal[..., 2])

    wx = tx * nt[..., 0] + bx * nt[..., 1] + nx * nt[..., 2]
    wy = ty * nt[..., 0] + by * nt[..., 1] + ny * nt[..., 2]
    wz = tz * nt[..., 0] + bz * nt[..., 1] + nz * nt[..., 2]
    length = np.sqrt(wx * wx + wy * wy + wz * wz)
    safe = length > 1e-8
    inv = np.where(safe, 1.0 / length, 0.0)
    wx = np.where(safe, wx * inv, 0.0)
    wy = np.where(safe, wy * inv, 0.0)
    wz = np.where(safe, wz * inv, 1.0)

    out[..., 0] = wx * 0.5 + 0.5
    out[..., 1] = wy * 0.5 + 0.5
    out[..., 2] = wz * 0.5 + 0.5
    out[..., 3] = 1.0
    out[~valid] = 0.0
    return out


class NormalObjectFromTangentCpu(BakeMap):
    """Derive object/world normals from tangent normal + TBN raster."""

    map_type: ClassVar[str] = "normal_object"
    method_id: ClassVar[str] = "normal_object_from_tangent"
    device: ClassVar[str] = "cpu"
    requires_textures: ClassVar[frozenset[str]] = frozenset({"normal"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        tangent_normal = inputs.tangent_normal
        if tangent_normal is None:
            raise ValueError("normal_object_from_tangent requires tangent_normal")

        tbn_tangent = inputs.extra.get("tbn_tangent")
        tbn_bitangent = inputs.extra.get("tbn_bitangent")
        tbn_normal = inputs.extra.get("tbn_normal")
        if tbn_tangent is None or tbn_bitangent is None or tbn_normal is None:
            raise ValueError("normal_object_from_tangent requires tbn_* arrays in inputs.extra")

        valid = inputs.valid
        if valid is None:
            valid = inputs.island_id >= 0

        rgba = _tangent_to_object_normals(
            tangent_normal,
            tbn_tangent,
            tbn_bitangent,
            tbn_normal,
            valid,
        )
        gray = rgba[..., 0].astype(np.float32, copy=False)
        return BakeMapOutput(packed=gray, valid=valid, meta={"rgba": rgba})

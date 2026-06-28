"""Canonical bake-engine coordinate contract (Blender 5.1 / Cycles).

Internal contract (after ingest + decode)
-----------------------------------------
All bake methods consume **one** layout. External app spaces are converted at
IO only (``engine/image_filters/``), never via runtime settings.

| Field | Space | Layout |
|-------|-------|--------|
| Tangent normals | MikkTSpace tangent, OpenGL Y+ | Unit vectors, ``rgb*2-1``, green up |
| Object normals | Blender object-space bake | Unit vectors as Cycles ``BLENDER_OBJECT`` |
| Position | Blender object-space bake | ``rgb*2-1`` object coordinates |
| PNG atlas | OpenGL bake | Row 0 = UV V=1 (top); +V = row index decreases |

Sources
-------
- Normal Map node, OpenGL default: https://docs.blender.org/manual/en/5.1/render/shader_nodes/displacement/normal_map.html
- ``ShaderNodeNormalMap.space`` / ``.uv_map``: https://docs.blender.org/api/current/bpy.types.ShaderNodeNormalMap.html
- Blender uses right-handed coords (+Y up, -Z forward for object/world bakes).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class TangentSpaceConvention(str, Enum):
    """Green-channel Y direction in **encoded** tangent normal RGB (ingest only)."""

    OPENGL = "opengl"
    DIRECTX = "directx"


class PngVConvention(str, Enum):
    """How PNG row index maps to OpenGL texture V (ingest only)."""

    OPENGL_BAKE = "opengl_bake"
    """Row 0 = V1 (top of UV island). +V in OpenGL = decreasing row index."""

    IMAGE_DOWN = "image_down"
    """Row 0 = V0. +V in texture = increasing row index (non-Blender sources)."""


class InternalNormalSpace(str, Enum):
    """Decoded normal fields inside the bake engine."""

    TANGENT_OPENGL = "tangent_opengl"
    """MikkTSpace tangent unit normal, OpenGL green up."""

    OBJECT_BLENDER = "object_blender"
    """Blender object-space unit normal (Cycles ``BLENDER_OBJECT`` bake)."""


class PositionSpace(str, Enum):
    """Decoded position fields inside the bake engine."""

    OBJECT_BLENDER = "object_blender"
    """Blender object-space position bake (``rgb*2-1``)."""


@dataclass(frozen=True)
class BakeConvention:
    """External bake layout descriptor — **ingest filters only**, not runtime."""

    tangent: TangentSpaceConvention = TangentSpaceConvention.OPENGL
    png_v: PngVConvention = PngVConvention.OPENGL_BAKE

    @classmethod
    def opengl_default(cls) -> BakeConvention:
        """Blender / Marmoset default: OpenGL tangent, PNG top = UV top."""
        return cls()

    @classmethod
    def internal(cls) -> BakeConvention:
        """Alias for the single internal atlas layout."""
        return cls.opengl_default()


# Frozen internal layout — do not parameterize bake methods with this.
INTERNAL_BAKE_CONVENTION = BakeConvention.internal()
INTERNAL_TANGENT_NORMAL = InternalNormalSpace.TANGENT_OPENGL
INTERNAL_OBJECT_NORMAL = InternalNormalSpace.OBJECT_BLENDER
INTERNAL_POSITION = PositionSpace.OBJECT_BLENDER


def internal_v_neighbor_indices() -> tuple[int, int]:
    """Return (plus_v_row_delta, minus_v_row_delta) for internal PNG layout."""
    return -1, 1


def decode_normal_rgb(rgb: np.ndarray) -> np.ndarray:
    """Decode OpenGL tangent or Blender object normal RGB (0..1) to unit normal.

    DirectX sources must pass through ``switch_normal_opengl_directx_cpu`` before decode.
    """
    normal = rgb.astype(np.float32) * 2.0 - 1.0
    length = np.linalg.norm(normal, axis=-1, keepdims=True)
    return normal / np.maximum(length, 1e-8)


def decode_position_rgb(rgb: np.ndarray) -> np.ndarray:
    """Decode Blender object-space position map (0..1 per channel) to object coords."""
    return (rgb.astype(np.float32) * 2.0 - 1.0)


def png_row_to_gl_v(row: np.ndarray, height: int) -> np.ndarray:
    """Map PNG row indices to OpenGL V for upload (row 0 = V=1)."""
    return 1.0 - (row.astype(np.float32) + 0.5) / float(height)


def gl_readback_to_png_rows(field: np.ndarray) -> np.ndarray:
    """Restore PNG row order after GL ``read_color`` (bottom-first → top-first)."""
    return np.flipud(field)


def png_to_gpu_texture_rows(rgba: np.ndarray) -> np.ndarray:
    """Flip PNG-layout RGBA for ``GPUTexture`` upload (top row → GL V=1)."""
    return np.flipud(rgba)


# Deprecated — kept for ingest/remap helpers; bake code uses ``internal_v_neighbor_indices``.
def v_neighbor_indices(convention: BakeConvention) -> tuple[int, int]:
    """Return V neighbor row deltas for an external ``BakeConvention`` (ingest/tests)."""
    if convention.png_v is PngVConvention.OPENGL_BAKE:
        return -1, 1
    return 1, -1

"""Map known external bake spaces to internal canonical RGBA (pre-decode)."""
from __future__ import annotations

from enum import Enum

import numpy as np

from ..static_utilities.coords import (
    BakeConvention,
    PngVConvention,
    TangentSpaceConvention,
)
from . import switch_normal_opengl_directx_cpu


class ExternalBakeSpace(str, Enum):
    """Common source layouts for ingest remapping."""

    BLENDER_CYCLES = "blender_cycles"
    """Blender 5.1 Cycles bakes — already internal canonical."""

    DIRECTX_TANGENT = "directx_tangent"
    """DirectX tangent normal RGB; PNG top = UV top."""

    DIRECTX_TANGENT_IMAGE_DOWN = "directx_tangent_image_down"
    """DirectX tangent normal; row 0 = UV V=0."""


_EXTERNAL_TO_CONVENTION: dict[ExternalBakeSpace, BakeConvention] = {
    ExternalBakeSpace.BLENDER_CYCLES: BakeConvention.opengl_default(),
    ExternalBakeSpace.DIRECTX_TANGENT: BakeConvention(
        tangent=TangentSpaceConvention.DIRECTX,
        png_v=PngVConvention.OPENGL_BAKE,
    ),
    ExternalBakeSpace.DIRECTX_TANGENT_IMAGE_DOWN: BakeConvention(
        tangent=TangentSpaceConvention.DIRECTX,
        png_v=PngVConvention.IMAGE_DOWN,
    ),
}


def external_convention(space: ExternalBakeSpace) -> BakeConvention:
    """Return the ``BakeConvention`` descriptor for an external source space."""
    return _EXTERNAL_TO_CONVENTION[space]


def filter(
    image: np.ndarray,
    *,
    from_space: ExternalBakeSpace,
    to_space: ExternalBakeSpace = ExternalBakeSpace.BLENDER_CYCLES,
) -> np.ndarray:
    """Remap RGBA from ``from_space`` to internal canonical ``to_space`` layout."""
    if from_space is to_space:
        return np.array(image, copy=True)

    src = _EXTERNAL_TO_CONVENTION[from_space]
    dst = _EXTERNAL_TO_CONVENTION[to_space]
    out = np.array(image, dtype=np.float32, copy=True)

    if src.tangent is not dst.tangent:
        out = switch_normal_opengl_directx_cpu.filter(
            out,
            from_convention=src.tangent,
            to_convention=dst.tangent,
        )

    if src.png_v is not dst.png_v:
        if src.png_v is PngVConvention.IMAGE_DOWN and dst.png_v is PngVConvention.OPENGL_BAKE:
            out = np.flipud(out)
        elif src.png_v is PngVConvention.OPENGL_BAKE and dst.png_v is PngVConvention.IMAGE_DOWN:
            out = np.flipud(out)
        else:
            raise ValueError(f"unsupported png_v remap: {src.png_v!r} → {dst.png_v!r}")

    return out

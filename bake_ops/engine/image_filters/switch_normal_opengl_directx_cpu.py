"""OpenGL ↔ DirectX tangent normal RGB conversion (green-channel flip).

Blender 5.1 bakes and expects OpenGL convention (Y+ in green):
https://docs.blender.org/manual/en/5.1/render/shader_nodes/displacement/normal_map.html
"""
from __future__ import annotations

import numpy as np

from ..static_utilities.coords import TangentSpaceConvention


def filter(
    image: np.ndarray,
    *,
    from_convention: TangentSpaceConvention,
    to_convention: TangentSpaceConvention,
) -> np.ndarray:
    """Flip green channel when converting between OpenGL and DirectX normal RGB.

    Args:
        image: H×W×C float RGBA or RGB in 0..1.
        from_convention: Encoded tangent normal convention of ``image``.
        to_convention: Desired encoded convention on output.

    Returns:
        Copy of ``image`` with green channel adjusted when conventions differ.
    """
    if from_convention is to_convention:
        return np.array(image, copy=True)
    if from_convention not in (
        TangentSpaceConvention.OPENGL,
        TangentSpaceConvention.DIRECTX,
    ) or to_convention not in (
        TangentSpaceConvention.OPENGL,
        TangentSpaceConvention.DIRECTX,
    ):
        raise ValueError(
            f"switch_normal supports OPENGL/DIRECTX only, got {from_convention!r} → {to_convention!r}"
        )
    out = np.array(image, dtype=np.float32, copy=True)
    out[..., 1] = 1.0 - out[..., 1]
    return out

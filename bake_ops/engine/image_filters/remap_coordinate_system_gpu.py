"""GPU remap from external bake spaces to internal canonical RGBA."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.gpu.gpu_runtime import gpu_runtime_available
from . import flip_png_v_gpu, switch_normal_opengl_directx_gpu
from .remap_coordinate_system_cpu import ExternalBakeSpace, external_convention
from lks_baker.bake_ops.engine.static_utilities.coords import PngVConvention


def filter(
    image: np.ndarray,
    *,
    from_space: ExternalBakeSpace,
    to_space: ExternalBakeSpace = ExternalBakeSpace.BLENDER_CYCLES,
) -> np.ndarray:
    """Remap RGBA from ``from_space`` to internal canonical ``to_space`` layout."""
    if from_space is to_space:
        return np.array(image, copy=True)
    if not gpu_runtime_available():
        raise RuntimeError("GPU runtime unavailable — use remap_coordinate_system_cpu.filter")

    src = external_convention(from_space)
    dst = external_convention(to_space)
    out = np.array(image, dtype=np.float32, copy=True)

    if src.tangent is not dst.tangent:
        out = switch_normal_opengl_directx_gpu.filter(
            out,
            from_convention=src.tangent,
            to_convention=dst.tangent,
        )

    if src.png_v is not dst.png_v:
        if src.png_v is PngVConvention.IMAGE_DOWN and dst.png_v is PngVConvention.OPENGL_BAKE:
            out = flip_png_v_gpu.filter(out)
        elif src.png_v is PngVConvention.OPENGL_BAKE and dst.png_v is PngVConvention.IMAGE_DOWN:
            out = flip_png_v_gpu.filter(out)
        else:
            raise ValueError(f"unsupported png_v remap: {src.png_v!r} → {dst.png_v!r}")

    return out

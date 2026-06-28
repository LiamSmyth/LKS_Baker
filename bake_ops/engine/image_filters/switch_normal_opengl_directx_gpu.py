"""GPU OpenGL ↔ DirectX tangent normal RGB conversion (green-channel flip)."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    gpu_runtime_available,
    run_fullscreen_shader_rgba,
    upload_rgba_texture,
)
from lks_baker.bake_ops.engine.image_filters.shaders import (
    FULLSCREEN_VERT,
    SWITCH_NORMAL_FRAG,
)
from lks_baker.bake_ops.engine.static_utilities.coords import TangentSpaceConvention

_SWITCH_NORMAL_PUSH: tuple[tuple[str, str, int], ...] = (("FLOAT", "flipGreen", 0),)
_SWITCH_NORMAL_SAMPLERS: tuple[str, ...] = ("imageTex",)


def filter(
    image: np.ndarray,
    *,
    from_convention: TangentSpaceConvention,
    to_convention: TangentSpaceConvention,
) -> np.ndarray:
    """Flip green channel when converting between OpenGL and DirectX normal RGB."""
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

    if not gpu_runtime_available():
        raise RuntimeError("GPU runtime unavailable — use switch_normal_opengl_directx_cpu.filter")

    height, width = image.shape[:2]
    channels = image.shape[2] if image.ndim == 3 else 1
    if channels == 1:
        rgba = np.zeros((height, width, 4), dtype=np.float32)
        rgba[..., 0] = image.astype(np.float32, copy=False)
        rgba[..., 3] = 1.0
    elif channels >= 4:
        rgba = np.array(image[..., :4], dtype=np.float32, copy=True)
    else:
        rgba = np.zeros((height, width, 4), dtype=np.float32)
        rgba[..., :channels] = image.astype(np.float32, copy=False)
        rgba[..., 3] = 1.0

    out_rgba = run_fullscreen_shader_rgba(
        FULLSCREEN_VERT,
        SWITCH_NORMAL_FRAG,
        width,
        height,
        {"flipGreen": 1.0},
        {"imageTex": upload_rgba_texture(rgba)},
        sampler_names=_SWITCH_NORMAL_SAMPLERS,
        push_constants=_SWITCH_NORMAL_PUSH,
    )

    if image.ndim == 2:
        return out_rgba[..., 0].astype(np.float32, copy=False)
    if channels >= 4:
        out = np.array(image, dtype=np.float32, copy=True)
        out[..., :4] = out_rgba
        if image.shape[-1] > 4:
            out[..., 4:] = image[..., 4:]
        return out
    return out_rgba[..., :channels].astype(np.float32, copy=False)

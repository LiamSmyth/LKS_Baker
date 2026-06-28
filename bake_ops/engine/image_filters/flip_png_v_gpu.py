"""GPU PNG row-order flip (IMAGE_DOWN ↔ OPENGL_BAKE)."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    gpu_runtime_available,
    run_fullscreen_shader_rgba,
    upload_rgba_texture,
)
from lks_baker.bake_ops.engine.image_filters.shaders import (
    FLIP_PNG_V_FRAG,
    FULLSCREEN_VERT,
)

_FLIP_PUSH: tuple[tuple[str, str, int], ...] = ()
_FLIP_SAMPLERS: tuple[str, ...] = ("imageTex",)


def filter(image: np.ndarray) -> np.ndarray:
    """Flip image rows to swap PNG V convention (row 0 top ↔ row 0 bottom)."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU runtime unavailable — use np.flipud(image) on CPU")

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
        FLIP_PNG_V_FRAG,
        width,
        height,
        {},
        {"imageTex": upload_rgba_texture(rgba)},
        sampler_names=_FLIP_SAMPLERS,
        push_constants=_FLIP_PUSH,
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

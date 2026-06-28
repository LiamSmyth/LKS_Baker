"""GPU percentile normalization for masked float image fields."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    gpu_runtime_available,
    run_fullscreen_shader_rgba,
    upload_rgba_texture,
)
from lks_baker.bake_ops.engine.image_filters.normalize_cpu import percentile_scale
from lks_baker.bake_ops.engine.image_filters.shaders import (
    FULLSCREEN_VERT,
    NORMALIZE_POSITIVE_FRAG,
    NORMALIZE_SIGNED_FRAG,
)

_SIGNED_PUSH: tuple[tuple[str, str, int], ...] = (
    ("FLOAT", "scale", 0),
    ("FLOAT", "contrast", 0),
    ("FLOAT", "flatFill", 0),
    ("FLOAT", "amplitude", 0),
    ("FLOAT", "useDirectAmplitude", 0),
)
_SIGNED_SAMPLERS: tuple[str, ...] = ("imageTex", "validTex")

_POSITIVE_PUSH: tuple[tuple[str, str, int], ...] = (
    ("FLOAT", "scale", 0),
    ("FLOAT", "flatFill", 0),
)
_POSITIVE_SAMPLERS: tuple[str, ...] = ("imageTex", "validTex")


def _upload_scalar_texture(values: np.ndarray) -> object:
    height, width = values.shape[:2]
    rgba = np.zeros((height, width, 4), dtype=np.float32)
    rgba[..., 0] = values.astype(np.float32, copy=False)
    rgba[..., 3] = 1.0
    return upload_rgba_texture(rgba)


def _upload_valid_texture(valid: np.ndarray) -> object:
    height, width = valid.shape[:2]
    rgba = np.zeros((height, width, 4), dtype=np.float32)
    rgba[..., 0] = valid.astype(np.float32, copy=False)
    rgba[..., 3] = 1.0
    return upload_rgba_texture(rgba)


def filter_signed(
    signed: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    contrast: float = 1.0,
    flat: float = 0.5,
    amplitude: float | None = None,
) -> np.ndarray:
    """Unitize a signed scalar field to mid-gray grayscale in [0, 1]."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU runtime unavailable — use normalize_cpu.filter_signed")

    height, width = signed.shape[:2]
    scale = percentile_scale(np.abs(signed), valid, percentile=percentile)
    use_direct = 1.0 if amplitude is not None else 0.0
    amp = float(amplitude if amplitude is not None else 0.0)
    out_rgba = run_fullscreen_shader_rgba(
        FULLSCREEN_VERT,
        NORMALIZE_SIGNED_FRAG,
        width,
        height,
        {
            "scale": scale,
            "contrast": contrast,
            "flatFill": flat,
            "amplitude": amp,
            "useDirectAmplitude": use_direct,
        },
        {
            "imageTex": _upload_scalar_texture(signed),
            "validTex": _upload_valid_texture(valid),
        },
        sampler_names=_SIGNED_SAMPLERS,
        push_constants=_SIGNED_PUSH,
    )
    return out_rgba[..., 0].astype(np.float32, copy=False)


def filter_positive(
    values: np.ndarray,
    valid: np.ndarray,
    *,
    percentile: float = 95.0,
    flat: float = 0.0,
) -> np.ndarray:
    """Unitize a non-negative scalar field to [0, 1] via percentile scaling."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU runtime unavailable — use normalize_cpu.filter_positive")

    height, width = values.shape[:2]
    scale = percentile_scale(values, valid, percentile=percentile)
    out_rgba = run_fullscreen_shader_rgba(
        FULLSCREEN_VERT,
        NORMALIZE_POSITIVE_FRAG,
        width,
        height,
        {"scale": scale, "flatFill": flat},
        {
            "imageTex": _upload_scalar_texture(values),
            "validTex": _upload_valid_texture(valid),
        },
        sampler_names=_POSITIVE_SAMPLERS,
        push_constants=_POSITIVE_PUSH,
    )
    return out_rgba[..., 0].astype(np.float32, copy=False)

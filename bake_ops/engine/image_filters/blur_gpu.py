"""Per-island Gaussian blur for H×W or H×W×C float fields on GPU."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    FullscreenOffscreenSession,
    gpu_runtime_available,
    upload_island_texture,
)
from lks_baker.bake_ops.engine.image_filters._gpu_helpers import (
    gaussian_1d_weights,
    read_rg_field,
    upload_kernel_texture,
    upload_mask_texture,
    upload_scalar_texture,
)
from lks_baker.bake_ops.engine.image_filters.shaders import (
    BLUR_PASS_FRAG,
    FULLSCREEN_VERT,
)
from lks_baker.bake_ops.engine.static_utilities.islands import (
    _coalesce_island_ids,
    _iter_island_labels,
)

_BLUR_PUSH: tuple[tuple[str, str, int], ...] = (
    ("INT", "kernelSize", 0),
    ("INT", "kernelRadius", 0),
    ("INT", "horizontalPass", 0),
    ("INT", "useBlurredWeight", 0),
)
_BLUR_SAMPLERS: tuple[str, ...] = (
    "sourceTex",
    "islandTex",
    "maskTex",
    "weightTex",
    "kernelTex",
)
_WEIGHT_EPS = 1e-8


def _draw_blur_pass(
    session: FullscreenOffscreenSession,
    *,
    channel: np.ndarray,
    island_id: np.ndarray,
    sample_mask: np.ndarray,
    weights: np.ndarray,
    kernel_radius: int,
    horizontal: bool,
    use_blurred_weight: bool,
    weight_field: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    kernel_tex = upload_kernel_texture(weights)
    island_tex = upload_island_texture(island_id.astype(np.float32))
    mask_tex = upload_mask_texture(sample_mask)
    source_tex = upload_scalar_texture(channel)
    weight_tex = upload_scalar_texture(
        weight_field if weight_field is not None else np.zeros_like(channel, dtype=np.float32)
    )
    rgba = session.draw_rgba(
        {
            "kernelSize": int(weights.size),
            "kernelRadius": kernel_radius,
            "horizontalPass": 1 if horizontal else 0,
            "useBlurredWeight": 1 if use_blurred_weight else 0,
        },
        {
            "sourceTex": source_tex,
            "islandTex": island_tex,
            "maskTex": mask_tex,
            "weightTex": weight_tex,
            "kernelTex": kernel_tex,
        },
    )
    return read_rg_field(rgba)


def _blur_channel_gpu(
    channel: np.ndarray,
    island_id: np.ndarray,
    sample_mask: np.ndarray,
    sigma: float,
    *,
    width: int,
    height: int,
) -> np.ndarray:
    weights = gaussian_1d_weights(sigma)
    kernel_radius = (int(weights.size) - 1) // 2

    session = FullscreenOffscreenSession(
        FULLSCREEN_VERT,
        BLUR_PASS_FRAG,
        width,
        height,
        sampler_names=_BLUR_SAMPLERS,
        push_constants=_BLUR_PUSH,
    )
    try:
        value_v, weight_v = _draw_blur_pass(
            session,
            channel=channel,
            island_id=island_id,
            sample_mask=sample_mask,
            weights=weights,
            kernel_radius=kernel_radius,
            horizontal=False,
            use_blurred_weight=False,
        )
        value_h, weight_h = _draw_blur_pass(
            session,
            channel=value_v,
            island_id=island_id,
            sample_mask=sample_mask,
            weights=weights,
            kernel_radius=kernel_radius,
            horizontal=True,
            use_blurred_weight=True,
            weight_field=weight_v,
        )
    finally:
        session.free()

    normalized = value_h / np.maximum(weight_h, _WEIGHT_EPS)
    out = np.zeros_like(channel, dtype=np.float32)
    labels = _iter_island_labels(island_id, island_id >= 0)
    for label in labels:
        island_mask = island_id == label
        out[island_mask] = normalized[island_mask]
    return out.astype(np.float32)


def filter(
    image: np.ndarray,
    island_id: np.ndarray,
    sigma: float,
    *,
    sample_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Blur per UV island without cross-island bleed (GPU separable Gaussian)."""
    if sigma <= 0.0:
        return image.copy()
    if not gpu_runtime_available():
        raise RuntimeError("GPU runtime unavailable for blur_gpu.filter")

    valid = island_id >= 0
    work_id = _coalesce_island_ids(island_id, valid)
    height, width = image.shape[:2]
    use_mask = valid if sample_mask is None else valid & sample_mask

    if image.ndim == 2:
        return _blur_channel_gpu(image, work_id, use_mask, sigma, width=width, height=height)

    channels = []
    for axis in range(image.shape[-1]):
        channels.append(
            _blur_channel_gpu(
                image[..., axis],
                work_id,
                use_mask,
                sigma,
                width=width,
                height=height,
            )
        )
    return np.stack(channels, axis=-1)


island_gaussian_blur = filter

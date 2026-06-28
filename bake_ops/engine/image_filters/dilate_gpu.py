"""GPU nearest-valid RGBA dilation matching the dilate_cpu 4-connected BFS fill.

Parity policy: ``dilate_cpu`` implements one algorithm — 4-connected BFS
(`dilate_rgba_nearest`) — for every case, including the infinite "fill to image
bounds" case (which simply runs ``max(width, height)`` iterations). The GPU
backend mirrors that single algorithm so CPU/GPU stay pixel-exact (see
``bake-engine-cpu-gpu-parity.mdc``). A Euclidean jump-flood fill is intentionally
*not* used here because it diverges from the CPU Manhattan BFS at region
boundaries and could never satisfy the pixel-exact parity gate.
"""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    FullscreenOffscreenSession,
    gpu_runtime_available,
    upload_rgba_texture,
)
from lks_baker.bake_ops.engine.image_filters import dilate_cpu
from lks_baker.bake_ops.engine.image_filters._gpu_helpers import upload_mask_texture
from lks_baker.bake_ops.engine.image_filters.dilate_cpu import DilateConfig
from lks_baker.bake_ops.engine.image_filters.shaders import (
    DILATE_COLOR_PASS_FRAG,
    DILATE_VALID_PASS_FRAG,
    FULLSCREEN_VERT,
)

_COLOR_PUSH: tuple[tuple[str, str, int], ...] = (
    ("FLOAT", "dilateAlpha", 0),
    ("FLOAT", "fillPhase", 0),
)
_COLOR_SAMPLERS: tuple[str, ...] = ("colorTex", "validTex", "footprintTex")
_VALID_PUSH: tuple[tuple[str, str, int], ...] = (("FLOAT", "fillPhase", 0),)
_VALID_SAMPLERS: tuple[str, ...] = ("validTex", "footprintTex")


def _dilate_rgba_bfs_gpu(
    rgba: np.ndarray,
    valid: np.ndarray,
    iterations: int,
    *,
    width: int,
    height: int,
    dilate_alpha: bool = False,
    fill_footprint: np.ndarray | None = None,
) -> np.ndarray:
    """4-connected BFS dilate on GPU with ping-pong textures (one CPU readback).

    Two sessions per logical buffer are required so that each pass always
    renders into a different ``GPUOffScreen`` than the one whose ``texture_color``
    is being sampled. Using a single session would create an OpenGL feedback loop
    (read + write to the same FBO attachment), which produces grid/plaid
    corruption from stale GPU texture-cache tiles.

    The final result is read back via ``read_color_rgba`` (``GPUOffScreen``'s
    documented ``read_color`` path) — never ``GPUTexture.read()`` on the color
    attachment, which returns row-padded data and corrupts on reshape.
    """
    color_sessions = (
        FullscreenOffscreenSession(
            FULLSCREEN_VERT,
            DILATE_COLOR_PASS_FRAG,
            width,
            height,
            sampler_names=_COLOR_SAMPLERS,
            push_constants=_COLOR_PUSH,
        ),
        FullscreenOffscreenSession(
            FULLSCREEN_VERT,
            DILATE_COLOR_PASS_FRAG,
            width,
            height,
            sampler_names=_COLOR_SAMPLERS,
            push_constants=_COLOR_PUSH,
        ),
    )
    valid_sessions = (
        FullscreenOffscreenSession(
            FULLSCREEN_VERT,
            DILATE_VALID_PASS_FRAG,
            width,
            height,
            sampler_names=_VALID_SAMPLERS,
            push_constants=_VALID_PUSH,
        ),
        FullscreenOffscreenSession(
            FULLSCREEN_VERT,
            DILATE_VALID_PASS_FRAG,
            width,
            height,
            sampler_names=_VALID_SAMPLERS,
            push_constants=_VALID_PUSH,
        ),
    )
    try:
        color_tex = upload_rgba_texture(rgba)
        valid_tex = upload_mask_texture(valid)
        footprint_tex = upload_mask_texture(
            fill_footprint if fill_footprint is not None else np.ones((height, width), dtype=bool),
        )
        dilate_alpha_uniform = 1.0 if dilate_alpha else 0.0
        last_color_session = color_sessions[0]
        phase1_iters = max(width, height) if fill_footprint is not None else 0
        ring = 0
        ran_pass = False
        for phase, phase_iters in ((1.0, phase1_iters), (0.0, iterations)):
            if phase_iters <= 0:
                continue
            for _ in range(phase_iters):
                dst = ring % 2
                ring += 1
                ran_pass = True
                last_color_session = color_sessions[dst]
                color_tex = last_color_session.draw_gpu_color_texture(
                    {"dilateAlpha": dilate_alpha_uniform, "fillPhase": phase},
                    {
                        "colorTex": color_tex,
                        "validTex": valid_tex,
                        "footprintTex": footprint_tex,
                    },
                )
                valid_tex = valid_sessions[dst].draw_gpu_color_texture(
                    {"fillPhase": phase},
                    {"validTex": valid_tex, "footprintTex": footprint_tex},
                )
        if not ran_pass:
            return rgba.astype(np.float32, copy=True)
        return last_color_session.read_color_rgba()
    finally:
        for s in (*color_sessions, *valid_sessions):
            s.free()


def filter(
    image: np.ndarray,
    *,
    mask: np.ndarray | None = None,
    fill_footprint: np.ndarray | None = None,
    config: DilateConfig | None = None,
) -> np.ndarray:
    """Dilate edge colors into empty mask pixels without averaging (GPU)."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU runtime unavailable for dilate_gpu.filter")

    cfg = config or DilateConfig()
    rgba, _ = dilate_cpu.prepare_rgba_and_valid(
        image,
        None if fill_footprint is not None else mask,
        cfg,
    )
    height, width = rgba.shape[:2]
    iterations = dilate_cpu.resolve_dilate_iterations(cfg.dilate_pixels, width, height)
    footprint: np.ndarray | None = None
    if fill_footprint is not None:
        footprint = dilate_cpu.binary_mask_from_grayscale(
            fill_footprint,
            threshold=cfg.mask_threshold,
        )
        valid = dilate_cpu.resolve_dilate_seed_mask(footprint, cfg)
    elif mask is not None:
        footprint = dilate_cpu.binary_mask_from_grayscale(mask, threshold=cfg.mask_threshold)
        valid = dilate_cpu.resolve_dilate_seed_mask(footprint, cfg)
    else:
        valid = dilate_cpu.adjust_valid_mask(
            dilate_cpu.binary_mask_from_rgba(
                rgba,
                threshold=cfg.mask_threshold,
                valid_epsilon=cfg.valid_epsilon,
            ),
            cfg.margin_adjust,
        )

    out_rgba = _dilate_rgba_bfs_gpu(
        rgba,
        valid,
        iterations,
        width=width,
        height=height,
        dilate_alpha=cfg.dilate_alpha,
        fill_footprint=footprint,
    )
    return dilate_cpu.restore_output_channels(out_rgba, image)


edge_dilate = filter

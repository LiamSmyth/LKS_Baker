"""Island-aware RGBA dilation for baked map padding via engine image_filters."""

from __future__ import annotations

from array import array
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np

from ..engine.static_utilities.images import (
    blender_pixels_to_png_rows,
    png_rows_to_blender_pixels,
)

if TYPE_CHECKING:
    from lks_baker.bake_ops.engine.image_filters.dilate_cpu import DilateConfig

_VALID_EPSILON = 1e-4
_GPU_DILATE_MAX_ITERATIONS = 64


def _can_spread_from_neighbor(
    island_buf: array | None,
    width: int,
    target_idx: int,
    neighbor_idx: int,
) -> bool:
    """True when neighbor color may influence target (shared island rules for dilate/AA)."""
    if island_buf is None:
        return True
    target_island = island_buf[target_idx]
    neighbor_island = island_buf[neighbor_idx]
    if neighbor_island < 0 and target_island >= 0:
        return False
    if target_island >= 0 and neighbor_island >= 0:
        return target_island == neighbor_island
    return True


def _select_dilate_filter(*, use_gpu: bool, iterations: int = 0) -> Callable[..., np.ndarray]:
    if use_gpu:
        from lks_baker.bake_ops.engine.gpu.gpu_runtime import gpu_runtime_available
        from lks_baker.bake_ops.engine.image_filters import dilate_filter_gpu

        if gpu_runtime_available():
            return dilate_filter_gpu
    from lks_baker.bake_ops.engine.image_filters import dilate_filter

    return dilate_filter


def _island_flat_to_2d(
    island_buf: array | None,
    width: int,
    height: int,
    *,
    blender_pixel_order: bool,
) -> np.ndarray | None:
    if island_buf is None or len(island_buf) != width * height:
        return None
    island_2d = np.asarray(island_buf, dtype=np.int32).reshape(height, width)
    if blender_pixel_order:
        return np.flipud(island_2d)
    return island_2d


def _read_image_rgba_png_rows(image) -> tuple[np.ndarray, int, int]:
    width, height = int(image.size[0]), int(image.size[1])
    if width <= 0 or height <= 0:
        raise ValueError(f'image has invalid size {width}x{height}')
    flat = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(flat)
    rgba = blender_pixels_to_png_rows(flat.reshape(height, width, 4))
    return rgba, width, height


def _write_image_rgba_png_rows(image, rgba: np.ndarray, width: int, height: int) -> None:
    flat = png_rows_to_blender_pixels(rgba)
    image.pixels.foreach_set(flat)
    image.update()


def dilate_rgba_array(
    rgba: np.ndarray,
    *,
    config: DilateConfig,
    island_buf: array | None = None,
    width: int | None = None,
    height: int | None = None,
    use_gpu: bool = True,
    blender_pixel_order: bool = False,
) -> np.ndarray:
    """Dilate H×W×4 float RGBA using one shared coverage footprint."""
    from lks_baker.bake_ops.engine.image_filters.dilate_cpu import (
        resolve_dilate_iterations,
    )

    if rgba.ndim != 3 or rgba.shape[-1] < 4:
        raise ValueError(f'expected H×W×4 rgba, got {rgba.shape}')

    height, width = rgba.shape[:2]
    if width <= 0 or height <= 0:
        return rgba.astype(np.float32, copy=True)

    island_2d = _island_flat_to_2d(
        island_buf,
        width,
        height,
        blender_pixel_order=blender_pixel_order,
    )
    out = rgba.astype(np.float32, copy=True)
    dilate_fn = _select_dilate_filter(
        use_gpu=use_gpu,
        iterations=resolve_dilate_iterations(config.dilate_pixels, width, height),
    )

    if island_2d is not None:
        coverage = island_2d >= 0
        return dilate_fn(
            out,
            fill_footprint=coverage.astype(np.float32),
            config=config,
        )

    return dilate_fn(out, config=config)


def dilate_rgba_buffer(
    pixels: array,
    width: int,
    height: int,
    *,
    iterations: int,
    island_buf: array | None = None,
    valid_epsilon: float = _VALID_EPSILON,
) -> array:
    """Expand valid RGBA texels into empty padding using the shared coverage mask."""
    from lks_baker.bake_ops.engine.image_filters.dilate_cpu import DilateConfig

    if iterations <= 0 or width <= 0 or height <= 0:
        return array('f', pixels)

    flat = np.asarray(pixels, dtype=np.float32).reshape(height, width, 4)
    config = DilateConfig(dilate_pixels=iterations, dilate_alpha=True)
    dilated = dilate_rgba_array(
        flat,
        config=config,
        island_buf=island_buf,
        width=width,
        height=height,
        use_gpu=False,
        blender_pixel_order=False,
    )
    return array('f', dilated.reshape(-1).tolist())


def dilate_bake_image(
    image,
    *,
    margin_pixels: int | None = None,
    island_buf: array | None = None,
    config: DilateConfig | None = None,
    use_gpu: bool = True,
) -> None:
    """Dilate baked map padding in-place on a Blender image datablock."""
    from lks_baker.bake_ops.engine.image_filters.dilate_cpu import DilateConfig

    rgba, width, height = _read_image_rgba_png_rows(image)
    if config is None:
        if margin_pixels is None or margin_pixels == 0:
            return
        config = DilateConfig(dilate_pixels=margin_pixels, dilate_alpha=True)
    dilated = dilate_rgba_array(
        rgba,
        config=config,
        island_buf=island_buf,
        width=width,
        height=height,
        use_gpu=use_gpu,
        blender_pixel_order=True,
    )
    _write_image_rgba_png_rows(image, dilated, width, height)

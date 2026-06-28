"""Nearest-valid RGBA dilation for UV padding / mip bleed margins."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

_DEFAULT_MASK_THRESHOLD = 0.5
_DEFAULT_VALID_EPSILON = 1e-4
_NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = ((0, -1), (0, 1), (-1, 0), (1, 0))


@dataclass(frozen=True)
class DilateConfig:
    """Controls mask prep and nearest-color dilation radius."""

    dilate_pixels: int = 16
    """Pixels to grow edge color into empty mask; negative values (``-1``) fill until image bounds."""
    margin_adjust: int = 0
    """Morph pre-pass on the binary mask (4-connected): negative erodes, positive dilates."""
    mask_threshold: float = _DEFAULT_MASK_THRESHOLD
    """Grayscale / alpha values above this are treated as in-mask."""
    valid_epsilon: float = _DEFAULT_VALID_EPSILON
    """RGBA valid fallback when alpha is low but RGB is non-zero."""
    dilate_alpha: bool = False
    """When True, expand alpha with color; when False, only RGB is filled outward."""


def resolve_dilate_iterations(dilate_pixels: int, width: int, height: int) -> int:
    """Return BFS iteration count; ``dilate_pixels < 0`` (i.e. ``-1``) uses ``max(width, height)``."""
    if dilate_pixels < 0:
        return max(width, height)
    return int(dilate_pixels)


def binary_mask_from_rgba(
    rgba: np.ndarray,
    *,
    threshold: float = _DEFAULT_MASK_THRESHOLD,
    valid_epsilon: float = _DEFAULT_VALID_EPSILON,
) -> np.ndarray:
    """Derive a binary in-mask field from RGBA (alpha primary, RGB fallback).

    Normal bakes often ship with uniform alpha (typically 1.0) while padding stays
    black; in that case alpha alone would mark the whole image valid and block
    dilation. When alpha does not vary, non-black RGB is required. When alpha
    mixes hits and misses (AO, position), alpha is authoritative and black texels
    with alpha=1 remain valid (fully occluded AO).
    """
    alpha = rgba[..., 3]
    rgb_max = np.max(rgba[..., :3], axis=-1)
    alpha_valid = alpha > threshold
    color_valid = rgb_max > valid_epsilon
    if bool(np.any(~alpha_valid)) and bool(np.any(alpha_valid)):
        return alpha_valid | (color_valid & ~alpha_valid)
    return color_valid


def binary_mask_from_grayscale(
    mask: np.ndarray,
    *,
    threshold: float = _DEFAULT_MASK_THRESHOLD,
) -> np.ndarray:
    """Threshold a grayscale mask to boolean."""
    return mask.astype(np.float32) > threshold


def adjust_valid_mask(valid: np.ndarray, margin_adjust: int) -> np.ndarray:
    """Morphologically erode (negative) or dilate (positive) a binary mask."""
    if margin_adjust == 0:
        return valid.copy()
    out = valid.astype(bool, copy=True)
    steps = abs(int(margin_adjust))
    erode = margin_adjust < 0
    for _ in range(steps):
        out = _morph_mask_step(out, erode=erode)
    return out


def resolve_dilate_seed_mask(
    footprint: np.ndarray,
    config: DilateConfig,
) -> np.ndarray:
    """Build the eroded seed mask from a coverage footprint and ``margin_adjust``.

    Seed colors come only from texels inside this mask (TBN island hit, explicit
    dilate mask, or alpha-derived valid when no footprint is supplied upstream).
    When erosion would empty the mask, the un-eroded footprint is used instead.
    """
    seed_base = footprint.astype(bool, copy=True)
    eroded = adjust_valid_mask(seed_base, config.margin_adjust)
    if not np.any(eroded):
        return seed_base
    return eroded


def prepare_rgba_and_valid(
    image: np.ndarray,
    mask: np.ndarray | None,
    config: DilateConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Promote input to H×W×4 float32 and build the binary valid mask."""
    if image.ndim == 2:
        rgba = np.zeros((*image.shape, 4), dtype=np.float32)
        rgba[..., 0] = image.astype(np.float32, copy=False)
        rgba[..., 3] = 1.0
        if mask is None:
            raise ValueError("scalar image requires an explicit mask")
        valid = binary_mask_from_grayscale(mask, threshold=config.mask_threshold)
    elif image.shape[-1] >= 4:
        rgba = np.array(image[..., :4], dtype=np.float32, copy=True)
        valid = (
            binary_mask_from_grayscale(mask, threshold=config.mask_threshold)
            if mask is not None
            else binary_mask_from_rgba(
                rgba,
                threshold=config.mask_threshold,
                valid_epsilon=config.valid_epsilon,
            )
        )
    elif image.shape[-1] == 3:
        rgba = np.ones((*image.shape[:2], 4), dtype=np.float32)
        rgba[..., :3] = image.astype(np.float32, copy=False)
        if mask is None:
            raise ValueError("RGB image requires an explicit mask")
        valid = binary_mask_from_grayscale(mask, threshold=config.mask_threshold)
    else:
        raise ValueError(f"unsupported image shape: {image.shape}")

    if valid.shape != rgba.shape[:2]:
        raise ValueError(f"mask shape {valid.shape} must match image {rgba.shape[:2]}")
    return rgba, valid


def dilate_rgba_nearest(
    rgba: np.ndarray,
    valid: np.ndarray,
    iterations: int,
    *,
    fill_footprint: np.ndarray | None = None,
    dilate_alpha: bool = False,
) -> np.ndarray:
    """Spread nearest in-mask RGBA outward one pixel per iteration (4-connected BFS).

    When ``fill_footprint`` is set, phase 1 fills every texel inside the footprint
    from the eroded *valid* seed before phase 2 expands ``iterations`` rings into
    padding. That overwrites aliased UV rim texels still inside the island.

    When ``dilate_alpha`` is False, only RGB is copied into invalid pixels; alpha stays
    at its original value (typically 0 outside the mask). When True, the full RGBA sample
    is copied so alpha expands with the valid region.
    """
    height, width = valid.shape
    out = rgba.astype(np.float32, copy=True)
    valid_work = valid.astype(bool, copy=True)
    footprint: np.ndarray | None = None
    if fill_footprint is not None:
        footprint = fill_footprint.astype(bool, copy=False)
        if footprint.shape != valid.shape:
            raise ValueError(
                f'fill_footprint shape {footprint.shape} must match valid {valid.shape}',
            )
        _dilate_bfs_ring(
            out,
            valid_work,
            max(width, height),
            dilate_alpha=dilate_alpha,
            write_mask=footprint,
        )
    if iterations <= 0:
        return out
    _dilate_bfs_ring(
        out,
        valid_work,
        iterations,
        dilate_alpha=dilate_alpha,
        write_mask=None,
    )
    return out


def has_dilate_frontier(valid: np.ndarray) -> bool:
    """Return True when invalid pixels border valid ones (another BFS pass may fill)."""
    valid_bool = valid.astype(bool, copy=False)
    padded = np.pad(valid_bool, 1, mode="constant", constant_values=False)
    invalid = ~valid_bool
    neighbor_valid = (
        padded[1:-1, :-2]
        | padded[1:-1, 2:]
        | padded[:-2, 1:-1]
        | padded[2:, 1:-1]
    )
    return bool(np.any(invalid & neighbor_valid))


def filter(
    image: np.ndarray,
    *,
    mask: np.ndarray | None = None,
    fill_footprint: np.ndarray | None = None,
    config: DilateConfig | None = None,
) -> np.ndarray:
    """Dilate edge colors into empty mask pixels without averaging."""
    cfg = config or DilateConfig()
    rgba, _ = prepare_rgba_and_valid(image, None if fill_footprint is not None else mask, cfg)
    height, width = rgba.shape[:2]
    iterations = resolve_dilate_iterations(cfg.dilate_pixels, width, height)
    if fill_footprint is not None:
        footprint = binary_mask_from_grayscale(
            fill_footprint,
            threshold=cfg.mask_threshold,
        )
        seed = resolve_dilate_seed_mask(footprint, cfg)
        out_rgba = dilate_rgba_nearest(
            rgba,
            seed,
            iterations,
            fill_footprint=footprint,
            dilate_alpha=cfg.dilate_alpha,
        )
    elif mask is not None:
        footprint = binary_mask_from_grayscale(mask, threshold=cfg.mask_threshold)
        seed = resolve_dilate_seed_mask(footprint, cfg)
        out_rgba = dilate_rgba_nearest(
            rgba,
            seed,
            iterations,
            fill_footprint=footprint,
            dilate_alpha=cfg.dilate_alpha,
        )
    else:
        valid = adjust_valid_mask(
            binary_mask_from_rgba(
                rgba,
                threshold=cfg.mask_threshold,
                valid_epsilon=cfg.valid_epsilon,
            ),
            cfg.margin_adjust,
        )
        out_rgba = dilate_rgba_nearest(
            rgba,
            valid,
            iterations,
            dilate_alpha=cfg.dilate_alpha,
        )
    return restore_output_channels(out_rgba, image)


def restore_output_channels(out_rgba: np.ndarray, source: np.ndarray) -> np.ndarray:
    if source.ndim == 2:
        return out_rgba[..., 0].astype(np.float32, copy=False)
    if source.shape[-1] >= 4:
        result = np.array(source, dtype=np.float32, copy=True)
        result[..., :4] = out_rgba
        return result
    if source.shape[-1] == 3:
        return out_rgba[..., :3].astype(np.float32, copy=False)
    raise ValueError(f"unsupported source shape: {source.shape}")


def _morph_mask_step(valid: np.ndarray, *, erode: bool) -> np.ndarray:
    padded = np.pad(valid, 1, mode="constant", constant_values=False)
    center = padded[1:-1, 1:-1]
    left = padded[1:-1, :-2]
    right = padded[1:-1, 2:]
    up = padded[:-2, 1:-1]
    down = padded[2:, 1:-1]
    if erode:
        return center & left & right & up & down
    return center | left | right | up | down


def _seed_frontier(valid: np.ndarray) -> deque[tuple[int, int]]:
    height, width = valid.shape
    frontier: deque[tuple[int, int]] = deque()
    for y in range(height):
        for x in range(width):
            if not valid[y, x]:
                continue
            for dy, dx in _NEIGHBOR_OFFSETS:
                ny = y + dy
                nx = x + dx
                if ny < 0 or ny >= height or nx < 0 or nx >= width:
                    continue
                if valid[ny, nx]:
                    continue
                frontier.append((y, x))
                break
    return frontier


def _dilate_bfs_ring(
    out: np.ndarray,
    valid_work: np.ndarray,
    iterations: int,
    *,
    dilate_alpha: bool,
    write_mask: np.ndarray | None,
) -> None:
    """Expand ``valid_work`` up to *iterations* rings, optionally gated by *write_mask*."""
    if iterations <= 0:
        return
    height, width = valid_work.shape
    frontier = _seed_frontier(valid_work)
    for _ in range(iterations):
        if not frontier:
            break
        if write_mask is not None and not np.any(write_mask & ~valid_work):
            break
        next_frontier: deque[tuple[int, int]] = deque()
        for src_y, src_x in frontier:
            for dy, dx in _NEIGHBOR_OFFSETS:
                ny = src_y + dy
                nx = src_x + dx
                if ny < 0 or ny >= height or nx < 0 or nx >= width:
                    continue
                if valid_work[ny, nx]:
                    continue
                if write_mask is not None and not write_mask[ny, nx]:
                    continue
                if dilate_alpha:
                    out[ny, nx] = out[src_y, src_x]
                else:
                    out[ny, nx, :3] = out[src_y, src_x, :3]
                valid_work[ny, nx] = True
                next_frontier.append((ny, nx))
        frontier = next_frontier


edge_dilate = filter

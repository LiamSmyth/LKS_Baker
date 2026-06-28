"""Island-aware edge-preserving antialiasing for baked map images."""

from __future__ import annotations

import math
from array import array

import bpy

from .bake_texture_dilate_helpers import _can_spread_from_neighbor

_NEIGHBOR_OFFSETS_3 = tuple(
    (ox, oy)
    for oy in (-1, 0, 1)
    for ox in (-1, 0, 1)
    if ox != 0 or oy != 0
)
_EDGE_GRADIENT_THRESHOLD = 0.12
_SPATIAL_SIGMA = 1.0
_RANGE_SIGMA = 0.06


def _luminance(r: float, g: float, b: float) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _gradient_magnitude(
    pixels: array,
    width: int,
    height: int,
    idx: int,
    *,
    island_buf: array | None,
) -> float:
    x = idx % width
    y = idx // width
    center = idx * 4
    center_lum = _luminance(pixels[center], pixels[center + 1], pixels[center + 2])
    max_delta = 0.0
    for ox, oy in _NEIGHBOR_OFFSETS_3:
        nx, ny = x + ox, y + oy
        if not (0 <= nx < width and 0 <= ny < height):
            continue
        nidx = ny * width + nx
        if not _can_spread_from_neighbor(island_buf, width, idx, nidx):
            continue
        base = nidx * 4
        neighbor_lum = _luminance(pixels[base], pixels[base + 1], pixels[base + 2])
        max_delta = max(max_delta, abs(neighbor_lum - center_lum))
    return max_delta


def antialias_rgba_buffer(
    pixels: array,
    width: int,
    height: int,
    *,
    island_buf: array | None = None,
    strength: float = 0.5,
    edge_gradient_threshold: float = _EDGE_GRADIENT_THRESHOLD,
    spatial_sigma: float = _SPATIAL_SIGMA,
    range_sigma: float = _RANGE_SIGMA,
) -> array:
    """Edge-aware bilateral smooth on interior texels; preserves high-gradient edges."""
    if width <= 0 or height <= 0 or strength <= 0.0:
        return array('f', pixels)

    count = width * height
    if island_buf is not None and len(island_buf) != count:
        island_buf = None

    strength = max(0.0, min(1.0, strength))
    spatial_denom = 2.0 * spatial_sigma * spatial_sigma
    range_denom = 2.0 * range_sigma * range_sigma

    out = array('f', pixels)
    for y in range(height):
        row_base = y * width
        for x in range(width):
            idx = row_base + x
            if island_buf is not None and island_buf[idx] < 0:
                continue
            if _gradient_magnitude(pixels, width, height, idx, island_buf=island_buf) > edge_gradient_threshold:
                continue

            center = idx * 4
            center_r = pixels[center]
            center_g = pixels[center + 1]
            center_b = pixels[center + 2]
            center_a = pixels[center + 3]
            center_lum = _luminance(center_r, center_g, center_b)

            acc_r = acc_g = acc_b = acc_a = 0.0
            weight_sum = 0.0
            for ox, oy in _NEIGHBOR_OFFSETS_3:
                nx, ny = x + ox, y + oy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                nidx = ny * width + nx
                if not _can_spread_from_neighbor(island_buf, width, idx, nidx):
                    continue
                dist_sq = float(ox * ox + oy * oy)
                base = nidx * 4
                nr = pixels[base]
                ng = pixels[base + 1]
                nb = pixels[base + 2]
                na = pixels[base + 3]
                lum_delta = _luminance(nr, ng, nb) - center_lum
                spatial_w = math.exp(-dist_sq / spatial_denom) if spatial_denom > 0.0 else 1.0
                range_w = math.exp(-(lum_delta * lum_delta) / range_denom) if range_denom > 0.0 else 1.0
                weight = spatial_w * range_w
                acc_r += nr * weight
                acc_g += ng * weight
                acc_b += nb * weight
                acc_a += na * weight
                weight_sum += weight

            if weight_sum <= 1e-8:
                continue

            blur_r = acc_r / weight_sum
            blur_g = acc_g / weight_sum
            blur_b = acc_b / weight_sum
            blur_a = acc_a / weight_sum
            dst = idx * 4
            out[dst] = center_r + (blur_r - center_r) * strength
            out[dst + 1] = center_g + (blur_g - center_g) * strength
            out[dst + 2] = center_b + (blur_b - center_b) * strength
            out[dst + 3] = center_a + (blur_a - center_a) * strength
    return out


def antialias_bake_image(
    image: bpy.types.Image,
    *,
    island_buf: array | None,
    width: int,
    height: int,
    strength: float = 0.5,
) -> None:
    """Apply island-aware edge-preserving AA in-place on a Blender image datablock."""
    if image.size[0] != width or image.size[1] != height:
        width, height = image.size[0], image.size[1]
    if width <= 0 or height <= 0:
        return
    pixels = array('f', [0.0] * (width * height * 4))
    image.pixels.foreach_get(pixels)
    filtered = antialias_rgba_buffer(
        pixels,
        width,
        height,
        island_buf=island_buf,
        strength=strength,
    )
    image.pixels.foreach_set(filtered)
    image.update()


def should_antialias_map_entry(map_entry) -> bool:
    """Gate antialias on per-map RNA flag (catalog eligibility is advisory only)."""
    return map_entry is not None and getattr(map_entry, 'lks_post_antialias', False)

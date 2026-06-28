"""Debug visualization for failed or discarded bake texels."""
from __future__ import annotations

import numpy as np

DEBUG_TEXEL_FAIL_RGB: tuple[float, float, float] = (1.0, 0.0, 1.0)
"""Fuchsia RGB for texels that failed to draw or were discarded from coverage."""

DEBUG_TEXEL_FAIL_GRAY: float = -1.0
"""Reserved packed sentinel (not used in production 0..1 maps); maps to fuchsia in debug PNGs."""


def settings_debug_texel_fail(settings: object) -> bool:
    """Return whether *settings* requests failed-texel debug coloring."""
    return bool(getattr(settings, "debug_texel_fail", False))


def resolve_coverage_mask(
    input_valid: np.ndarray,
    output_valid: np.ndarray | None = None,
) -> np.ndarray:
    """Return the authoritative per-texel coverage mask for a bake result."""
    if output_valid is not None and output_valid.shape[:2] == input_valid.shape[:2]:
        return output_valid
    return input_valid


def packed_to_debug_rgb(packed: np.ndarray, coverage_mask: np.ndarray) -> np.ndarray:
    """Build an H×W×3 RGB preview: valid texels grayscale, failed texels fuchsia."""
    gray = np.clip(packed.astype(np.float32, copy=False), 0.0, 1.0)
    rgb = np.stack([gray, gray, gray], axis=-1)
    fail = ~coverage_mask
    if np.any(fail):
        rgb = np.array(rgb, copy=True)
        rgb[fail] = DEBUG_TEXEL_FAIL_RGB
    return rgb


def apply_debug_texel_fail_mask(
    packed: np.ndarray,
    coverage_mask: np.ndarray,
    *,
    debug_texel_fail: bool,
) -> np.ndarray:
    """When debug is enabled, return H×W×3 RGB with failed texels fuchsia; else return *packed*."""
    if not debug_texel_fail:
        return packed
    return packed_to_debug_rgb(packed, coverage_mask)


def mark_debug_fail_sentinel(
    packed: np.ndarray,
    coverage_mask: np.ndarray,
    *,
    debug_texel_fail: bool,
) -> np.ndarray:
    """Copy *packed* and write ``DEBUG_TEXEL_FAIL_GRAY`` on ``~coverage_mask`` when debug is on."""
    if not debug_texel_fail:
        return packed
    out = np.array(packed, dtype=np.float32, copy=True)
    out[~coverage_mask] = DEBUG_TEXEL_FAIL_GRAY
    return out

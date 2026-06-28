"""Image I/O and map decoding (numpy + Pillow only)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from .coords import decode_normal_rgb, decode_position_rgb

MIN_INTERNAL_BIT_DEPTH: Literal[16] = 16
"""Minimum bit depth for internal bake buffers (policy: bake-engine-internal-bit-depth.mdc)."""

INTERNAL_BAKE_DTYPE = np.float32
"""Default numpy dtype for internal bake arrays after load/decode."""


def blender_pixels_to_png_rows(rgba: np.ndarray) -> np.ndarray:
    """Convert Blender ``Image.pixels`` layout to internal PNG rows (row 0 = UV top)."""
    return np.flipud(rgba.astype(INTERNAL_BAKE_DTYPE, copy=False))


def png_rows_to_blender_pixels(rgba: np.ndarray) -> np.ndarray:
    """Flatten internal PNG-row H×W×4 to Blender ``Image.pixels`` order (bottom row first)."""
    return np.flipud(rgba.astype(INTERNAL_BAKE_DTYPE, copy=False)).reshape(-1)


def load_rgba(path: str | Path) -> np.ndarray:
    """Load an image as float32 RGBA in 0..1 (≥16-bit internal storage after load)."""
    array = np.array(Image.open(path).convert("RGBA"))
    if array.dtype == np.uint16:
        return array.astype(INTERNAL_BAKE_DTYPE) / 65535.0
    return array.astype(INTERNAL_BAKE_DTYPE) / 255.0


def resize_rgba01(
    rgba: np.ndarray,
    width: int,
    height: int,
    *,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> np.ndarray:
    """Resize float RGBA in 0..1 without 8-bit quantization (float32 per channel)."""
    src_h, src_w = rgba.shape[:2]
    sample = np.clip(rgba[..., :4], 0.0, 1.0).astype(INTERNAL_BAKE_DTYPE, copy=False)
    if width == src_w and height == src_h:
        return sample

    channels = [
        np.asarray(
            Image.fromarray(sample[..., index], mode="F").resize((width, height), resample=resample),
            dtype=INTERNAL_BAKE_DTYPE,
        )
        for index in range(4)
    ]
    return np.stack(channels, axis=-1)


def maybe_downscale_rgba01(rgba: np.ndarray, max_size: int | None) -> np.ndarray:
    """Downscale longest edge to ``max_size`` while preserving ≥16-bit internal precision."""
    if max_size is None:
        return rgba.astype(INTERNAL_BAKE_DTYPE, copy=False)

    height, width = rgba.shape[:2]
    longest = max(height, width)
    if longest <= max_size:
        return rgba.astype(INTERNAL_BAKE_DTYPE, copy=False)

    scale = max_size / float(longest)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    return resize_rgba01(rgba, new_w, new_h)


def resize_field01(
    field: np.ndarray,
    width: int,
    height: int,
    *,
    nearest: bool = False,
) -> np.ndarray:
    """Resize a bake field (bool, H×W, or H×W×C float) without 8-bit vector quantization."""
    resample = Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS
    if field.dtype == bool:
        image = Image.fromarray(field.astype(np.uint8) * 255, mode="L")
        resized = image.resize((width, height), resample=resample)
        return np.asarray(resized, dtype=bool) > 0
    if field.ndim == 2:
        image = Image.fromarray(field.astype(INTERNAL_BAKE_DTYPE), mode="F")
        resized = image.resize((width, height), resample=resample)
        return np.asarray(resized, dtype=INTERNAL_BAKE_DTYPE)
    channels = int(field.shape[-1])
    if channels >= 4:
        return resize_rgba01(field, width, height, resample=resample)
    sample = np.clip(field[..., :3], 0.0, 1.0).astype(INTERNAL_BAKE_DTYPE, copy=False)
    rgb = [
        np.asarray(
            Image.fromarray(sample[..., index], mode="F").resize((width, height), resample=resample),
            dtype=INTERNAL_BAKE_DTYPE,
        )
        for index in range(3)
    ]
    return np.stack(rgb, axis=-1)


def save_rgba16(path: str | Path, rgba: np.ndarray) -> None:
    """Save H×W×4 float RGBA in 0..1 as 16-bit PNG (fixture / derivative source storage)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = np.clip(rgba[..., :4], 0.0, 1.0)
    out = (sample * 65535.0).astype(np.uint16)
    Image.fromarray(out, mode="RGBA").save(path)


def save_gray01(path: str | Path, gray: np.ndarray) -> None:
    """Save final packed grayscale output as 8-bit PNG (export step only).

    Args:
        path: Filesystem path.
        gray: H×W float32 grayscale in 0..1.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.clip(gray * 255.0, 0.0, 255.0).astype(np.uint8)
    Image.fromarray(out, mode="L").save(path)


def save_rgb01(path: str | Path, rgb: np.ndarray) -> None:
    """Save H×W×3 float RGB in 0..1 as an 8-bit PNG (export / debug preview only)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = np.clip(rgb * 255.0, 0.0, 255.0).astype(np.uint8)
    Image.fromarray(out, mode="RGB").save(path)


def save_bake_packed_png(
    path: str | Path,
    packed: np.ndarray,
    *,
    coverage_mask: np.ndarray | None = None,
    debug_texel_fail: bool = False,
) -> None:
    """Save packed bake output — grayscale in production, RGB fuchsia debug when requested."""
    from .debug_texels import apply_debug_texel_fail_mask

    if not debug_texel_fail or coverage_mask is None:
        save_gray01(path, packed)
        return

    preview = apply_debug_texel_fail_mask(packed, coverage_mask, debug_texel_fail=True)
    save_rgb01(path, preview)


def dilate_gray01_island(
    gray: np.ndarray,
    island_id: np.ndarray,
    *,
    margin_pixels: int,
) -> np.ndarray:
    """Expand gray values into empty padding without crossing UV islands."""
    if margin_pixels <= 0:
        return gray

    from array import array

    from ...static_utilities.bake_texture_dilate_helpers import dilate_rgba_buffer

    height, width = gray.shape[:2]
    count = width * height
    pixels = array("f", [0.0] * (count * 4))
    island_buf = array("i", [-1] * count)
    for idx in range(count):
        y, x = divmod(idx, width)
        label = int(island_id[y, x])
        island_buf[idx] = label
        base = idx * 4
        value = float(gray[y, x])
        if label >= 0:
            pixels[base : base + 3] = array("f", (value, value, value))
            pixels[base + 3] = 1.0

    dilated = dilate_rgba_buffer(
        pixels,
        width,
        height,
        iterations=margin_pixels,
        island_buf=island_buf,
    )
    out = np.array(gray, dtype=np.float32, copy=True)
    for idx in range(count):
        if island_buf[idx] < 0 and dilated[idx * 4 + 3] > 0.01:
            y, x = divmod(idx, width)
            out[y, x] = dilated[idx * 4]
    return out


def save_gray16(path: str | Path, gray: np.ndarray) -> None:
    """Save gray16.

    Args:
        path: Filesystem path.
        gray: H×W float32 grayscale in 0..1.
    """
    out = np.clip(gray * 65535.0, 0.0, 65535.0).astype(np.uint16)
    Image.fromarray(out, mode="I;16").save(path)


def decode_tangent_normal(rgba: np.ndarray) -> np.ndarray:
    """Decode tangent normal RGBA to internal ``InternalNormalSpace.TANGENT_OPENGL`` unit vectors."""
    return decode_normal_rgb(rgba[..., :3])


def decode_object_normal(rgba: np.ndarray) -> np.ndarray:
    """Decode object normal RGBA to internal ``InternalNormalSpace.OBJECT_BLENDER`` unit vectors."""
    return decode_normal_rgb(rgba[..., :3])


def decode_position(rgba: np.ndarray) -> np.ndarray:
    """Decode position RGBA to internal ``PositionSpace.OBJECT_BLENDER`` coordinates."""
    return decode_position_rgb(rgba[..., :3])


def alpha_valid_mask(rgba: np.ndarray, *, alpha_threshold: float = 0.01) -> np.ndarray:
    """True where bake alpha indicates a ray hit (Cycles authority)."""
    if rgba.shape[-1] >= 4:
        return rgba[..., 3] > alpha_threshold
    return np.ones(rgba.shape[:2], dtype=bool)


def valid_mask_from_rgba(rgba: np.ndarray, *, alpha_threshold: float = 0.01) -> np.ndarray:
    """Legacy mask: alpha minus flat default tangent RGB (padding heuristic).

    Do not use for curvature — flat tangent-space normals decode to (0.5, 0.5, 1.0)
    and would be wrongly excluded. Use ``resolve_bake_valid_mask`` instead.
    """
    alpha = alpha_valid_mask(rgba, alpha_threshold=alpha_threshold)
    flat_tangent = np.all(
        np.abs(rgba[..., :3] - np.array([0.5, 0.5, 1.0], dtype=np.float32)) < 0.02,
        axis=-1,
    )
    return alpha & (~flat_tangent)


def resolve_bake_valid_mask(
    normal_rgba: np.ndarray,
    object_rgba: np.ndarray | None = None,
    position_rgba: np.ndarray | None = None,
    *,
    alpha_threshold: float = 0.01,
) -> np.ndarray:
    """Valid texels for engine maps — prefer alpha from WSNM / position bakes.

    Tangent normal PNGs often ship with alpha=1 everywhere; object/position bakes
    carry the real ray-hit mask from Cycles.
    """
    if object_rgba is not None and object_rgba.shape[:2] == normal_rgba.shape[:2]:
        object_alpha = alpha_valid_mask(object_rgba, alpha_threshold=alpha_threshold)
        if int(object_alpha.sum()) > 0 and int((~object_alpha).sum()) > 0:
            return object_alpha
    if position_rgba is not None and position_rgba.shape[:2] == normal_rgba.shape[:2]:
        position_alpha = alpha_valid_mask(position_rgba, alpha_threshold=alpha_threshold)
        if int(position_alpha.sum()) > 0 and int((~position_alpha).sum()) > 0:
            return position_alpha
    return alpha_valid_mask(normal_rgba, alpha_threshold=alpha_threshold)


def find_map(bake_dir: Path, suffix: str) -> Path | None:
    """Find map.

    Args:
        bake_dir: Directory containing exported bake textures.
        suffix: ``str`` value.

    Returns:
        ``Path | None`` result.
    """
    matches = sorted(bake_dir.glob(f"*{suffix}*"))
    for path in matches:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"}:
            return path
    return None

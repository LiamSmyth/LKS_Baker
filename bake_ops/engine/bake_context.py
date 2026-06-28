"""Load bake textures from a directory into BakeMapInput fields."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .bake_map import BakeMapInput
from .image_filters.switch_normal_opengl_directx_cpu import filter as switch_normal_filter
from .settings.curvature_settings import CurvatureSettings
from .static_utilities.coords import TangentSpaceConvention
from .static_utilities.images import (
    decode_object_normal,
    decode_position,
    decode_tangent_normal,
    find_map,
    load_rgba,
    maybe_downscale_rgba01,
    resolve_bake_valid_mask,
)
from .static_utilities.islands import resolve_island_ids


@dataclass
class BakeContext:
    """Legacy-compatible context (same fields as BakeMapInput textures)."""

    valid: np.ndarray
    island_id: np.ndarray
    object_normal: np.ndarray
    position: np.ndarray
    object_rgba: np.ndarray
    position_rgba: np.ndarray
    tangent_normal: np.ndarray | None = None
    normal_rgba: np.ndarray | None = None


def _maybe_downscale(rgba: np.ndarray, max_size: int | None) -> np.ndarray:
    return maybe_downscale_rgba01(rgba, max_size)


def _ingest_tangent_normal_rgba(
    rgba: np.ndarray,
    *,
    tangent_normal_source: TangentSpaceConvention,
) -> np.ndarray:
    """Optional pre-decode ingest: remap external tangent normal RGB to internal OpenGL."""
    if tangent_normal_source is TangentSpaceConvention.OPENGL:
        return rgba
    return switch_normal_filter(
        rgba,
        from_convention=tangent_normal_source,
        to_convention=TangentSpaceConvention.OPENGL,
    )


def load_bake_context(
    bake_dir: str | Path,
    settings: CurvatureSettings,
    *,
    tangent_normal_source: TangentSpaceConvention = TangentSpaceConvention.OPENGL,
) -> BakeContext:
    """Load object normal / position textures from a bake directory into arrays.

    Args:
        bake_dir: Folder containing exported bake maps (``normal_object``, ``position``).
        settings: Optional ``max_size`` downscale only (no coordinate toggles).
        tangent_normal_source: External tangent normal encoding before canonical decode.

    Returns:
        ``BakeContext`` with decoded normals, position, valid mask, and island labels.

    Raises:
        FileNotFoundError: When ``normal_object`` is missing from ``bake_dir``.
    """
    bake_dir = Path(bake_dir)
    object_path = find_map(bake_dir, "normal_object")
    if object_path is None:
        raise FileNotFoundError(f"normal_object map not found in {bake_dir}")

    object_rgba = _maybe_downscale(load_rgba(object_path), settings.max_size)
    position_rgba = np.zeros_like(object_rgba)
    position_rgba[..., :3] = 0.5
    position_rgba[..., 3] = 1.0
    position_path = find_map(bake_dir, "position")
    if position_path is not None:
        position_rgba = _maybe_downscale(load_rgba(position_path), settings.max_size)

    normal_path = find_map(bake_dir, "normal")
    normal_rgba: np.ndarray | None = None
    tangent: np.ndarray | None = None
    if normal_path is not None:
        normal_rgba = _maybe_downscale(load_rgba(normal_path), settings.max_size)
        normal_rgba = _ingest_tangent_normal_rgba(
            normal_rgba,
            tangent_normal_source=tangent_normal_source,
        )
        tangent = decode_tangent_normal(normal_rgba)

    mask_rgba = object_rgba if normal_rgba is None else normal_rgba
    valid = resolve_bake_valid_mask(mask_rgba, object_rgba, position_rgba)
    object_normal = decode_object_normal(object_rgba)

    position = np.zeros_like(object_normal)
    if position_path is not None:
        position = decode_position(position_rgba)

    island_id = resolve_island_ids(valid, position, object_normal, tangent)

    return BakeContext(
        valid=valid,
        island_id=island_id,
        object_normal=object_normal,
        position=position,
        object_rgba=object_rgba,
        position_rgba=position_rgba,
        tangent_normal=tangent,
        normal_rgba=normal_rgba,
    )


def context_to_input(ctx: BakeContext, settings: CurvatureSettings, *, mesh=None, **extra) -> BakeMapInput:
    """Convert a legacy ``BakeContext`` into a ``BakeMapInput`` for ``BakeMap.bake``."""
    return BakeMapInput(
        valid=ctx.valid,
        island_id=ctx.island_id,
        tangent_normal=ctx.tangent_normal,
        object_normal=ctx.object_normal,
        position=ctx.position,
        normal_rgba=ctx.normal_rgba,
        object_rgba=ctx.object_rgba,
        position_rgba=ctx.position_rgba,
        mesh=mesh,
        image_size=int(ctx.valid.shape[0]),
        settings=settings,
        extra=extra,
    )

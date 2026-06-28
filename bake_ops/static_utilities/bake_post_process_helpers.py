"""Canonical post-bake antialias and denoise application for all bake backends."""
from __future__ import annotations

from array import array
from typing import TYPE_CHECKING

from .bake_antialias_helpers import antialias_bake_image, should_antialias_map_entry
from .bake_denoise_helpers import denoise_bake_image, should_denoise_map_entry
from .bake_map_catalog import EDGE_SENSITIVE_MAP_IDS, get_bake_map_spec, is_edge_sensitive_map

if TYPE_CHECKING:
    import bpy

    from .bake_map_catalog import LKS_BakeMapSpec


def apply_map_post_process(
    image: bpy.types.Image,
    map_entry,
    *,
    map_id: str | None = None,
    spec: LKS_BakeMapSpec | None = None,
    island_buf: array | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Apply optional antialias and denoise to a baked image (after dilate)."""
    resolved_map_id = map_id or (map_entry.map_id if map_entry is not None else None)
    resolved_spec = spec if spec is not None else (
        get_bake_map_spec(resolved_map_id) if resolved_map_id else None
    )
    if width is None or height is None:
        width = int(image.size[0])
        height = int(image.size[1])

    if should_antialias_map_entry(map_entry):
        strength = float(getattr(map_entry, 'lks_post_antialias_strength', 0.5))
        antialias_bake_image(
            image,
            island_buf=island_buf,
            width=width,
            height=height,
            strength=strength,
        )

    if (
        map_entry is not None
        and resolved_spec is not None
        and should_denoise_map_entry(map_entry, resolved_spec.map_id)
    ):
        denoise_bake_image(image, map_id=resolved_spec.map_id)

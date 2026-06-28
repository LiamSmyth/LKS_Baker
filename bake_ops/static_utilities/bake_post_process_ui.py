"""Shared gear-popup Post-process section for all bake map entries."""
from __future__ import annotations

from typing import Any

from .bake_map_catalog import EDGE_SENSITIVE_MAP_IDS, is_edge_sensitive_map


def draw_bake_post_process_settings(layout: Any, entry: Any) -> None:
    """Draw map-level antialias and denoise toggles below method settings."""
    box = layout.box()
    box.label(text='Post-process', icon='IMAGE_DATA')
    box.prop(entry, 'lks_post_antialias', text='Antialias')
    if entry.lks_post_antialias:
        box.prop(entry, 'lks_post_antialias_strength', text='Strength')
    box.prop(entry, 'lks_post_denoise', text='Denoise')
    if is_edge_sensitive_map(entry.map_id):
        box.label(text='AA/denoise may soften edges on this map', icon='INFO')

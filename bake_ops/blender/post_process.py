"""Post-bake dilate, AA, and denoise — canonical helpers and re-exports."""
from __future__ import annotations

from ..static_utilities.bake_antialias_helpers import antialias_bake_image, should_antialias_map_entry
from ..static_utilities.bake_denoise_helpers import denoise_bake_image, should_denoise_map_entry
from ..static_utilities.bake_map_catalog import EDGE_SENSITIVE_MAP_IDS, is_edge_sensitive_map
from ..static_utilities.bake_post_process_helpers import apply_map_post_process
from ..static_utilities.bake_texture_dilate_helpers import dilate_bake_image

__all__ = [
    'antialias_bake_image',
    'apply_map_post_process',
    'dilate_bake_image',
    'denoise_bake_image',
    'EDGE_SENSITIVE_MAP_IDS',
    'is_edge_sensitive_map',
    'should_antialias_map_entry',
    'should_denoise_map_entry',
]

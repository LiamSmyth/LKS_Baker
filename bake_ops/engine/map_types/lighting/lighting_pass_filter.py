"""COMBINED bake pass-filter configuration for catalog lighting maps."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_baker.bake_ops.static_utilities.bake_map_catalog import (
    BAKE_MAP_LIGHTING_IDS,
    LKS_BakeMapSpec,
    get_bake_map_spec,
)

if TYPE_CHECKING:
    import bpy


def resolve_lighting_pass_filter(map_id: str, *, spec: LKS_BakeMapSpec | None = None) -> frozenset[str]:
    """Return the COMBINED pass-filter set for a lighting catalog *map_id*."""
    resolved = spec if spec is not None else get_bake_map_spec(map_id)
    if resolved is None or resolved.pass_filter is None:
        raise ValueError(f'lighting map {map_id!r} has no pass_filter in catalog')
    return resolved.pass_filter


def apply_combined_pass_filter(scene: bpy.types.Scene, pass_filter: frozenset[str]) -> None:
    """Configure ``scene.render.bake`` pass flags for a COMBINED lighting bake."""
    bake = scene.render.bake
    bake.use_pass_direct = 'DIRECT' in pass_filter
    bake.use_pass_indirect = 'INDIRECT' in pass_filter
    bake.use_pass_diffuse = 'DIFFUSE' in pass_filter
    bake.use_pass_glossy = 'GLOSSY' in pass_filter
    bake.use_pass_transmission = 'TRANSMISSION' in pass_filter
    bake.use_pass_color = False
    bake.use_pass_emit = False


def is_lighting_map_id(map_id: str) -> bool:
    return map_id in BAKE_MAP_LIGHTING_IDS


def uses_cycles_combined_backend(spec: LKS_BakeMapSpec) -> bool:
    return spec.blender_backend == 'cycles_combined' and spec.cycles_type == 'COMBINED'

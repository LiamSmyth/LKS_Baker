"""Collect registered Cycles COMBINED lighting ``BakeMap`` implementations."""
from __future__ import annotations

from typing import Type

from lks_baker.bake_ops.engine.bake_map import BakeMap
from lks_baker.bake_ops.engine.blender_bake.blender_cycles_map import (
    make_blender_cycles_bake_map,
)
from lks_baker.bake_ops.static_utilities.bake_map_catalog import (
    BAKE_MAP_LIGHTING_IDS,
)

CompleteLightingBlenderBake = make_blender_cycles_bake_map('complete_lighting')
DiffuseLightingBlenderBake = make_blender_cycles_bake_map('diffuse_lighting')
SpecularLightingBlenderBake = make_blender_cycles_bake_map('specular_lighting')
IndirectLightingBlenderBake = make_blender_cycles_bake_map('indirect_lighting')

LIGHTING_BLENDER_BAKE_MAPS: tuple[Type[BakeMap], ...] = (
    CompleteLightingBlenderBake,
    DiffuseLightingBlenderBake,
    SpecularLightingBlenderBake,
    IndirectLightingBlenderBake,
)

assert {cls.map_type for cls in LIGHTING_BLENDER_BAKE_MAPS} == set(BAKE_MAP_LIGHTING_IDS)

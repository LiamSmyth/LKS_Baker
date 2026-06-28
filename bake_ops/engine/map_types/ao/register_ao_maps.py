"""Collect registered AO ``BakeMap`` implementations."""
from __future__ import annotations

from typing import Type

from lks_baker.bake_ops.engine.bake_map import BakeMap
from lks_baker.bake_ops.engine.map_types.ao.ao_composite_cpu import AoCompositeCpu
from lks_baker.bake_ops.engine.map_types.ao.atlas_hbao_cpu import AtlasHbaoCpu
from lks_baker.bake_ops.engine.map_types.ao.height_hbao_cpu import HeightHbaoCpu
from lks_baker.bake_ops.engine.map_types.ao.normal_cavity_cpu import NormalCavityCpu
from lks_baker.bake_ops.engine.map_types.ao.normal_height_hbao_cpu import NormalHeightHbaoCpu

AO_BAKE_MAPS: tuple[Type[BakeMap], ...] = (
    NormalCavityCpu,
    AoCompositeCpu,
    AtlasHbaoCpu,
    NormalHeightHbaoCpu,
    HeightHbaoCpu,
)

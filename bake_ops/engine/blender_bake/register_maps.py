"""Collect all registered Blender Cycles builtin bake map classes."""
from __future__ import annotations

from typing import Type

from lks_baker.bake_ops.engine.bake_map import BakeMap
from lks_baker.bake_ops.engine.map_types.albedo.blender_bake import AlbedoBlenderBake
from lks_baker.bake_ops.engine.map_types.ao.blender_bake import AoBlenderBake
from lks_baker.bake_ops.engine.map_types.emissive.blender_bake import EmissiveBlenderBake
from lks_baker.bake_ops.engine.map_types.material_id.blender_bake import MaterialIdBlenderBake
from lks_baker.bake_ops.engine.map_types.lighting.register_lighting_maps import (
    LIGHTING_BLENDER_BAKE_MAPS,
)
from lks_baker.bake_ops.engine.map_types.metalness.blender_bake import MetalnessBlenderBake
from lks_baker.bake_ops.engine.map_types.normal.blender_bake import NormalBlenderBake
from lks_baker.bake_ops.engine.map_types.normal_object.blender_bake import NormalObjectBlenderBake
from lks_baker.bake_ops.engine.map_types.object_id.blender_bake import ObjectIdBlenderBake
from lks_baker.bake_ops.engine.map_types.position.blender_bake import PositionBlenderBake
from lks_baker.bake_ops.engine.map_types.roughness.blender_bake import RoughnessBlenderBake
from lks_baker.bake_ops.engine.map_types.specular.blender_bake import SpecularBlenderBake
from lks_baker.bake_ops.engine.map_types.transparency.blender_bake import TransparencyBlenderBake
from lks_baker.bake_ops.engine.map_types.vertex_color.blender_bake import VertexColorBlenderBake

BLENDER_BUILTIN_BAKE_MAPS: tuple[Type[BakeMap], ...] = (
    NormalBlenderBake,
    NormalObjectBlenderBake,
    PositionBlenderBake,
    AoBlenderBake,
    RoughnessBlenderBake,
    AlbedoBlenderBake,
    SpecularBlenderBake,
    MetalnessBlenderBake,
    EmissiveBlenderBake,
    TransparencyBlenderBake,
    VertexColorBlenderBake,
    MaterialIdBlenderBake,
    ObjectIdBlenderBake,
    *LIGHTING_BLENDER_BAKE_MAPS,
)

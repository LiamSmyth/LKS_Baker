"""Blender Cycles builtin bake for the ``emissive`` catalog map."""
from __future__ import annotations

from lks_baker.bake_ops.engine.blender_bake.blender_cycles_map import make_blender_cycles_bake_map

EmissiveBlenderBake = make_blender_cycles_bake_map("emissive")

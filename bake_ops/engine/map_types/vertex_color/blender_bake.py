"""Blender Cycles builtin bake for the ``vertex_color`` catalog map."""
from __future__ import annotations

from lks_baker.bake_ops.engine.blender_bake.blender_cycles_map import make_blender_cycles_bake_map

VertexColorBlenderBake = make_blender_cycles_bake_map("vertex_color")

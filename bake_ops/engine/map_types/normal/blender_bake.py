"""Blender Cycles builtin bake for the ``normal`` catalog map."""
from __future__ import annotations

from lks_baker.bake_ops.engine.blender_bake.blender_cycles_map import make_blender_cycles_bake_map

NormalBlenderBake = make_blender_cycles_bake_map("normal")

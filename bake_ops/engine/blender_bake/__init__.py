"""Blender Cycles builtin bakes — shared engine path for native ``bpy.ops.object.bake``."""
from __future__ import annotations

from .blender_bake_context import BlenderBakeExecutionContext
from .catalog import (
    BLENDER_BUILTIN_DEVICE,
    BLENDER_BUILTIN_MAP_IDS,
    BLENDER_BUILTIN_METHOD_ID,
    is_blender_builtin_map_id,
    iter_blender_builtin_specs,
    supports_blender_builtin_bake,
)
from .register_maps import BLENDER_BUILTIN_BAKE_MAPS

__all__ = (
    "BLENDER_BUILTIN_BAKE_MAPS",
    "BLENDER_BUILTIN_DEVICE",
    "BLENDER_BUILTIN_MAP_IDS",
    "BLENDER_BUILTIN_METHOD_ID",
    "BlenderBakeExecutionContext",
    "is_blender_builtin_map_id",
    "iter_blender_builtin_specs",
    "run_blender_cycles_bake",
    "supports_blender_builtin_bake",
)


def run_blender_cycles_bake(ctx: BlenderBakeExecutionContext) -> None:
    """Run Cycles bake for one map using the shared production executor."""
    from .execute import run_blender_cycles_bake as _run

    _run(ctx)

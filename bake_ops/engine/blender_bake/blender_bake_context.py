"""Runtime context for one Blender Cycles builtin bake step."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import bpy

    from lks_baker.bake_ops.static_utilities.bake_blender_helpers import (
        LKS_BakeGroupMeshes,
    )
    from lks_baker.bake_ops.static_utilities.bake_map_catalog import LKS_BakeMapSpec
    from lks_baker.bake_ops.static_utilities.bake_shader_override_helpers import (
        BakeMaterialOverrideStack,
    )


@dataclass
class BlenderBakeExecutionContext:
    """Everything required to run ``bpy.ops.object.bake`` for one catalog map."""

    context: bpy.types.Context
    scene: bpy.types.Scene
    project: object
    spec: LKS_BakeMapSpec
    group_meshes: LKS_BakeGroupMeshes
    low_mesh: bpy.types.Object
    image: bpy.types.Image
    filepath: Path
    samples: int
    cycles_margin_pixels: int
    material_stack: BakeMaterialOverrideStack
    position_bbox: tuple | None
    log_ctx: dict[str, object] | None = None

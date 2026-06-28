"""Execute one Blender Cycles selected-to-active bake step."""
from __future__ import annotations

from lks_baker.bake_ops.engine.blender_bake.blender_bake_context import BlenderBakeExecutionContext
from lks_baker.bake_ops.static_utilities.bake_blender_helpers import run_blender_cycles_bake_step


def run_blender_cycles_bake(ctx: BlenderBakeExecutionContext) -> None:
    """Run Cycles bake for one map using the shared production executor."""
    run_blender_cycles_bake_step(
        ctx.context,
        ctx.scene,
        ctx.project,
        ctx.spec,
        ctx.group_meshes,
        ctx.low_mesh,
        ctx.image,
        ctx.samples,
        ctx.cycles_margin_pixels,
        ctx.material_stack,
        ctx.position_bbox,
        log_ctx=ctx.log_ctx,
    )

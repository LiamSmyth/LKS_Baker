"""BakeMap base for Blender Cycles builtin bakes."""
from __future__ import annotations

from typing import ClassVar, Type

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.bake_maps.bake_map_implementation import BakeMapImplementation
from lks_baker.bake_ops.engine.blender_bake.blender_bake_context import BlenderBakeExecutionContext
from lks_baker.bake_ops.engine.blender_bake.catalog import (
    BLENDER_BUILTIN_DEVICE,
    BLENDER_BUILTIN_METHOD_ID,
)
from lks_baker.bake_ops.engine.catalog_bridge import get_bake_map_spec


class BlenderCyclesBakeMap(BakeMap, BakeMapImplementation):
    """Selected-to-active Cycles bake via ``bpy.ops.object.bake``."""

    method_id: ClassVar[str] = BLENDER_BUILTIN_METHOD_ID
    device: ClassVar[str] = BLENDER_BUILTIN_DEVICE
    execution_kind: ClassVar[str] = "blender_cycles"
    cost_tier: ClassVar[int] = 2

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        from lks_baker.bake_ops.engine.blender_bake.execute import run_blender_cycles_bake

        raw_ctx = inputs.extra.get("blender_context")
        if not isinstance(raw_ctx, BlenderBakeExecutionContext):
            raise ValueError(f"{self.map_type} blender bake requires BlenderBakeExecutionContext in inputs.extra")
        run_blender_cycles_bake(raw_ctx)
        height, width = int(raw_ctx.image.size[1]), int(raw_ctx.image.size[0])
        return BakeMapOutput(
            packed=np.zeros((height, width), dtype=np.float32),
            valid=None,
            meta={
                "blender_builtin": True,
                "image": raw_ctx.image,
                "filepath": str(raw_ctx.filepath),
            },
        )


def make_blender_cycles_bake_map(map_id: str) -> Type[BlenderCyclesBakeMap]:
    """Factory: one ``BlenderCyclesBakeMap`` subclass per catalog ``map_id``."""
    spec = get_bake_map_spec(map_id)
    if spec is None:
        raise ValueError(f"unknown bake map_id {map_id!r}")

    class_name = "".join(part.title() for part in map_id.split("_")) + "BlenderBake"

    return type(
        class_name,
        (BlenderCyclesBakeMap,),
        {
            "map_type": map_id,
            "produces": map_id,
            "__module__": __name__,
            "__doc__": f"Blender Cycles builtin bake for catalog map {map_id!r}.",
        },
    )

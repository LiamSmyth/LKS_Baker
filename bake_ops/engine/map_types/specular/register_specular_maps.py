"""Register specular bake map implementations."""
from __future__ import annotations

from typing import Type

from lks_baker.bake_ops.engine.bake_map import BakeMap
from lks_baker.bake_ops.engine.map_types.specular.emit_raster_cpu import EmitRasterCpu
from lks_baker.bake_ops.engine.map_types.specular.emit_raster_gpu import EmitRasterGpu

SPECULAR_BAKE_MAPS: tuple[Type[BakeMap], ...] = (
    EmitRasterCpu,
    EmitRasterGpu,
)

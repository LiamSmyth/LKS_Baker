"""Register bent-normal bake map implementations."""
from __future__ import annotations

from typing import Type

from lks_baker.bake_ops.engine.bake_map import BakeMap
from lks_baker.bake_ops.engine.map_types.bent_normal.hemisphere_trace_cpu import (
    HemisphereTraceCpu,
)
from lks_baker.bake_ops.engine.map_types.bent_normal.hemisphere_trace_gpu import (
    HemisphereTraceGpu,
)

BENT_NORMAL_BAKE_MAPS: tuple[Type[BakeMap], ...] = (
    HemisphereTraceCpu,
    HemisphereTraceGpu,
)

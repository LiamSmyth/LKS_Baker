"""Register bent-normal object-space bake maps."""
from __future__ import annotations

from typing import Type

from lks_baker.bake_ops.engine.bake_map import BakeMap
from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_cpu import (
    BentNormalObjectCpu,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_gpu import (
    BentNormalObjectGpu,
)

BENT_NORMAL_OBJECT_BAKE_MAPS: tuple[Type[BakeMap], ...] = (
    BentNormalObjectCpu,
    BentNormalObjectGpu,
)

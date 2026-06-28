"""Atlas hemisphere bent-normal trace (GPU).

Reuses ``bent_normal_object_gpu`` then transforms to tangent space on CPU for parity.
"""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMapInput
from lks_baker.bake_ops.engine.gpu.gpu_runtime import gpu_runtime_available
from lks_baker.bake_ops.engine.map_types.bent_normal.bent_normal_map import BentNormalMap
from lks_baker.bake_ops.engine.map_types.bent_normal.bent_normal_map_implementation import (
    BentNormalMapImplementation,
)
from lks_baker.bake_ops.engine.map_types.bent_normal.static_utilities.atlas_hemisphere_bent_normal import (
    _object_to_tangent,
    atlas_hemisphere_bent_normal,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_gpu import (
    bent_normal_object_gpu,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.static_utilities.bent_normal_object import (
    _safe_normalize,
    bent_normal_object,
    pack_bent_normal_rgb,
    surface_tangent_frames,
)
from lks_baker.bake_ops.engine.settings.bent_normal_settings import (
    HemisphereTraceSettings,
    hemisphere_trace_to_object_settings,
)


def atlas_hemisphere_bent_normal_gpu(
    position: np.ndarray,
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: HemisphereTraceSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """GPU object-space bent normal + CPU tangent transform."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU offscreen runtime unavailable")

    obj_settings = hemisphere_trace_to_object_settings(settings)
    bent_object, _ = bent_normal_object_gpu(
        position,
        object_normal,
        island_id,
        valid,
        obj_settings,
    )
    tangent, bitangent, normal = surface_tangent_frames(object_normal, position, island_id)
    bent_tangent = _object_to_tangent(bent_object, tangent, bitangent, normal)
    bent_tangent = _safe_normalize(bent_tangent)
    bent_tangent[~valid] = 0.0
    rgba = pack_bent_normal_rgb(bent_tangent, valid)
    return rgba, bent_tangent


def atlas_hemisphere_bent_normal_with_fallback(
    position: np.ndarray,
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: HemisphereTraceSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """Prefer GPU object pass when offscreen runtime is available."""
    if gpu_runtime_available():
        return atlas_hemisphere_bent_normal_gpu(
            position,
            object_normal,
            island_id,
            valid,
            settings,
        )
    return atlas_hemisphere_bent_normal(
        position,
        object_normal,
        island_id,
        valid,
        settings,
    )


class HemisphereTraceGpu(BentNormalMap, BentNormalMapImplementation):
    """GPU tangent bent-normal via object-space atlas passes."""

    method_id: ClassVar[str] = "hemisphere_trace"
    device: ClassVar[str] = "gpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 2
    requires_textures_or: ClassVar[tuple[frozenset[str], ...]] = (
        frozenset({"position", "normal_object"}),
    )

    def bake(self, inputs: BakeMapInput):
        self.require_object_normal_and_position(inputs)
        settings = self.bent_normal_settings(inputs)
        obj_settings = hemisphere_trace_to_object_settings(settings.hemisphere_trace)
        if gpu_runtime_available():
            bent_object, _ = bent_normal_object_gpu(
                inputs.position,
                inputs.object_normal,
                inputs.island_id,
                inputs.valid,
                obj_settings,
            )
            tangent, bitangent, normal = surface_tangent_frames(
                inputs.object_normal,
                inputs.position,
                inputs.island_id,
            )
            bent_tangent = _object_to_tangent(bent_object, tangent, bitangent, normal)
            bent_tangent = _safe_normalize(bent_tangent)
            bent_tangent[~inputs.valid] = 0.0
            rgba = pack_bent_normal_rgb(bent_tangent, inputs.valid)
        else:
            bent_object, _ = bent_normal_object(
                inputs.position,
                inputs.object_normal,
                inputs.island_id,
                inputs.valid,
                obj_settings,
            )
            rgba, bent_tangent = atlas_hemisphere_bent_normal(
                inputs.position,
                inputs.object_normal,
                inputs.island_id,
                inputs.valid,
                settings.hemisphere_trace,
            )
        return self.rgb_output(rgba, valid=inputs.valid, bent_tangent=bent_tangent)

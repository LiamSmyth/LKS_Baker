"""Object-space bent normal atlas baker (GPU)."""
from __future__ import annotations

import math
from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMapInput
from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    FullscreenOffscreenSession,
    encode_normal_rgba,
    gpu_runtime_available,
    upload_float_rgb_texture,
    upload_island_texture,
    upload_rgba_texture,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_map import (
    BentNormalObjectMap,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_map_implementation import (
    BentNormalObjectMapImplementation,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.shaders import (
    BENT_NORMAL_OBJECT_DIR_FRAG,
    FULLSCREEN_VERT,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.static_utilities.bent_normal_object import (
    _safe_normalize,
    _world_metric,
    bent_normal_object,
    build_local_hemisphere_directions,
    pack_bent_normal_rgb,
    surface_tangent_frames,
)
from lks_baker.bake_ops.engine.settings.bent_normal_settings import BentNormalObjectSettings

_DIR_PUSH: tuple[tuple[str, str, int], ...] = (
    ("VEC3", "uLocalDir", 0),
    ("FLOAT", "uRadius", 0),
    ("FLOAT", "uBias", 0),
    ("FLOAT", "uSteps", 0),
    ("FLOAT", "uUvTheta", 0),
    ("FLOAT", "uDuMean", 0),
    ("FLOAT", "uDvMean", 0),
    ("FLOAT", "uDySign", 0),
)

_DIR_SAMPLERS: tuple[str, ...] = (
    "normalTex",
    "positionTex",
    "islandTex",
)


def bent_normal_object_gpu(
    position: np.ndarray,
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: BentNormalObjectSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """GPU multi-pass accumulation mirroring ``bent_normal_object`` CPU."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU offscreen runtime unavailable")

    from lks_baker.bake_ops.engine.static_utilities.coords import internal_v_neighbor_indices

    height, width = valid.shape[:2]
    normal = _safe_normalize(object_normal)
    du_world, dv_world = _world_metric(position, island_id)
    du_mean = max(float(np.mean(du_world[valid])) if np.any(valid) else 1.0, 1e-6)
    dv_mean = max(float(np.mean(dv_world[valid])) if np.any(valid) else 1.0, 1e-6)
    pv_plus, _ = internal_v_neighbor_indices()
    dy_sign = 1.0 if pv_plus < 0 else -1.0

    normal_tex = upload_rgba_texture(encode_normal_rgba(normal))
    position_tex = upload_float_rgb_texture(position.astype(np.float32))
    island_tex = upload_island_texture(island_id.astype(np.float32))

    session = FullscreenOffscreenSession(
        FULLSCREEN_VERT,
        BENT_NORMAL_OBJECT_DIR_FRAG,
        width,
        height,
        sampler_names=_DIR_SAMPLERS,
        push_constants=_DIR_PUSH,
    )

    sum_dir = np.zeros((height, width, 3), dtype=np.float32)
    weight = np.zeros((height, width), dtype=np.float32)
    local_dirs = build_local_hemisphere_directions(settings.directions, settings.spread_angle_deg)

    try:
        for local_dir in local_dirs:
            uv_theta = math.atan2(float(local_dir[1]), float(local_dir[0]))
            rgba = session.draw_rgba(
                {
                    "uLocalDir": tuple(float(v) for v in local_dir),
                    "uRadius": float(settings.radius_world),
                    "uBias": float(settings.bias),
                    "uSteps": float(max(1, int(settings.steps_per_direction))),
                    "uUvTheta": float(uv_theta),
                    "uDuMean": float(du_mean),
                    "uDvMean": float(dv_mean),
                    "uDySign": float(dy_sign),
                },
                {
                    "normalTex": normal_tex,
                    "positionTex": position_tex,
                    "islandTex": island_tex,
                },
            )
            contrib = rgba[..., :3]
            w = rgba[..., 3]
            sum_dir += contrib
            weight += w
    finally:
        session.free()

    _, _, fallback_n = surface_tangent_frames(object_normal, position, island_id)
    bent = np.where(weight[..., None] > 0.0, sum_dir / np.maximum(weight[..., None], 1e-6), fallback_n)
    bent = _safe_normalize(bent)
    bent[~valid] = 0.0
    rgba = pack_bent_normal_rgb(bent, valid)
    return bent.astype(np.float32), rgba


class BentNormalObjectGpu(BentNormalObjectMap, BentNormalObjectMapImplementation):
    """GPU bent-normal atlas baker with CPU fallback."""

    method_id: ClassVar[str] = "bent_normal_object"
    device: ClassVar[str] = "gpu"
    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 2
    requires_textures: ClassVar[frozenset[str]] = frozenset({"position", "normal_object"})

    def bake(self, inputs: BakeMapInput):
        self.require_object_normal_and_position(inputs)
        settings = self.bent_normal_settings(inputs)
        if gpu_runtime_available():
            _bent, rgba = bent_normal_object_gpu(
                inputs.position,
                inputs.object_normal,
                inputs.island_id,
                inputs.valid,
                settings,
            )
        else:
            _bent, rgba = bent_normal_object(
                inputs.position,
                inputs.object_normal,
                inputs.island_id,
                inputs.valid,
                settings,
            )
        return self.rgb_output(rgba, inputs.valid)

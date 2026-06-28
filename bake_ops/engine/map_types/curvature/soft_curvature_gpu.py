"""GPU soft curvature — multi-scale integration via offscreen GLSL passes."""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    FullscreenOffscreenSession,
    encode_normal_rgba,
    gpu_runtime_available,
    upload_float_rgb_texture,
    upload_island_texture,
    upload_offset_table,
    upload_rgba_texture,
)
from lks_baker.bake_ops.engine.map_types.curvature.curvature_maps.curvature_map import CurvatureMap
from lks_baker.bake_ops.engine.map_types.curvature.curvature_maps.curvature_map_implementation import (
    CurvatureMapImplementation,
)
from lks_baker.bake_ops.engine.map_types.curvature.shaders import (
    FULLSCREEN_VERT,
    SOFT_CURVATURE_FRAG,
)
from lks_baker.bake_ops.engine.map_types.curvature.static_utilities.soft_curvature import (
    _prepare_fields,
    bake_soft_curvature,
    circle_offsets,
    mip_chain_radii,
    pack_soft_curvature,
    prepare_soft_curvature_shell,
    signed_soft_curvature,
)
from lks_baker.bake_ops.engine.settings.curvature_settings import SoftCurvatureSettings
from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData
from lks_baker.bake_ops.engine.static_utilities.runtime_log import log, timed_step
from lks_baker.bake_ops.engine.map_types.curvature.static_utilities.soft_curvature_debug import (
    soft_curvature_debug,
    soft_curvature_timebox,
)

SOFT_CURVATURE_PUSH: tuple[tuple[str, str, int], ...] = (
    ("INT", "numOffsets", 0),
)

SOFT_CURVATURE_SAMPLERS: tuple[str, ...] = (
    "normalTex",
    "positionTex",
    "islandTex",
    "offsetsTex",
)

_SOFT_CURVATURE_MAX_OFFSETS = 4096
"""Max ring samples in one soft-curvature draw (covers mip radius up to ~650)."""


def _prepare_gpu_textures(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    coverage: np.ndarray,
) -> tuple[object, object, object]:
    """Normalize fields on CPU and upload RGBA32F / R32F textures for GLSL."""
    normal, position_field, work_islands = _prepare_fields(
        object_normal,
        position,
        island_id,
        coverage,
    )
    normal_tex = upload_rgba_texture(encode_normal_rgba(normal))
    position_tex = upload_float_rgb_texture(position_field)
    island_tex = upload_island_texture(work_islands.astype(np.float32))
    return normal_tex, position_tex, island_tex


def _curvature_at_radius_gpu(
    session: FullscreenOffscreenSession,
    normal_tex: object,
    position_tex: object,
    island_tex: object,
    coverage: np.ndarray,
    radius: int,
    *,
    samples_per_radius: int | None,
) -> np.ndarray:
    """Island-aware ring curvature at *radius* — one GPU draw per mip level."""
    offsets = circle_offsets(radius, samples_per_radius)
    height, width = coverage.shape
    if not offsets:
        return np.zeros((height, width), dtype=np.float32)
    if len(offsets) > _SOFT_CURVATURE_MAX_OFFSETS:
        raise ValueError(
            f"soft_curvature GPU ring at radius={radius} needs {len(offsets)} offsets; "
            f"max is {_SOFT_CURVATURE_MAX_OFFSETS}"
        )

    with timed_step(f"soft_curvature GPU radius={radius} ({len(offsets)} samples)"):
        rgba = session.draw_rgba(
            {"numOffsets": len(offsets)},
            {
                "normalTex": normal_tex,
                "positionTex": position_tex,
                "islandTex": island_tex,
                "offsetsTex": upload_offset_table(offsets),
            },
        )

    scale_sum = rgba[..., 0]
    sample_count = rgba[..., 1]
    scale_valid = sample_count > 0.0
    scale_curvature = np.zeros((height, width), dtype=np.float32)
    scale_curvature[scale_valid] = scale_sum[scale_valid] / sample_count[scale_valid]
    scale_curvature[~coverage] = 0.0
    return scale_curvature


def signed_soft_curvature_gpu(
    object_normal: np.ndarray,
    position: np.ndarray,
    island_id: np.ndarray,
    coverage: np.ndarray,
    settings: SoftCurvatureSettings,
) -> np.ndarray:
    """Multi-scale signed curvature on GPU; integration + pack stay CPU-side."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU offscreen runtime unavailable")

    height, width = coverage.shape
    normal_tex, position_tex, island_tex = _prepare_gpu_textures(
        object_normal,
        position,
        island_id,
        coverage,
    )

    radii = settings.radii if settings.radii is not None else mip_chain_radii(height, width)
    log(f"soft_curvature GPU: {width}x{height}, {len(radii)} mip radii")

    session = FullscreenOffscreenSession(
        FULLSCREEN_VERT,
        SOFT_CURVATURE_FRAG,
        width,
        height,
        sampler_names=SOFT_CURVATURE_SAMPLERS,
        push_constants=SOFT_CURVATURE_PUSH,
    )
    try:
        def at_radius(radius: int) -> np.ndarray:
            return _curvature_at_radius_gpu(
                session,
                normal_tex,
                position_tex,
                island_tex,
                coverage,
                radius,
                samples_per_radius=settings.samples_per_radius,
            )

        return signed_soft_curvature(
            object_normal,
            position,
            island_id,
            coverage,
            settings,
            curvature_at_radius=at_radius,
        )
    finally:
        session.free()


def bake_soft_curvature_gpu(
    object_normal: np.ndarray,
    mesh: MeshData,
    settings: SoftCurvatureSettings,
    *,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(packed_gray, signed, coverage)`` using GPU ring passes."""
    with soft_curvature_timebox(f"bake_soft_curvature_gpu {image_size}x{image_size}"):
        soft_curvature_debug(f"bake_soft_curvature_gpu: image_size={image_size}")
        position, coverage, island_id = prepare_soft_curvature_shell(mesh, image_size)
        with timed_step("soft_curvature_gpu signed_soft_curvature_gpu"):
            signed = signed_soft_curvature_gpu(
                object_normal,
                position,
                island_id,
                coverage,
                settings,
            )
        with timed_step("soft_curvature_gpu pack"):
            packed = pack_soft_curvature(signed, coverage, settings.pack)
        soft_curvature_debug("bake_soft_curvature_gpu: done")
    return packed, signed, coverage


class SoftCurvatureGpu(CurvatureMap, CurvatureMapImplementation):
    """GPU soft curvature from low-poly UV shell positions + object-space normal map."""

    method_id: ClassVar[str] = "soft_curvature"
    device: ClassVar[str] = "gpu"
    requires_textures = frozenset({"normal_object"})
    requires_meshes = frozenset({"mesh"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        if inputs.object_normal is None:
            raise ValueError("soft_curvature requires object_normal texture")
        if not gpu_runtime_available():
            raise RuntimeError("GPU offscreen runtime unavailable; use device='cpu'")

        mesh = inputs.low_mesh or inputs.mesh
        if mesh is None:
            mesh = self.require_mesh(inputs)

        image_size = self.image_size(inputs)
        packed, signed, coverage = bake_soft_curvature_gpu(
            inputs.object_normal,
            mesh,
            inputs.settings.soft,
            image_size=image_size,
        )
        return self.output(packed, signed=signed, valid=coverage)


def bake_soft_curvature_with_cpu_fallback(
    object_normal: np.ndarray,
    mesh: MeshData,
    settings: SoftCurvatureSettings,
    *,
    image_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Prefer GPU when offscreen runtime is available."""
    if gpu_runtime_available():
        return bake_soft_curvature_gpu(object_normal, mesh, settings, image_size=image_size)
    return bake_soft_curvature(object_normal, mesh, settings, image_size=image_size)

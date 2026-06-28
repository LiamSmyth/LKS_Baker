"""Rasterize low-mesh triangle edges in UV space (GPU)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput
from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
    FullscreenOffscreenSession,
    gpu_runtime_available,
)
from lks_baker.bake_ops.engine.map_types.wireframe.shaders import (
    FULLSCREEN_VERT,
    WIREFRAME_UV_RASTER_FRAG,
    reload_shaders,
)
from lks_baker.bake_ops.engine.map_types.wireframe.static_utilities.wireframe_raster import (
    collect_uv_edge_segments_pixel,
    resolve_wireframe_aa_sigma,
)
from lks_baker.bake_ops.engine.map_types.wireframe.wireframe_uv_raster_cfg import (
    WireframeUvRasterConfig,
)
from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData
from lks_baker.bake_ops.engine.static_utilities.mesh_uv_charts import (
    rasterize_triangle_chart_ids,
    triangle_uv_chart_ids,
)

WIREFRAME_GPU_MAX_EDGES_PER_PASS = 512
"""Must match ``MAX_EDGES`` in ``wireframe_uv_raster_frag.glsl``."""

WIREFRAME_UV_RASTER_PUSH: tuple[tuple[str, str, int], ...] = ()
WIREFRAME_UV_RASTER_SAMPLERS: tuple[str, ...] = ("edgeTex", "paramsTex")


def _upload_scalar_params(
    half_width: float,
    aa_sigma: float,
    *,
    image_size: int,
    edge_count: int,
) -> object:
    """Upload raster params as a 1×1 ``RGBA32F`` texture (``a`` = batch edge count)."""
    import gpu

    table = np.array(
        [[float(image_size), float(half_width), float(aa_sigma), float(edge_count)]],
        dtype=np.float32,
    )
    flat = np.ascontiguousarray(table.reshape(-1))
    buffer = gpu.types.Buffer("FLOAT", flat.size, flat)
    return gpu.types.GPUTexture(size=(1, 1), format="RGBA32F", data=buffer)


def _upload_edge_batch(edges: np.ndarray) -> object:
    """Upload one batch of ``N×4`` edge segments as a ``1×N`` ``RGBA32F`` texture."""
    import gpu

    count = max(int(len(edges)), 1)
    if len(edges) == 0:
        table = np.zeros((1, 4), dtype=np.float32)
    else:
        table = np.ascontiguousarray(edges.astype(np.float32, copy=False))
    flat = table.reshape(-1)
    buffer = gpu.types.Buffer("FLOAT", flat.size, flat)
    return gpu.types.GPUTexture(size=(count, 1), format="RGBA32F", data=buffer)


def _rasterize_line_strength_gpu(
    edges: np.ndarray,
    image_size: int,
    *,
    half_width: float,
    aa_sigma: float,
) -> np.ndarray:
    """Accumulate max antialiased line coverage on GPU (batched edge passes)."""
    line_strength = np.zeros((image_size, image_size), dtype=np.float32)
    if len(edges) == 0:
        return line_strength

    reload_shaders()
    from lks_baker.bake_ops.engine.map_types.wireframe import shaders

    frag = shaders.WIREFRAME_UV_RASTER_FRAG
    session = FullscreenOffscreenSession(
        FULLSCREEN_VERT,
        frag,
        image_size,
        image_size,
        sampler_names=WIREFRAME_UV_RASTER_SAMPLERS,
        push_constants=WIREFRAME_UV_RASTER_PUSH,
    )
    try:
        for batch_start in range(0, len(edges), WIREFRAME_GPU_MAX_EDGES_PER_PASS):
            batch = edges[batch_start : batch_start + WIREFRAME_GPU_MAX_EDGES_PER_PASS]
            edge_count = int(len(batch))
            pass_strength = session.draw_rgba(
                {},
                {
                    "edgeTex": _upload_edge_batch(batch),
                    "paramsTex": _upload_scalar_params(
                        half_width,
                        aa_sigma,
                        image_size=image_size,
                        edge_count=edge_count,
                    ),
                },
            )[..., 0]
            np.maximum(line_strength, pass_strength, out=line_strength)
    finally:
        session.free()
    return line_strength


def rasterize_wireframe_uv_gpu(
    mesh: MeshData,
    image_size: int,
    *,
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    line_thickness_px: float = 1.5,
    aa_quality: str = 'MEDIUM',
) -> tuple[np.ndarray, np.ndarray]:
    """GPU wireframe raster matching ``rasterize_wireframe_uv`` output layout."""
    if not gpu_runtime_available():
        raise RuntimeError("GPU offscreen runtime unavailable")

    charts = triangle_uv_chart_ids(mesh)
    _, raster_valid = rasterize_triangle_chart_ids(mesh, charts, image_size)
    valid = raster_valid.astype(bool, copy=False)

    half_width = max(float(line_thickness_px) * 0.5, 0.5)
    aa_sigma = resolve_wireframe_aa_sigma(
        line_thickness_px=line_thickness_px,
        aa_quality=aa_quality,
    )
    edges = collect_uv_edge_segments_pixel(mesh, image_size)
    line_strength = _rasterize_line_strength_gpu(
        edges,
        image_size,
        half_width=half_width,
        aa_sigma=aa_sigma,
    )

    rgba = np.zeros((image_size, image_size, 4), dtype=np.float32)
    painted = line_strength > 1e-4
    rgba[painted, 0] = float(color[0])
    rgba[painted, 1] = float(color[1])
    rgba[painted, 2] = float(color[2])
    rgba[painted, 3] = np.clip(line_strength[painted] * float(color[3]), 0.0, 1.0)
    valid = valid | painted
    return rgba, valid


class WireframeUvRasterGpu(BakeMap):
    """Colored wireframe lines from low-poly mesh UV edges (GPU)."""

    map_type: ClassVar[str] = "wireframe"
    method_id: ClassVar[str] = "wireframe_uv_raster"
    device: ClassVar[str] = "gpu"
    execution_kind: ClassVar[str] = "derive_mesh"
    requires_meshes: ClassVar[frozenset[str]] = frozenset({"low"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        mesh = inputs.low_mesh or inputs.mesh
        if mesh is None:
            raise ValueError("wireframe_uv_raster requires low mesh in BakeMapInput")
        image_size = inputs.image_size
        if image_size is None:
            raise ValueError("wireframe_uv_raster requires image_size")
        if not gpu_runtime_available():
            raise RuntimeError("GPU offscreen runtime unavailable; use device='cpu'")

        config = inputs.extra.get("wireframe_config")
        if not isinstance(config, WireframeUvRasterConfig):
            config = WireframeUvRasterConfig()

        rgba, valid = rasterize_wireframe_uv_gpu(
            mesh,
            image_size,
            color=config.color,
            line_thickness_px=config.line_thickness_px,
            aa_quality=config.aa_quality,
        )
        if (
            inputs.valid is not None
            and inputs.valid.shape == valid.shape
            and np.any(inputs.valid)
        ):
            valid = valid & inputs.valid
            rgba[~valid] = 0.0

        gray = rgba[..., 0].astype(np.float32, copy=False)
        return BakeMapOutput(packed=gray, valid=valid, meta={"rgba": rgba})

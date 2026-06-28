"""Rasterize mesh triangle edges into a UV atlas wireframe RGBA image."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData
from lks_baker.bake_ops.engine.static_utilities.mesh_uv_charts import (
    rasterize_triangle_chart_ids,
    triangle_uv_chart_ids,
)
from lks_baker.bake_ops.engine.static_utilities.uv_raster import uv_to_pixel

_AA_SIGMA_SCALE: dict[str, float] = {
    'LOW': 0.35,
    'MEDIUM': 0.65,
    'HIGH': 1.15,
}


def resolve_wireframe_aa_sigma(*, line_thickness_px: float, aa_quality: str) -> float:
    """Convert AA preset + line thickness (texels) to Gaussian sigma in pixels."""
    scale = _AA_SIGMA_SCALE.get(aa_quality, _AA_SIGMA_SCALE['MEDIUM'])
    return max(float(line_thickness_px) * scale, 0.25)


def collect_uv_edge_segments_pixel(mesh: MeshData, image_size: int) -> np.ndarray:
    """Return ``N×4`` float32 edge segments in PNG pixel coordinates."""
    segments: list[list[float]] = []
    for tri_uv in mesh.face_uvs:
        for i0, i1 in ((0, 1), (1, 2), (2, 0)):
            pa = uv_to_pixel(tri_uv[i0][None], image_size)[0]
            pb = uv_to_pixel(tri_uv[i1][None], image_size)[0]
            segments.append([float(pa[0]), float(pa[1]), float(pb[0]), float(pb[1])])
    if not segments:
        return np.zeros((0, 4), dtype=np.float32)
    return np.asarray(segments, dtype=np.float32)


def _splat_rgba_edge_segment(
    line_strength: np.ndarray,
    uv_a: np.ndarray,
    uv_b: np.ndarray,
    image_size: int,
    *,
    half_width: float,
    aa_sigma: float,
) -> None:
    """Accumulate antialiased line coverage along one UV edge segment."""
    pa = uv_to_pixel(uv_a[None], image_size)[0]
    pb = uv_to_pixel(uv_b[None], image_size)[0]
    reach = half_width + aa_sigma * 3.0
    min_x = max(0, int(np.floor(min(pa[0], pb[0]) - reach)))
    max_x = min(image_size - 1, int(np.ceil(max(pa[0], pb[0]) + reach)))
    min_y = max(0, int(np.floor(min(pa[1], pb[1]) - reach)))
    max_y = min(image_size - 1, int(np.ceil(max(pa[1], pb[1]) + reach)))
    if min_x > max_x or min_y > max_y:
        return

    xs = np.arange(min_x, max_x + 1, dtype=np.float32) + np.float32(0.5)
    ys = np.arange(min_y, max_y + 1, dtype=np.float32) + np.float32(0.5)
    grid_x, grid_y = np.meshgrid(xs, ys)
    points = np.stack([grid_x, grid_y], axis=-1).astype(np.float32, copy=False)

    pa = pa.astype(np.float32, copy=False)
    pb = pb.astype(np.float32, copy=False)
    ab = pb - pa
    ab_len_sq = max(float(np.dot(ab, ab)), 1e-8)
    t = np.clip(np.sum((points - pa) * ab, axis=-1) / ab_len_sq, 0.0, 1.0)
    closest = pa + t[..., None] * ab
    dist = np.linalg.norm(points - closest, axis=-1).astype(np.float32, copy=False)

    core = dist <= half_width
    edge = (~core) & (dist <= half_width + aa_sigma * 3.0)
    alpha = np.zeros_like(dist, dtype=np.float32)
    alpha[core] = 1.0
    if np.any(edge):
        edge_dist = dist[edge] - half_width
        alpha[edge] = np.exp(-(edge_dist * edge_dist) / (2.0 * aa_sigma * aa_sigma)).astype(
            np.float32,
        )

    yy, xx = np.nonzero(alpha > 1e-4)
    if yy.size == 0:
        return
    local_alpha = alpha[yy, xx]
    np.maximum.at(line_strength, (min_y + yy, min_x + xx), local_alpha)


def rasterize_line_strength_cpu(
    mesh: MeshData,
    image_size: int,
    *,
    line_thickness_px: float = 1.5,
    aa_quality: str = 'MEDIUM',
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(line_strength float32 H×W, chart_valid bool H×W)``."""
    charts = triangle_uv_chart_ids(mesh)
    _, raster_valid = rasterize_triangle_chart_ids(mesh, charts, image_size)
    valid = raster_valid.astype(bool, copy=False)

    line_strength = np.zeros((image_size, image_size), dtype=np.float32)
    half_width = max(float(line_thickness_px) * 0.5, 0.5)
    aa_sigma = resolve_wireframe_aa_sigma(
        line_thickness_px=line_thickness_px,
        aa_quality=aa_quality,
    )

    for tri_uv in mesh.face_uvs:
        for i0, i1 in ((0, 1), (1, 2), (2, 0)):
            _splat_rgba_edge_segment(
                line_strength,
                tri_uv[i0],
                tri_uv[i1],
                image_size,
                half_width=half_width,
                aa_sigma=aa_sigma,
            )

    return line_strength, valid


def rasterize_wireframe_uv(
    mesh: MeshData,
    image_size: int,
    *,
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    line_thickness_px: float = 1.5,
    aa_quality: str = 'MEDIUM',
) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize triangle edges in UV space.

    ``line_thickness_px`` is the full stroke width in atlas texels (not world units).

    Returns:
        ``(rgba float32 H×W×4, valid bool H×W)`` — lines tinted by ``color`` on transparent background.
    """
    line_strength, valid = rasterize_line_strength_cpu(
        mesh,
        image_size,
        line_thickness_px=line_thickness_px,
        aa_quality=aa_quality,
    )

    rgba = np.zeros((image_size, image_size, 4), dtype=np.float32)
    painted = line_strength > 1e-4
    rgba[painted, 0] = float(color[0])
    rgba[painted, 1] = float(color[1])
    rgba[painted, 2] = float(color[2])
    rgba[painted, 3] = np.clip(line_strength[painted] * float(color[3]), 0.0, 1.0)
    valid = valid | painted
    return rgba, valid

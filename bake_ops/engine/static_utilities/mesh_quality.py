"""Mesh bake quality checks (UV overlap, topology warnings)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mesh_data import MeshData, bake_vertex_curvature_to_uv


@dataclass
class MeshBakeReport:
    """Mesh quality warnings for bake readiness.

    Attributes:
        verts: ``int`` value.
        tris: ``int`` value.
        raster_pixels: ``int`` value.
        bake_pixels: ``int`` value.
        overlap_pixels: ``int`` value.
        bake_coverage: ``float`` value.
    """
    verts: int
    tris: int
    raster_pixels: int
    bake_pixels: int
    overlap_pixels: int
    bake_coverage: float

    def format_warnings(self) -> list[str]:
        """Format warnings.

        Returns:
            ``list[str]`` result.
        """
        warnings: list[str] = []
        if self.tris < 100:
            warnings.append(
                f"Low mesh has only {self.tris} tris ({self.verts} verts) — "
                "mesh/dihedral bakes need the real bake low-poly, not a placeholder."
            )
        if self.bake_coverage < 0.5:
            warnings.append(
                f"Low mesh UVs cover {self.bake_coverage * 100:.1f}% of the texture bake mask — "
                "UV layout may not match the source maps."
            )
        return warnings


def mesh_bake_report(
    low: MeshData,
    image_size: int,
    bake_valid: np.ndarray,
) -> MeshBakeReport:
    """Mesh bake report.

    Args:
        low: ``MeshData`` value.
        image_size: Square bake resolution (H = W).
        bake_valid: ``np.ndarray`` value.

    Returns:
        ``MeshBakeReport`` result.
    """
    zeros = np.zeros(len(low.vertices), dtype=np.float32)
    _, raster_valid = bake_vertex_curvature_to_uv(low, zeros, image_size)
    overlap = raster_valid & bake_valid
    bake_pixels = int(bake_valid.sum())
    overlap_pixels = int(overlap.sum())
    coverage = overlap_pixels / max(bake_pixels, 1)
    return MeshBakeReport(
        verts=len(low.vertices),
        tris=len(low.faces),
        raster_pixels=int(raster_valid.sum()),
        bake_pixels=bake_pixels,
        overlap_pixels=overlap_pixels,
        bake_coverage=coverage,
    )


def print_mesh_bake_report(report: MeshBakeReport, *, label: str = "Low mesh") -> None:
    """Print mesh bake report.

    Args:
        report: ``MeshBakeReport`` value.
    """
    print(
        f"{label}: {report.verts} verts, {report.tris} tris, "
        f"UV overlap {report.overlap_pixels}/{report.bake_pixels} "
        f"({report.bake_coverage * 100:.1f}% of bake mask)"
    )
    for warning in report.format_warnings():
        print(f"  WARNING: {warning}")

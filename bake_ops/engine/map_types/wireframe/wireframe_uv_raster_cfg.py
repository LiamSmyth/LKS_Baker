"""Static config for the ``wireframe_uv_raster`` bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry

WIREFRAME_AA_QUALITY_ITEMS: tuple[tuple[str, str, str], ...] = (
    ('LOW', 'Low', 'Narrow edge soften'),
    ('MEDIUM', 'Medium', 'Balanced anti-aliasing'),
    ('HIGH', 'High', 'Wide edge soften'),
)

DEFAULT_WIREFRAME_COLOR: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
DEFAULT_WIREFRAME_AA_QUALITY = 'MEDIUM'
DEFAULT_WIREFRAME_LINE_THICKNESS_PX = 1.5


@dataclass
class WireframeUvRasterConfig:
    """UV-space wireframe raster tuning."""

    color: tuple[float, float, float, float] = DEFAULT_WIREFRAME_COLOR
    aa_quality: str = DEFAULT_WIREFRAME_AA_QUALITY
    line_thickness_px: float = DEFAULT_WIREFRAME_LINE_THICKNESS_PX


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> WireframeUvRasterConfig:
    """Build config from map-entry RNA."""
    color = tuple(float(channel) for channel in entry.lks_wireframe_color)
    if len(color) == 3:
        color = (*color, 1.0)
    return WireframeUvRasterConfig(
        color=color,
        aa_quality=str(entry.lks_wireframe_aa_quality),
        line_thickness_px=float(entry.lks_wireframe_line_thickness),
    )

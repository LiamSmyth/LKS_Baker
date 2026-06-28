"""Shared packing and multiscale configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PackSettings:
    """Final signed -> grayscale packing."""

    percentile: float = 95.0
    strength: float = 0.5
    flat: float = 0.5


@dataclass
class MultiscaleSettings:
    """Blur radii (texels) and weights for multiscale accumulation."""

    radii: tuple[float, ...] = (0.0, 2.0, 8.0, 16.0)
    weights: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125)

"""Per-method configuration for cavity / detail-AO generation."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AoPackSettings:
    """AO percentile pack settings.

    Attributes:
        percentile: ``float`` value.
        strength: ``float`` value.
    """
    percentile: float = 95.0
    strength: float = 0.5


@dataclass
class AoMultiscaleSettings:
    """Multiscale radius/weight list for cavity AO.

    Attributes:
        radii: ``tuple[float, ...]`` value.
        weights: ``tuple[float, ...]`` value.
    """
    radii: tuple[float, ...] = (0.0, 1.0, 4.0, 16.0)
    weights: tuple[float, ...] = (0.35, 0.35, 0.2, 0.1)


@dataclass
class CavitySettings:
    """Normal-cavity multiscale AO settings.

    Attributes:
        intensity: ``float`` value.
        multiscale: ``AoMultiscaleSettings`` value.
        pack: ``AoPackSettings`` value.
    """
    intensity: float = 1.0
    multiscale: AoMultiscaleSettings = field(default_factory=AoMultiscaleSettings)
    pack: AoPackSettings = field(default_factory=AoPackSettings)

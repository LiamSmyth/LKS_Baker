"""Per-method configuration for bent-normal generation."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BentNormalObjectSettings:
    """Atlas bent-normal sampling parameters (object/world-space output).

    Attributes:
        directions: Hemisphere sample count (minimum 4).
        steps_per_direction: UV atlas march steps per sample direction.
        radius_world: Maximum world-space search radius for occlusion.
        spread_angle_deg: Cone half-angle limiting samples around the surface normal.
        bias: Small offset reducing self-occlusion from tangent-plane neighbors.
    """

    directions: int = 12
    steps_per_direction: int = 8
    radius_world: float = 0.35
    spread_angle_deg: float = 90.0
    bias: float = 0.02


@dataclass
class HemisphereTraceSettings:
    """Tangent bent-normal settings for ``hemisphere_trace`` (maps to object atlas core)."""

    sample_count: int = 16
    steps_per_direction: int = 8
    radius_world: float = 0.35
    bias: float = 0.02
    spread: float = 1.0


@dataclass
class BentNormalSettings:
    """Aggregate tangent bent-normal lab settings."""

    max_size: int | None = None
    hemisphere_trace: HemisphereTraceSettings = field(default_factory=HemisphereTraceSettings)
    debug_texel_fail: bool = False


def hemisphere_trace_to_object_settings(
    settings: HemisphereTraceSettings,
) -> BentNormalObjectSettings:
    """Convert tangent-method settings into object-space atlas settings."""
    spread_angle = float(max(5.0, min(90.0, 90.0 * float(settings.spread))))
    return BentNormalObjectSettings(
        directions=max(4, int(settings.sample_count)),
        steps_per_direction=max(1, int(settings.steps_per_direction)),
        radius_world=float(settings.radius_world),
        spread_angle_deg=spread_angle,
        bias=float(settings.bias),
    )

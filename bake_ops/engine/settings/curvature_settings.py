"""Per-method configuration for curvature generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


@dataclass
class PackSettings:
    """Final signed -> grayscale packing."""

    percentile: float = 95.0
    strength: float = 0.5
    flat: float = 0.5


@dataclass
class TangentSettings:
    """Tangent-divergence curvature tuning (intensity, invert, pack).

    Attributes:
        intensity: ``float`` value.
        invert: ``bool`` value.
        sample_radius: ``int`` value.
        pack: ``PackSettings`` value.
    """
    intensity: float = 1.0
    # True: negate divergence so peaks pack bright, valleys dark (OpenGL tangent normals).
    invert: bool = True
    # Per-island blur radius (texels) for position/tangent/divergence smoothing.
    sample_radius: int = 6
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.5))


@dataclass
class WorldSettings:
    """World-divergence curvature tuning.

    Attributes:
        sample_radius: ``int`` value.
        use_rate_form: ``bool`` value.
        intensity: ``float`` value.
        pack: ``PackSettings`` value.
    """
    sample_radius: int = 2
    use_rate_form: bool = False
    intensity: float = 1.0
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.15))


@dataclass
class MeshSettings:
    """Mesh Laplacian curvature tuning.

    Attributes:
        smooth_interpolation: ``bool`` value.
        pack: ``PackSettings`` value.
    """
    smooth_interpolation: bool = True
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.22))


@dataclass
class DihedralSettings:
    """Dihedral edge curvature tuning.

    Attributes:
        radius_texels: ``float`` value.
        min_angle_deg: ``float`` value.
        edge_falloff: ``float`` value.
        pack: ``PackSettings`` value.
    """
    radius_texels: float = 8.0
    min_angle_deg: float = 1.0
    edge_falloff: float = 2.0
    # strength < 0.5 so flat+strength < 1.0 — prevents pure-white saturation
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.45))


@dataclass
class TangentMeshSettings:
    """Tangent/mesh blend weights and pack settings.

    Attributes:
        tangent_weight: ``float`` value.
        mesh_weight: ``float`` value.
        pack: ``PackSettings`` value.
    """
    tangent_weight: float = 1.0
    mesh_weight: float = 0.35
    # strength < 0.5 so flat+strength < 1.0 — prevents pure-white saturation
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.45))


@dataclass
class SdSettings:
    """Production SD curvature (object normal + geometry macro normal)."""

    magnitude_gain: float = 1.5
    convexity_sign: float = 1.0
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.35))


@dataclass
class SoftCurvatureSettings:
    """Multi-scale soft curvature from low-poly shell + object-space normals."""

    radii: tuple[int, ...] | None = None
    scale_weights: tuple[float, ...] | None = None
    samples_per_radius: int | None = None
    normalize_each_scale: bool = True
    normalize_percentile: float = 95.0
    convex_is_white: bool = True
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.5))


@dataclass
class HighToLowSettings:
    """GPU raycast high-poly curvature onto low-poly UV texels."""

    max_ray_distance: float = 0.0
    ray_epsilon: float = 1e-4
    cast_both_sides: bool = True
    num_ray_samples: int = 4
    ray_jitter: float = 0.02
    pack: PackSettings = field(default_factory=lambda: PackSettings(strength=0.06))


class Backend(str, Enum):
    """Backend.

    Attributes:
        AUTO: Field value.
        CPU: Field value.
        GPU: Field value.
    """
    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"


@dataclass
class CurvatureLabSettings:
    """Aggregate curvature lab settings for all methods.

    Attributes:
        max_size: Optional longest-edge downscale limit.
        backend: ``Backend`` value.
        tangent: ``TangentSettings`` value.
        world: ``WorldSettings`` value.
        mesh: Triangulated ``MeshData`` for mesh-backed bakes.
        dihedral: ``DihedralSettings`` value.
        tangent_mesh: ``TangentMeshSettings`` value.
        sd: ``SdSettings`` value.
        soft: ``SoftCurvatureSettings`` value.
        high_to_low: ``HighToLowSettings`` value.
    """
    max_size: int | None = None
    backend: Backend = Backend.AUTO
    tangent: TangentSettings = field(default_factory=TangentSettings)
    world: WorldSettings = field(default_factory=WorldSettings)
    mesh: MeshSettings = field(default_factory=MeshSettings)
    dihedral: DihedralSettings = field(default_factory=DihedralSettings)
    tangent_mesh: TangentMeshSettings = field(default_factory=TangentMeshSettings)
    sd: SdSettings = field(default_factory=SdSettings)
    soft: SoftCurvatureSettings = field(default_factory=SoftCurvatureSettings)
    high_to_low: HighToLowSettings = field(default_factory=HighToLowSettings)
    debug_texel_fail: bool = False

    def with_overrides(self, **kwargs: object) -> CurvatureLabSettings:
        """Deep copy with dotted overrides like tangent__pack__strength=0.25."""
        import copy

        out = copy.deepcopy(self)
        for key, value in kwargs.items():
            parts = key.split("__")
            obj = out
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)
        return out


# Legacy alias
CurvatureSettings = CurvatureLabSettings

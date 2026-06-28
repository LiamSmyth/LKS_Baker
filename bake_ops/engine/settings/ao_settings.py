"""Per-method configuration for AO generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from ..map_types.cavity.cavity_settings import (
    AoMultiscaleSettings,
    AoPackSettings,
    CavitySettings,
)


@dataclass
class AtlasHbaoSettings:
    """Atlas horizon-based AO sampling parameters.

    Attributes:
        directions: ``int`` value.
        steps_per_direction: ``int`` value.
        radius_world: ``float`` value.
        bias: ``float`` value.
        strength: ``float`` value.
    """
    directions: int = 8
    steps_per_direction: int = 8
    radius_world: float = 0.35
    bias: float = 0.02
    strength: float = 1.0


@dataclass
class HeightIntegrateSettings:
    """Height-from-normal integration solver settings.

    Attributes:
        integration_solver: ``Literal['fft', 'jacobi']`` value.
        jacobi_iterations: ``int`` value.
        height_scale: ``float`` value.
    """
    integration_solver: Literal["fft", "jacobi"] = "fft"
    jacobi_iterations: int = 200
    height_scale: float = 1.0


@dataclass
class TextureHbaoSettings:
    """Texture-space HBAO sampling parameters.

    Attributes:
        directions: ``int`` value.
        steps_per_direction: ``int`` value.
        ao_radius_texels: ``float`` value.
        bias: ``float`` value.
        strength: ``float`` value.
    """
    directions: int = 8
    steps_per_direction: int = 12
    ao_radius_texels: float = 16.0
    bias: float = 0.01
    strength: float = 1.0


class CompositeBlendMode(str, Enum):
    """CompositeBlendMode.

    Attributes:
        MULTIPLY_LERP: Field value.
        MULTIPLY: Field value.
        MIN: Field value.
        DETAIL_ONLY: Field value.
    """
    MULTIPLY_LERP = "MULTIPLY_LERP"
    MULTIPLY = "MULTIPLY"
    MIN = "MIN"
    DETAIL_ONLY = "DETAIL_ONLY"


@dataclass
class CompositeSettings:
    """AO composite blend and detail tuning.

    Attributes:
        detail_weight: ``float`` value.
        detail_contrast: ``float`` value.
        blend_mode: ``CompositeBlendMode`` value.
    """
    detail_weight: float = 1.0
    detail_contrast: float = 1.0
    blend_mode: CompositeBlendMode = CompositeBlendMode.MULTIPLY_LERP


@dataclass
class AoSettings:
    """Aggregate AO lab settings.

    Attributes:
        max_size: Optional longest-edge downscale limit.
        cavity: ``CavitySettings`` value.
        atlas_hbao: ``AtlasHbaoSettings`` value.
        height_integrate: ``HeightIntegrateSettings`` value.
        texture_hbao: ``TextureHbaoSettings`` value.
        composite: ``CompositeSettings`` value.
    """
    max_size: int | None = None
    cavity: CavitySettings = field(default_factory=CavitySettings)
    atlas_hbao: AtlasHbaoSettings = field(default_factory=AtlasHbaoSettings)
    height_integrate: HeightIntegrateSettings = field(default_factory=HeightIntegrateSettings)
    texture_hbao: TextureHbaoSettings = field(default_factory=TextureHbaoSettings)
    composite: CompositeSettings = field(default_factory=CompositeSettings)
    debug_texel_fail: bool = False

"""Abstract bake map contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

from .settings.curvature_settings import CurvatureSettings


@dataclass
class BakeMapInput:
    """Textures and mesh data supplied by an orchestrator."""

    valid: np.ndarray
    island_id: np.ndarray
    tangent_normal: np.ndarray | None = None
    object_normal: np.ndarray | None = None
    position: np.ndarray | None = None
    normal_rgba: np.ndarray | None = None
    object_rgba: np.ndarray | None = None
    position_rgba: np.ndarray | None = None
    mesh: Any | None = None
    low_mesh: Any | None = None
    high_mesh: Any | None = None
    surface_position: np.ndarray | None = None
    surface_normal: np.ndarray | None = None
    surface_valid: np.ndarray | None = None
    image_size: int | None = None
    settings: CurvatureSettings = field(default_factory=CurvatureSettings)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BakeMapOutput:
    """Result of a single bake map execution.

    Attributes:
        packed: H×W float32 grayscale in 0..1 (primary bake output).
        signed: Optional H×W signed field before percentile packing.
        valid: Optional H×W bool mask copied from inputs for downstream use.
        meta: Arbitrary per-method metadata (timings, debug channels, etc.).
    """

    packed: np.ndarray
    signed: np.ndarray | None = None
    valid: np.ndarray | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class BakeMap(ABC):
    """One bake algorithm on one device."""

    map_type: ClassVar[str]
    method_id: ClassVar[str]
    device: ClassVar[str]

    execution_kind: ClassVar[str] = "derive_2d"
    cost_tier: ClassVar[int] = 1
    produces: ClassVar[str] = ""
    requires_textures: ClassVar[frozenset[str]] = frozenset()
    requires_textures_or: ClassVar[tuple[frozenset[str], ...]] = ()
    requires_meshes: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def key(cls) -> tuple[str, str, str]:
        """Return registry lookup key ``(map_type, method_id, device)``."""
        return cls.map_type, cls.method_id, cls.device

    @classmethod
    def output_map_id(cls) -> str:
        """Return catalog map id written by this implementation (``produces`` or ``map_type``)."""
        return cls.produces or cls.map_type

    @classmethod
    def can_satisfy(cls, scheduled: set[str], available_on_disk: set[str]) -> bool:
        """Return whether required input textures are scheduled or already on disk.

        Args:
            scheduled: Map ids planned for the current bake job.
            available_on_disk: Map ids present in the bake texture directory.

        Returns:
            True when all ``requires_textures`` and one ``requires_textures_or`` group match.
        """
        available = scheduled | available_on_disk
        if cls.requires_textures and not cls.requires_textures.issubset(available):
            return False
        if cls.requires_textures_or:
            if not any(group.issubset(available) for group in cls.requires_textures_or):
                return False
        return True

    @classmethod
    def uses_gpu(cls) -> bool:
        """True when this implementation invokes GPU shaders or offscreen passes."""
        return cls.device == "gpu"

    @abstractmethod
    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        """Execute this bake method and return packed (and optional signed) maps.

        Args:
            inputs: Textures, masks, mesh data, resolution, and per-method settings.

        Returns:
            ``BakeMapOutput`` with at least ``packed`` populated for valid texels.
        """

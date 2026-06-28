"""Shared BakeMap helpers."""
from __future__ import annotations

import numpy as np

from ..bake_map import BakeMapInput, BakeMapOutput


class BakeMapImplementation:
    """Mixin-style helpers for concrete bake maps."""

    @staticmethod
    def require_mesh(inputs: BakeMapInput):
        """Return ``inputs.mesh`` or raise when a mesh-backed method lacks mesh data."""
        if inputs.mesh is None:
            raise ValueError("mesh is required for this bake map")
        return inputs.mesh

    @staticmethod
    def image_size(inputs: BakeMapInput) -> int:
        """Return square bake resolution from ``inputs.image_size`` or ``valid`` shape."""
        if inputs.image_size is not None:
            return inputs.image_size
        return int(inputs.valid.shape[0])

    @staticmethod
    def output(packed: np.ndarray, *, signed: np.ndarray | None = None, valid: np.ndarray | None = None, **meta) -> BakeMapOutput:
        """Build a standard ``BakeMapOutput`` from packed (and optional signed) arrays."""
        return BakeMapOutput(packed=packed, signed=signed, valid=valid, meta=meta)

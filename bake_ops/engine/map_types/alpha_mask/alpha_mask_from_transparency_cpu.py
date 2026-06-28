"""Hard-threshold transparency into a binary mask (CPU)."""
from __future__ import annotations

from typing import ClassVar

import numpy as np

from lks_baker.bake_ops.engine.bake_map import BakeMap, BakeMapInput, BakeMapOutput

_ALPHA_MASK_THRESHOLD = 0.5


class AlphaMaskFromTransparencyCpu(BakeMap):
    """Binary alpha mask from a transparency bake."""

    map_type: ClassVar[str] = "alpha_mask"
    method_id: ClassVar[str] = "alpha_mask_from_transparency"
    device: ClassVar[str] = "cpu"
    requires_textures: ClassVar[frozenset[str]] = frozenset({"transparency"})

    def bake(self, inputs: BakeMapInput) -> BakeMapOutput:
        rgba = inputs.extra.get("transparency_rgba")
        if rgba is None:
            raise ValueError("alpha_mask_from_transparency requires transparency_rgba in inputs.extra")
        valid = inputs.valid
        if valid is None:
            valid = np.max(rgba[..., :4], axis=-1) > 1e-8

        value = np.max(rgba[..., :4], axis=-1)
        mask = np.where(value >= _ALPHA_MASK_THRESHOLD, 1.0, 0.0).astype(np.float32)
        mask[~valid] = 0.0
        return BakeMapOutput(packed=mask, valid=valid)

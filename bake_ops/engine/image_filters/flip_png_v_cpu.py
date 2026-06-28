"""CPU PNG row-order flip (IMAGE_DOWN ↔ OPENGL_BAKE)."""
from __future__ import annotations

import numpy as np


def filter(image: np.ndarray) -> np.ndarray:
    """Flip image rows to swap PNG V convention (row 0 top ↔ row 0 bottom)."""
    if image.ndim == 2:
        return np.flipud(image.astype(np.float32, copy=False))

    channels = image.shape[-1]
    if channels >= 4:
        out = np.array(image, dtype=np.float32, copy=True)
        out[..., :4] = np.flipud(out[..., :4])
        return out

    return np.flipud(image.astype(np.float32, copy=False))

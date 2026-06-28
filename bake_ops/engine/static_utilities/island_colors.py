"""Stable pseudo-random RGB colors per UV island id."""
from __future__ import annotations

import struct
import zlib

import numpy as np


def island_id_to_rgb01(island_id: int) -> tuple[float, float, float]:
    """Return deterministic RGB in 0..1 for one island label."""
    digest = zlib.crc32(struct.pack("i", int(island_id))) & 0xFFFFFFFF
    return (
        ((digest >> 0) & 0xFF) / 255.0,
        ((digest >> 8) & 0xFF) / 255.0,
        ((digest >> 16) & 0xFF) / 255.0,
    )


def paint_island_id_rgba(island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Paint H×W×4 RGBA from integer island labels (-1 = empty)."""
    out = np.zeros((*island_id.shape, 4), dtype=np.float32)
    mask = valid & (island_id >= 0)
    if not np.any(mask):
        return out
    for label in np.unique(island_id[mask]):
        red, green, blue = island_id_to_rgb01(int(label))
        sel = mask & (island_id == label)
        out[sel, 0] = red
        out[sel, 1] = green
        out[sel, 2] = blue
        out[sel, 3] = 1.0
    return out

"""Typed array aliases for curvature bake methods."""
from __future__ import annotations

import numpy as np

GrayscaleMap = np.ndarray  # HxW float32 in 0..1
SignedMap = np.ndarray  # HxW float32 signed curvature
NormalMap = np.ndarray  # HxWx3 float32 unit vectors
PositionMap = np.ndarray  # HxWx3 float32 world/object positions
RgbaMap = np.ndarray  # HxWx4 float32 encoded textures
IslandIdMap = np.ndarray  # HxW int32
ValidMask = np.ndarray  # HxW bool

"""Per-island Gaussian blur for H×W or H×W×C float fields."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from ..static_utilities.islands import _coalesce_island_ids, _iter_island_labels


def filter(
    image: np.ndarray,
    island_id: np.ndarray,
    sigma: float,
    *,
    sample_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Blur per UV island without cross-island bleed."""
    if sigma <= 0.0:
        return image.copy()

    valid = island_id >= 0
    work_id = _coalesce_island_ids(island_id, valid)
    labels = _iter_island_labels(work_id, valid)

    out = np.zeros_like(image, dtype=np.float32)
    for label in labels:
        island_mask = work_id == label
        use_mask = island_mask if sample_mask is None else island_mask & sample_mask
        if not np.any(use_mask):
            continue

        if image.ndim == 2:
            patch = np.where(use_mask, image, 0.0)
            weight = use_mask.astype(np.float32)
            blurred = ndimage.gaussian_filter(patch, sigma, mode="nearest")
            weight_blurred = ndimage.gaussian_filter(weight, sigma, mode="nearest")
            normalized = blurred / np.maximum(weight_blurred, 1e-8)
            out[island_mask] = normalized[island_mask]
        else:
            channels = []
            weight = use_mask.astype(np.float32)
            weight_blurred = ndimage.gaussian_filter(weight, sigma, mode="nearest")
            for axis in range(image.shape[-1]):
                patch = np.where(use_mask, image[..., axis], 0.0)
                blurred = ndimage.gaussian_filter(patch, sigma, mode="nearest")
                channels.append(blurred / np.maximum(weight_blurred, 1e-8))
            normalized = np.stack(channels, axis=-1)
            out[island_mask] = normalized[island_mask]
    return out.astype(np.float32)


island_gaussian_blur = filter

"""Optional named GPU filter dispatch with per-filter defaults."""
from __future__ import annotations

from typing import Any

import numpy as np

from . import blur_gpu, normalize_gpu


_FILTER_DEFAULTS: dict[str, dict[str, Any]] = {
    "blur": {"sigma": 1.0},
    "normalize_signed": {"percentile": 95.0, "contrast": 1.0, "flat": 0.5},
    "normalize_positive": {"percentile": 95.0, "flat": 0.0},
}


def run_filter(name: str, image: np.ndarray, **overrides: Any) -> np.ndarray:
    """Run a registered GPU filter by name; ``overrides`` replace defaults."""
    params = {**_FILTER_DEFAULTS.get(name, {}), **overrides}
    if name == "blur":
        island_id = params.pop("island_id")
        sigma = float(params.pop("sigma"))
        sample_mask = params.pop("sample_mask", None)
        if params:
            raise TypeError(f"unexpected blur kwargs: {sorted(params)}")
        return blur_gpu.filter(image, island_id, sigma, sample_mask=sample_mask)
    if name == "normalize_signed":
        valid = params.pop("valid")
        return normalize_gpu.filter_signed(image, valid, **params)
    if name == "normalize_positive":
        valid = params.pop("valid")
        return normalize_gpu.filter_positive(image, valid, **params)
    raise KeyError(f"unknown GPU image filter: {name!r}")

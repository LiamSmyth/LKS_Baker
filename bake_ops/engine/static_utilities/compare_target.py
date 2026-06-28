"""Compare generated curvature against a reference target map."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class CompareResult:
    """Numeric comparison stats between two grayscale maps.

    Attributes:
        mae: ``float`` value.
        rmse: ``float`` value.
        correlation: ``float`` value.
        target_mean: ``float`` value.
        target_std: ``float`` value.
        output_mean: ``float`` value.
        output_std: ``float`` value.
    """
    mae: float
    rmse: float
    correlation: float
    target_mean: float
    target_std: float
    output_mean: float
    output_std: float


def load_target_gray01(path: str | Path) -> np.ndarray:
    """Load target gray01.

    Args:
        path: Filesystem path.

    Returns:
        ``np.ndarray`` result.
    """
    image = Image.open(path)
    array = np.array(image, dtype=np.float32)
    if image.mode in {"I;16", "I"}:
        return array / 65535.0
    if array.ndim == 3:
        array = array[..., 0]
    return array / 255.0


def compare_maps(
    target: np.ndarray,
    output: np.ndarray,
    valid: np.ndarray | None = None,
) -> CompareResult:
    """Compare maps.

    Args:
        target: ``np.ndarray`` value.
        output: ``np.ndarray`` value.
        valid: H×W bool mask of texels with mesh coverage.

    Returns:
        ``CompareResult`` result.
    """
    if valid is None:
        valid = np.ones(target.shape[:2], dtype=bool)

    mask = valid & np.isfinite(target) & np.isfinite(output)
    t = target[mask].astype(np.float64)
    o = output[mask].astype(np.float64)
    diff = o - t
    corr = float(np.corrcoef(t, o)[0, 1]) if t.size > 1 else 0.0
    return CompareResult(
        mae=float(np.mean(np.abs(diff))),
        rmse=float(np.sqrt(np.mean(diff * diff))),
        correlation=corr,
        target_mean=float(np.mean(t)),
        target_std=float(np.std(t)),
        output_mean=float(np.mean(o)),
        output_std=float(np.std(o)),
    )


def print_compare(label: str, result: CompareResult) -> None:
    """Print compare.

    Args:
        label: ``str`` value.
        result: ``CompareResult`` value.
    """
    print(
        f"{label}: MAE={result.mae:.4f} RMSE={result.rmse:.4f} "
        f"corr={result.correlation:.4f} "
        f"target(mean={result.target_mean:.3f}, std={result.target_std:.3f}) "
        f"out(mean={result.output_mean:.3f}, std={result.output_std:.3f})"
    )

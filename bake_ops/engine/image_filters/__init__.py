"""Engine-wide image-to-image filters (map-type agnostic)."""
from __future__ import annotations

from . import (
    blur_cpu,
    blur_gpu,
    dilate_cpu,
    dilate_gpu,
    executor_cpu,
    executor_gpu,
    flip_png_v_cpu,
    flip_png_v_gpu,
    normalize_cpu,
    normalize_gpu,
    remap_coordinate_system_cpu,
    remap_coordinate_system_gpu,
    switch_normal_opengl_directx_cpu,
    switch_normal_opengl_directx_gpu,
)
from .blur_cpu import filter as blur_filter, island_gaussian_blur
from .blur_gpu import filter as blur_filter_gpu
from .dilate_cpu import DilateConfig, edge_dilate, filter as dilate_filter
from .dilate_gpu import filter as dilate_filter_gpu
from .executor_cpu import run_filter
from .executor_gpu import run_filter as run_filter_gpu
from .normalize_cpu import (
    filter_positive,
    filter_signed,
    percentile_scale,
    unitize_positive,
    unitize_signed,
)
from .normalize_gpu import filter_positive as filter_positive_gpu
from .normalize_gpu import filter_signed as filter_signed_gpu
from .remap_coordinate_system_cpu import (
    ExternalBakeSpace,
    external_convention,
    filter as remap_coordinate_filter,
)
from .remap_coordinate_system_gpu import filter as remap_coordinate_filter_gpu
from .flip_png_v_cpu import filter as flip_png_v_filter
from .flip_png_v_gpu import filter as flip_png_v_filter_gpu
from .switch_normal_opengl_directx_cpu import filter as switch_normal_filter
from .switch_normal_opengl_directx_gpu import filter as switch_normal_filter_gpu

__all__ = [
    "ExternalBakeSpace",
    "blur_cpu",
    "blur_filter",
    "blur_filter_gpu",
    "blur_gpu",
    "DilateConfig",
    "dilate_cpu",
    "dilate_filter",
    "dilate_filter_gpu",
    "dilate_gpu",
    "edge_dilate",
    "executor_cpu",
    "executor_gpu",
    "external_convention",
    "filter_positive",
    "filter_positive_gpu",
    "filter_signed",
    "filter_signed_gpu",
    "flip_png_v_cpu",
    "flip_png_v_filter",
    "flip_png_v_filter_gpu",
    "flip_png_v_gpu",
    "island_gaussian_blur",
    "normalize_cpu",
    "normalize_gpu",
    "percentile_scale",
    "remap_coordinate_filter",
    "remap_coordinate_filter_gpu",
    "remap_coordinate_system_cpu",
    "remap_coordinate_system_gpu",
    "run_filter",
    "run_filter_gpu",
    "switch_normal_filter",
    "switch_normal_filter_gpu",
    "switch_normal_opengl_directx_cpu",
    "switch_normal_opengl_directx_gpu",
    "unitize_positive",
    "unitize_signed",
]

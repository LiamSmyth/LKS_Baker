"""Registry device selection and execution-backend helpers."""
from __future__ import annotations

from .settings.curvature_settings import Backend


def resolve_registry_device(settings: Backend | str) -> str:
    """Map CurvatureSettings.backend to a registry device key ('cpu' or 'gpu')."""
    if settings is Backend.CPU or settings == Backend.CPU.value:
        return "cpu"
    if settings is Backend.GPU or settings == Backend.GPU.value:
        return "gpu"
    from lks_baker.bake_ops.engine.gpu.gpu_runtime import gpu_runtime_available

    return "gpu" if gpu_runtime_available() else "cpu"


def registry_device_uses_gpu(device: str) -> bool:
    """True when the registry device slot invokes GPU shaders/offscreen."""
    return device == "gpu"

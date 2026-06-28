"""Blender-facing bake adapters (lazy imports — avoid pulling PIL on package load)."""

from __future__ import annotations

__all__ = [
    "build_bake_input_from_bpy",
    "packed_gray_to_bpy_image",
    "resolve_engine_device",
    "resolve_engine_method_id",
    "try_derive_curvature_via_bake_engine",
    "execute_bake_job",
    "execute_bake_groups",
    "LKS_BakeGroupMeshes",
    "LKS_BakedMapResult",
]


def __getattr__(name: str):
    if name in {
        "build_bake_input_from_bpy",
        "packed_gray_to_bpy_image",
        "resolve_engine_device",
        "resolve_engine_method_id",
        "try_derive_curvature_via_bake_engine",
    }:
        from . import curvature_bridge, image_adapter

        if name == "try_derive_curvature_via_bake_engine":
            return curvature_bridge.try_derive_curvature_via_bake_engine
        return getattr(image_adapter, name)
    if name in {"execute_bake_job", "execute_bake_groups"}:
        from .job_adapter import execute_bake_groups as _exec_groups, execute_bake_job

        return execute_bake_job if name == "execute_bake_job" else _exec_groups
    if name in {"LKS_BakeGroupMeshes", "LKS_BakedMapResult"}:
        from .cycles_executor import LKS_BakeGroupMeshes, LKS_BakedMapResult

        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

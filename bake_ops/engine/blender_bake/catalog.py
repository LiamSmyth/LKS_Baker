"""Catalog helpers for Blender builtin Cycles bakes."""
from __future__ import annotations

from lks_baker.bake_ops.engine.catalog_bridge import (
    ENGINE_MAP_TYPE_ALIASES,
    LKS_BakeMapSpec,
    get_bake_map_spec,
    resolve_engine_map_type,
)

BLENDER_BUILTIN_METHOD_ID = "blender"
BLENDER_BUILTIN_DEVICE = "blender"

# Implemented catalog maps that map to ``bpy.ops.object.bake`` (Cycles native, COMBINED, or EMIT shader).
BLENDER_BUILTIN_MAP_IDS: tuple[str, ...] = (
    "normal",
    "normal_object",
    "position",
    "ao",
    "roughness",
    "albedo",
    "specular",
    "metalness",
    "emissive",
    "transparency",
    "vertex_color",
    "material_id",
    "object_id",
    "complete_lighting",
    "diffuse_lighting",
    "specular_lighting",
    "indirect_lighting",
)


def supports_blender_builtin_bake(spec: LKS_BakeMapSpec | None) -> bool:
    """True when *spec* has a registered Blender Cycles bake implementation."""
    if spec is None or not spec.implemented:
        return False
    engine_map_type = resolve_engine_map_type(spec.map_id)
    if engine_map_type not in BLENDER_BUILTIN_MAP_IDS:
        return False
    if spec.cycles_type is not None:
        return True
    if spec.blender_backend == "cycles_combined":
        return spec.cycles_type == "COMBINED"
    if spec.blender_backend == "texture_derive" and spec.derive_method is not None:
        return False
    return spec.blender_backend == "cycles_emit"


def iter_blender_builtin_specs() -> list[LKS_BakeMapSpec]:
    """Return catalog specs that expose the ``blender`` bake-engine method."""
    specs: list[LKS_BakeMapSpec] = []
    seen: set[str] = set()
    for map_id in (*BLENDER_BUILTIN_MAP_IDS, *ENGINE_MAP_TYPE_ALIASES):
        if map_id in seen:
            continue
        seen.add(map_id)
        spec = get_bake_map_spec(map_id)
        if supports_blender_builtin_bake(spec):
            specs.append(spec)
    return specs


def is_blender_builtin_map_id(map_id: str) -> bool:
    return supports_blender_builtin_bake(get_bake_map_spec(map_id))

"""Register bake map implementations by (map_type, method_id, device)."""
from __future__ import annotations

from typing import Type

from .bake_map import BakeMap
from lks_baker.bake_ops.engine.blender_bake.catalog import BLENDER_BUILTIN_METHOD_ID
from lks_baker.bake_ops.engine.blender_bake.register_maps import BLENDER_BUILTIN_BAKE_MAPS
from lks_baker.bake_ops.engine.catalog_bridge import resolve_engine_map_type
from lks_baker.bake_ops.engine.map_types.ao.register_ao_maps import AO_BAKE_MAPS
from lks_baker.bake_ops.engine.map_types.curvature.register_curvature_maps import (
    CURVATURE_BAKE_MAPS,
)
from lks_baker.bake_ops.engine.map_types.alpha_mask.alpha_mask_from_transparency_cpu import (
    AlphaMaskFromTransparencyCpu,
)
from lks_baker.bake_ops.engine.map_types.cavity.cavity_from_curvature_cpu import CavityFromCurvatureCpu
from lks_baker.bake_ops.engine.map_types.convexity.convexity_from_curvature_cpu import (
    ConvexityFromCurvatureCpu,
)
from lks_baker.bake_ops.engine.map_types.normal_object.normal_object_from_tangent_cpu import (
    NormalObjectFromTangentCpu,
)
from lks_baker.bake_ops.engine.map_types.uv_island.uv_island_from_mesh_cpu import UvIslandFromMeshCpu
from lks_baker.bake_ops.engine.map_types.bent_normal.register_bent_normal_maps import (
    BENT_NORMAL_BAKE_MAPS,
)
from lks_baker.bake_ops.engine.map_types.bent_normal_object.register_bent_normal_object_maps import (
    BENT_NORMAL_OBJECT_BAKE_MAPS,
)
from lks_baker.bake_ops.engine.map_types.group_id.group_id_raster_cpu import GroupIdRasterCpu
from lks_baker.bake_ops.engine.map_types.group_id.group_id_raster_gpu import GroupIdRasterGpu
from lks_baker.bake_ops.engine.map_types.specular.register_specular_maps import (
    SPECULAR_BAKE_MAPS,
)
from lks_baker.bake_ops.engine.map_types.wireframe.wireframe_uv_raster_cpu import WireframeUvRasterCpu
from lks_baker.bake_ops.engine.map_types.wireframe.wireframe_uv_raster_gpu import WireframeUvRasterGpu
from .settings.curvature_settings import Backend

_ALL_MAPS: tuple[Type[BakeMap], ...] = (
    *BLENDER_BUILTIN_BAKE_MAPS,
    *CURVATURE_BAKE_MAPS,
    *AO_BAKE_MAPS,
    *BENT_NORMAL_BAKE_MAPS,
    *BENT_NORMAL_OBJECT_BAKE_MAPS,
    CavityFromCurvatureCpu,
    ConvexityFromCurvatureCpu,
    NormalObjectFromTangentCpu,
    UvIslandFromMeshCpu,
    GroupIdRasterCpu,
    GroupIdRasterGpu,
    *SPECULAR_BAKE_MAPS,
    WireframeUvRasterCpu,
    WireframeUvRasterGpu,
    AlphaMaskFromTransparencyCpu,
)

_REGISTRY: dict[tuple[str, str, str], Type[BakeMap]] = {cls.key(): cls for cls in _ALL_MAPS}


def list_bake_maps() -> list[tuple[str, str, str]]:
    """Return sorted registry keys ``(map_type, method_id, device)``."""
    return sorted(_REGISTRY.keys())


_LEGACY_METHOD_IDS: dict[str, str] = {
    "object_normal_sd": "soft_curvature",
}


def _normalize_method_id(map_type: str, method_id: str) -> str:
    if map_type == "curvature":
        return _LEGACY_METHOD_IDS.get(method_id, method_id)
    return method_id


def list_by_map_type(map_type: str) -> list[tuple[str, str, str]]:
    """Return registry keys filtered to one ``map_type``."""
    return [key for key in _REGISTRY if key[0] == map_type]


def resolve_bake_map(
    map_type: str,
    method_id: str,
    device: str | Backend | None = None,
) -> BakeMap:
    """Instantiate a registered ``BakeMap`` implementation.

    Args:
        map_type: Catalog map family (e.g. ``"curvature"``).
        method_id: Method id; legacy aliases normalized for curvature.
        device: Explicit ``"cpu"``/``"gpu"``, or ``Backend.AUTO`` to pick first available GPU then CPU.

    Returns:
        Fresh instance of the matching ``BakeMap`` subclass.

    Raises:
        KeyError: When no implementation matches or GPU runtime is unavailable for auto GPU selection.
    """
    map_type = resolve_engine_map_type(map_type)
    method_id = _normalize_method_id(map_type, method_id)
    if device is not None and not isinstance(device, Backend):
        dev = str(device)
        if dev == "blender":
            key = (map_type, method_id, dev)
            if key not in _REGISTRY:
                raise KeyError(f"Unknown bake map {key!r}; known: {list_bake_maps()}")
            return _REGISTRY[key]()
    if method_id == BLENDER_BUILTIN_METHOD_ID and (device is None or device == Backend.AUTO):
        key = (map_type, BLENDER_BUILTIN_METHOD_ID, "blender")
        if key in _REGISTRY:
            return _REGISTRY[key]()
    if device is None or device == Backend.AUTO:
        for dev in ("gpu", "cpu"):
            key = (map_type, method_id, dev)
            if key not in _REGISTRY:
                continue
            if dev == "gpu":
                from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
                    gpu_runtime_available,
                )

                if not gpu_runtime_available():
                    continue
            return _REGISTRY[key]()
        raise KeyError(f"No available bake map for {map_type!r} / {method_id!r}")

    dev = device.value if isinstance(device, Backend) else str(device)
    key = (map_type, method_id, dev)
    if key not in _REGISTRY:
        raise KeyError(f"Unknown bake map {key!r}; known: {list_bake_maps()}")
    return _REGISTRY[key]()

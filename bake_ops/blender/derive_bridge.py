"""Bridge production texture derive to bake_engine for catalog derive maps."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .image_adapter import (
    bpy_image_to_rgba,
    packed_gray_to_bpy_image,
    rgba01_to_bpy_image,
    tbn_fields_png_rows,
)
from ..engine.bake_map import BakeMapInput
from ..engine.orchestrator import BakeEngine, BakeRequest
from ..engine.settings.curvature_settings import CurvatureSettings
from ..engine.static_utilities.bootstrap import ensure_bake_engine_deps
from ..engine.static_utilities.images import valid_mask_from_rgba
from ..engine.static_utilities.images import decode_tangent_normal

if TYPE_CHECKING:
    import bpy

    from ..static_utilities.bake_texture_derivatives import LKS_TBNRaster


def _engine_rgba_to_bpy_image(
    result,
    *,
    width: int,
    height: int,
    valid: np.ndarray,
    name: str,
) -> bpy.types.Image:
    rgba = result.output.meta.get("rgba")
    if rgba is not None:
        return rgba01_to_bpy_image(rgba, width=width, height=height, valid=valid, name=name)
    return packed_gray_to_bpy_image(
        result.output.packed,
        width=width,
        height=height,
        valid=valid,
        name=name,
    )


def try_derive_normal_object_via_bake_engine(
    normal_image: bpy.types.Image,
    *,
    tbn: LKS_TBNRaster,
) -> bpy.types.Image | None:
    """Run normal_object_from_tangent via bake_engine when TBN + TSNM are available."""
    ensure_bake_engine_deps()
    width, height = int(normal_image.size[0]), int(normal_image.size[1])
    if width != tbn.width or height != tbn.height:
        return None

    normal_rgba = bpy_image_to_rgba(normal_image, width=width, height=height)
    tangent_normal = decode_tangent_normal(normal_rgba)
    island_id, valid, tbn_tangent, tbn_bitangent, tbn_normal = tbn_fields_png_rows(tbn)
    # Match legacy derive_normal_object_from_tangent: TBN island_id >= 0 is the gate.
    # resolve_bake_valid_mask / valid_mask_from_rgba wrongly exclude flat tangent RGB.

    bake_input = BakeMapInput(
        valid=valid,
        island_id=island_id,
        tangent_normal=tangent_normal,
        normal_rgba=normal_rgba,
        image_size=height,
        settings=CurvatureSettings(),
        extra={
            "tbn_tangent": tbn_tangent,
            "tbn_bitangent": tbn_bitangent,
            "tbn_normal": tbn_normal,
        },
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="normal_object",
            method_id="normal_object_from_tangent",
            device="cpu",
            inputs=bake_input,
        ),
    )
    return _engine_rgba_to_bpy_image(
        result,
        width=width,
        height=height,
        valid=valid,
        name="_LKS_DERIVE_NORMAL_OBJECT",
    )


def try_derive_uv_island_via_bake_engine(
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
) -> bpy.types.Image | None:
    """Run uv_island_from_mesh via bake_engine when low mesh is available."""
    if low_mesh.type != "MESH" or low_mesh.data is None:
        return None

    from lks_baker.bake_ops.engine.static_utilities.blender_mesh import meshdata_from_object

    ensure_bake_engine_deps()
    mesh_data = meshdata_from_object(low_mesh, label="low")
    # Mesh derive computes its own raster valid; do not pass an all-false placeholder mask.
    bake_input = BakeMapInput(
        valid=np.ones((height, width), dtype=bool),
        island_id=np.full((height, width), -1, dtype=np.int32),
        low_mesh=mesh_data,
        mesh=mesh_data,
        image_size=height,
        settings=CurvatureSettings(),
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="uv_island",
            method_id="uv_island_from_mesh",
            device="cpu",
            inputs=bake_input,
        ),
    )
    valid = result.output.valid
    if valid is None:
        valid = np.ones((height, width), dtype=bool)
    return _engine_rgba_to_bpy_image(
        result,
        width=width,
        height=height,
        valid=valid,
        name="_LKS_DERIVE_UV_ISLAND",
    )


def try_derive_wireframe_via_bake_engine(
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    *,
    map_entry=None,
) -> bpy.types.Image | None:
    """Run wireframe_uv_raster via bake_engine when low mesh is available."""
    if low_mesh.type != "MESH" or low_mesh.data is None:
        return None

    from lks_baker.bake_ops.engine.map_types.wireframe.wireframe_uv_raster_cfg import (
        WireframeUvRasterConfig,
        config_from_entry,
    )
    from lks_baker.bake_ops.engine.static_utilities.blender_mesh import meshdata_from_object

    ensure_bake_engine_deps()
    mesh_data = meshdata_from_object(low_mesh, label="low")
    config: WireframeUvRasterConfig = (
        config_from_entry(map_entry) if map_entry is not None else WireframeUvRasterConfig()
    )
    bake_input = BakeMapInput(
        valid=np.ones((height, width), dtype=bool),
        island_id=np.full((height, width), -1, dtype=np.int32),
        low_mesh=mesh_data,
        mesh=mesh_data,
        image_size=height,
        settings=CurvatureSettings(),
        extra={"wireframe_config": config},
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="wireframe",
            method_id="wireframe_uv_raster",
            device="cpu",
            inputs=bake_input,
        ),
    )
    valid = result.output.valid
    if valid is None:
        valid = np.ones((height, width), dtype=bool)
    return _engine_rgba_to_bpy_image(
        result,
        width=width,
        height=height,
        valid=valid,
        name="_LKS_DERIVE_WIREFRAME",
    )


def try_derive_group_id_via_bake_engine(
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    *,
    map_entry=None,
) -> bpy.types.Image | None:
    """Run group_id_raster via bake_engine when low mesh is available."""
    if low_mesh.type != "MESH" or low_mesh.data is None:
        return None

    from lks_baker.bake_ops.engine.map_types.group_id.group_id_raster_cfg import (
        GroupIdRasterConfig,
        config_from_entry,
    )
    from lks_baker.bake_ops.engine.map_types.group_id.static_utilities.face_group_ids import (
        get_group_id_derive_skip_reason,
        mesh_with_face_int_ids,
        read_triangulated_face_int_ids_from_object,
    )
    from lks_baker.bake_ops.engine.static_utilities.blender_mesh import meshdata_from_object

    ensure_bake_engine_deps()
    if get_group_id_derive_skip_reason(low_mesh, map_entry=map_entry) is not None:
        return None

    config: GroupIdRasterConfig = (
        config_from_entry(map_entry) if map_entry is not None else GroupIdRasterConfig()
    )
    try:
        face_int_ids = read_triangulated_face_int_ids_from_object(
            low_mesh,
            config.attribute_name,
        )
    except ValueError:
        return None

    mesh_data = meshdata_from_object(low_mesh, label="low")
    mesh_data = mesh_with_face_int_ids(mesh_data, face_int_ids)
    bake_input = BakeMapInput(
        valid=np.ones((height, width), dtype=bool),
        island_id=np.full((height, width), -1, dtype=np.int32),
        low_mesh=mesh_data,
        mesh=mesh_data,
        image_size=height,
        settings=CurvatureSettings(),
        extra={
            "group_id_config": config,
            "face_int_ids": face_int_ids,
        },
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="group_id",
            method_id="group_id_raster",
            device="cpu",
            inputs=bake_input,
        ),
    )
    valid = result.output.valid
    if valid is None:
        valid = np.ones((height, width), dtype=bool)
    return _engine_rgba_to_bpy_image(
        result,
        width=width,
        height=height,
        valid=valid,
        name="_LKS_DERIVE_GROUP_ID",
    )


def try_derive_hemisphere_trace_via_bake_engine(
    normal_object_image: bpy.types.Image,
    position_image: bpy.types.Image,
    *,
    map_entry=None,
    tbn=None,
) -> bpy.types.Image | None:
    """Run bent_normal hemisphere_trace via bake_engine when OSNM + position atlases are available."""
    ensure_bake_engine_deps()
    width, height = int(normal_object_image.size[0]), int(normal_object_image.size[1])
    if width != int(position_image.size[0]) or height != int(position_image.size[1]):
        return None

    from lks_baker.bake_ops.engine.map_types.bent_normal.hemisphere_trace_cfg import (
        HemisphereTraceConfig,
        bent_normal_settings_from_config,
        config_from_entry,
    )
    from lks_baker.bake_ops.engine.static_utilities.images import (
        decode_object_normal,
        decode_position,
        valid_mask_from_rgba,
    )

    normal_rgba = bpy_image_to_rgba(normal_object_image, width=width, height=height)
    position_rgba = bpy_image_to_rgba(position_image, width=width, height=height)
    object_normal = decode_object_normal(normal_rgba)
    position = decode_position(position_rgba)
    valid = valid_mask_from_rgba(normal_rgba) & valid_mask_from_rgba(position_rgba)
    if tbn is not None and tbn.width == width and tbn.height == height:
        island_id, tbn_valid, _, _, _ = tbn_fields_png_rows(tbn)
        valid = valid & tbn_valid
    else:
        island_id = np.full((height, width), -1, dtype=np.int32)

    config: HemisphereTraceConfig = (
        config_from_entry(map_entry) if map_entry is not None else HemisphereTraceConfig()
    )
    bent_settings = bent_normal_settings_from_config(config)
    bake_input = BakeMapInput(
        valid=valid,
        island_id=island_id,
        object_normal=object_normal,
        position=position,
        object_rgba=normal_rgba,
        position_rgba=position_rgba,
        image_size=height,
        settings=CurvatureSettings(),
        extra={"bent_normal_settings": bent_settings},
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="bent_normal",
            method_id="hemisphere_trace",
            device="cpu",
            inputs=bake_input,
        ),
    )
    return _engine_rgba_to_bpy_image(
        result,
        width=width,
        height=height,
        valid=valid,
        name="_LKS_DERIVE_BENT_NORMAL",
    )


def try_derive_bent_normal_object_via_bake_engine(
    normal_object_image: bpy.types.Image,
    position_image: bpy.types.Image,
    *,
    map_entry=None,
    tbn=None,
) -> bpy.types.Image | None:
    """Run bent_normal_object via bake_engine when OSNM + position atlases are available."""
    ensure_bake_engine_deps()
    width, height = int(normal_object_image.size[0]), int(normal_object_image.size[1])
    if width != int(position_image.size[0]) or height != int(position_image.size[1]):
        return None

    from lks_baker.bake_ops.engine.map_types.bent_normal_object.bent_normal_object_cfg import (
        BentNormalObjectConfig,
        bent_normal_settings_from_config,
        config_from_entry,
    )
    from lks_baker.bake_ops.engine.static_utilities.images import (
        decode_object_normal,
        decode_position,
        valid_mask_from_rgba,
    )

    normal_rgba = bpy_image_to_rgba(normal_object_image, width=width, height=height)
    position_rgba = bpy_image_to_rgba(position_image, width=width, height=height)
    object_normal = decode_object_normal(normal_rgba)
    position = decode_position(position_rgba)
    valid = valid_mask_from_rgba(normal_rgba) & valid_mask_from_rgba(position_rgba)
    if tbn is not None and tbn.width == width and tbn.height == height:
        island_id, tbn_valid, _, _, _ = tbn_fields_png_rows(tbn)
        valid = valid & tbn_valid
    else:
        island_id = np.full((height, width), -1, dtype=np.int32)

    config: BentNormalObjectConfig = (
        config_from_entry(map_entry) if map_entry is not None else BentNormalObjectConfig()
    )
    bent_settings = bent_normal_settings_from_config(config)
    bake_input = BakeMapInput(
        valid=valid,
        island_id=island_id,
        object_normal=object_normal,
        position=position,
        object_rgba=normal_rgba,
        position_rgba=position_rgba,
        image_size=height,
        settings=CurvatureSettings(),
        extra={"bent_normal_settings": bent_settings},
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="bent_normal_object",
            method_id="bent_normal_object",
            device="cpu",
            inputs=bake_input,
        ),
    )
    return _engine_rgba_to_bpy_image(
        result,
        width=width,
        height=height,
        valid=valid,
        name="_LKS_DERIVE_BENT_NORMAL_OBJECT",
    )


def try_derive_alpha_mask_via_bake_engine(
    transparency_image: bpy.types.Image,
) -> bpy.types.Image | None:
    """Run alpha_mask_from_transparency via bake_engine."""
    ensure_bake_engine_deps()
    width, height = int(transparency_image.size[0]), int(transparency_image.size[1])
    rgba = bpy_image_to_rgba(transparency_image, width=width, height=height)
    valid = valid_mask_from_rgba(rgba)
    bake_input = BakeMapInput(
        valid=valid,
        island_id=np.full((height, width), -1, dtype=np.int32),
        image_size=height,
        settings=CurvatureSettings(),
        extra={"transparency_rgba": rgba},
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="alpha_mask",
            method_id="alpha_mask_from_transparency",
            device="cpu",
            inputs=bake_input,
        ),
    )
    return packed_gray_to_bpy_image(
        result.output.packed,
        width=width,
        height=height,
        valid=valid,
        name="_LKS_DERIVE_ALPHA_MASK",
    )

"""Run registered bake-engine CPU/GPU methods from production Blender context."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .image_adapter import (
    bpy_image_to_rgba,
    build_bake_input_from_bpy,
    island_id_from_tbn,
    packed_gray_to_bpy_image,
    rgba01_to_bpy_image,
)
from ..engine.bake_map import BakeMapInput
from ..engine.orchestrator import BakeEngine, BakeRequest
from ..engine.settings.ao_settings import AoSettings
from ..engine.settings.production_mapping import curvature_settings_from_constants
from ..engine.static_utilities.bootstrap import ensure_bake_engine_deps
from ..engine.static_utilities.debug_texels import resolve_coverage_mask
from ..engine.static_utilities.images import (
    decode_object_normal,
    decode_position,
    decode_tangent_normal,
    resolve_bake_valid_mask,
)
from ..static_utilities.bake_map_catalog import resolve_engine_map_type
from ..static_utilities.bake_texture_derivatives import raster_tbn_from_low_mesh

if TYPE_CHECKING:
    import bpy

    from ..static_utilities.bake_texture_derivatives import LKS_TBNRaster

_OSNM_ENGINE_METHODS = frozenset({
    'atlas_hbao',
    'normal_height_hbao',
    'height_hbao',
    'ao_composite',
})
_TSNM_ENGINE_METHODS = frozenset({'normal_cavity'})
_SPECULAR_EMIT_METHODS = frozenset({'emit_raster'})


def _attach_specular_emit_inputs(
    bake_input: BakeMapInput,
    *,
    low_mesh: bpy.types.Object,
    high_mesh: bpy.types.Object,
    map_entry=None,
    project=None,
) -> BakeMapInput:
    from lks_baker.bake_ops.engine.map_types.specular.emit_raster_cfg import (
        config_from_entry as emit_raster_config_from_entry,
    )
    from lks_baker.bake_ops.engine.static_utilities.blender_mesh import (
        meshdata_from_object,
    )
    from lks_baker.bake_ops.engine.static_utilities.mesh_material_emit import (
        mesh_material_emit_data_from_object,
    )

    bake_input.low_mesh = meshdata_from_object(low_mesh, label='low')
    bake_input.high_mesh = meshdata_from_object(high_mesh, label='high')
    bake_input.mesh = bake_input.low_mesh
    bake_input.extra['mesh_material_emit_data'] = mesh_material_emit_data_from_object(
        high_mesh,
        'specular',
    )
    if map_entry is not None:
        bake_input.extra['emit_raster_config'] = emit_raster_config_from_entry(
            map_entry,
            project=project,
        )
    return bake_input


def _build_osnm_bake_input(
    input_images: dict[str, bpy.types.Image],
    tbn: LKS_TBNRaster,
    *,
    method_id: str,
    image_size: int,
    map_entry=None,
) -> BakeMapInput:
    object_img = input_images.get('normal_object')
    position_img = input_images.get('position')
    if object_img is None or position_img is None:
        raise RuntimeError(
            f"Engine method '{method_id}' requires normal_object and position inputs",
        )
    width, height = tbn.width, tbn.height
    object_rgba = bpy_image_to_rgba(object_img, width=width, height=height)
    position_rgba = bpy_image_to_rgba(position_img, width=width, height=height)
    normal_rgba = object_rgba
    normal_img = input_images.get('normal')
    tangent_normal = None
    if normal_img is not None:
        normal_rgba = bpy_image_to_rgba(normal_img, width=width, height=height)
        tangent_normal = decode_tangent_normal(normal_rgba)
    island_id, tbn_valid = island_id_from_tbn(tbn)
    valid = resolve_bake_valid_mask(normal_rgba, object_rgba, position_rgba) & tbn_valid
    return BakeMapInput(
        valid=valid,
        island_id=island_id,
        tangent_normal=tangent_normal,
        object_normal=decode_object_normal(object_rgba),
        position=decode_position(position_rgba),
        normal_rgba=normal_rgba,
        object_rgba=object_rgba,
        position_rgba=position_rgba,
        image_size=image_size,
        settings=curvature_settings_from_constants(
            map_entry=map_entry,
            method_id=method_id,
            image_size=image_size,
        ),
    )


def _build_engine_bake_input(
    input_images: dict[str, bpy.types.Image],
    tbn: LKS_TBNRaster,
    *,
    method_id: str,
    map_type: str,
    image_size: int,
    map_entry=None,
    low_mesh: bpy.types.Object | None = None,
    high_mesh: bpy.types.Object | None = None,
    project=None,
) -> BakeMapInput:
    """Build ``BakeMapInput`` for a registered non-blender engine method."""
    if method_id in _OSNM_ENGINE_METHODS:
        bake_input = _build_osnm_bake_input(
            input_images,
            tbn,
            method_id=method_id,
            image_size=image_size,
            map_entry=map_entry,
        )
    elif method_id in _TSNM_ENGINE_METHODS:
        normal_img = input_images.get('normal')
        if normal_img is None:
            raise RuntimeError(f"Engine method '{method_id}' requires tangent normal input")
        width, height = int(normal_img.size[0]), int(normal_img.size[1])
        normal_rgba = bpy_image_to_rgba(normal_img, width=width, height=height)
        tangent_normal = decode_tangent_normal(normal_rgba)
        island_id, valid = island_id_from_tbn(tbn)
        bake_input = BakeMapInput(
            valid=valid,
            island_id=island_id,
            tangent_normal=tangent_normal,
            normal_rgba=normal_rgba,
            image_size=height,
            settings=curvature_settings_from_constants(
                map_entry=map_entry,
                method_id=method_id,
                image_size=image_size,
            ),
        )
    else:
        bake_input = build_bake_input_from_bpy(
            input_images,
            tbn,
            settings=curvature_settings_from_constants(
                map_entry=map_entry,
                method_id=method_id,
                image_size=image_size,
            ),
            engine_method_id=method_id,
        )
        if bake_input is None:
            raise RuntimeError(f"Engine method '{method_id}' could not resolve required inputs")

    if map_type == 'ao':
        bake_input.extra['ao_settings'] = AoSettings(max_size=image_size, debug_texel_fail=False)
    if map_type == 'specular' and method_id in _SPECULAR_EMIT_METHODS:
        if low_mesh is None or high_mesh is None:
            raise RuntimeError("emit_raster requires low and high mesh objects")
        bake_input = _attach_specular_emit_inputs(
            bake_input,
            low_mesh=low_mesh,
            high_mesh=high_mesh,
            map_entry=map_entry,
            project=project,
        )
    return bake_input


def run_engine_method_to_bpy_image(
    map_id: str,
    method_id: str,
    *,
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    input_images: dict[str, bpy.types.Image],
    tbn_cache: LKS_TBNRaster | None = None,
    map_entry=None,
    high_mesh: bpy.types.Object | None = None,
    project=None,
) -> bpy.types.Image:
    """Execute one registered CPU/GPU bake-engine method and return a Blender image."""
    ensure_bake_engine_deps()
    map_type = resolve_engine_map_type(map_id)
    tbn = tbn_cache or raster_tbn_from_low_mesh(low_mesh, width, height)
    bake_input = _build_engine_bake_input(
        input_images,
        tbn,
        method_id=method_id,
        map_type=map_type,
        image_size=width,
        map_entry=map_entry,
        low_mesh=low_mesh,
        high_mesh=high_mesh,
        project=project,
    )
    settings = bake_input.settings
    result = BakeEngine().bake(
        BakeRequest(
            map_type=map_type,
            method_id=method_id,
            device='cpu',
            inputs=bake_input,
            settings=settings,
        ),
    )
    coverage = resolve_coverage_mask(bake_input.valid, result.output.valid)
    rgba = result.output.meta.get('rgba')
    if rgba is not None:
        return rgba01_to_bpy_image(
            rgba,
            width=width,
            height=height,
            valid=coverage,
            name=f'_LKS_ENGINE_{map_id.upper()}',
        )
    return packed_gray_to_bpy_image(
        result.output.packed,
        width=width,
        height=height,
        valid=coverage,
        name=f'_LKS_ENGINE_{map_id.upper()}',
    )

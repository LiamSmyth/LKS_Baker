"""Bridge production texture derive to bake_engine."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .image_adapter import (
    build_bake_input_from_bpy,
    packed_gray_to_bpy_image,
    resolve_engine_device,
    resolve_engine_method_id,
)
from ..engine.orchestrator import BakeEngine, BakeRequest
from ..engine.settings.production_mapping import curvature_settings_from_constants
from ..engine.static_utilities.bootstrap import ensure_bake_engine_deps
from ..engine.static_utilities.debug_texels import resolve_coverage_mask

if TYPE_CHECKING:
    import bpy

    from ..static_utilities.bake_texture_derivatives import LKS_TBNRaster


def try_derive_curvature_via_bake_engine(
    input_images: dict[str, bpy.types.Image],
    *,
    tbn: LKS_TBNRaster,
    low_mesh: bpy.types.Object | None = None,
    method_id: str = "auto",
    device: str = "cpu",
    tangent_strength: float = 0.5,
    world_strength: float = 0.1,
    map_entry=None,
    image_size: int | None = None,
) -> bpy.types.Image | None:
    """Run bake_engine curvature when inputs are sufficient; else return None."""
    resolved_method = resolve_engine_method_id(input_images, preferred=method_id)
    if resolved_method is None:
        return None

    ensure_bake_engine_deps()
    settings = curvature_settings_from_constants(
        backend=device,
        tangent_strength=tangent_strength,
        world_strength=world_strength,
        method_id=resolved_method,
        map_entry=map_entry,
        image_size=image_size or tbn.width,
    )
    bake_input = build_bake_input_from_bpy(
        input_images,
        tbn,
        settings=settings,
        low_mesh=low_mesh,
        engine_method_id=resolved_method,
    )
    if bake_input is None:
        return None

    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type="curvature",
            method_id=resolved_method,
            device=resolve_engine_device(device),
            inputs=bake_input,
            settings=settings,
        )
    )
    coverage = resolve_coverage_mask(bake_input.valid, result.output.valid)
    return packed_gray_to_bpy_image(
        result.output.packed,
        width=tbn.width,
        height=tbn.height,
        valid=coverage,
    )


def try_derive_split_via_bake_engine(
    curvature_image: bpy.types.Image,
    *,
    tbn: LKS_TBNRaster,
    map_type: str,
    method_id: str,
) -> bpy.types.Image | None:
    """Derive convexity/cavity split from a packed curvature map via bake_engine."""
    import numpy as np

    from .image_adapter import bpy_image_to_rgba, island_id_from_tbn, packed_gray_to_bpy_image

    ensure_bake_engine_deps()
    width, height = int(curvature_image.size[0]), int(curvature_image.size[1])
    curv_rgba = bpy_image_to_rgba(curvature_image, width=width, height=height)
    packed = curv_rgba[..., 0].astype(np.float32, copy=False)
    island_id, tbn_valid = island_id_from_tbn(tbn)
    valid = (packed > 1e-8) & tbn_valid

    from lks_baker.bake_ops.engine.bake_map import BakeMapInput
    from lks_baker.bake_ops.engine.orchestrator import BakeEngine, BakeRequest
    from lks_baker.bake_ops.engine.settings.curvature_settings import CurvatureSettings

    bake_input = BakeMapInput(
        valid=valid,
        island_id=island_id,
        image_size=height,
        settings=CurvatureSettings(),
        extra={"curvature_packed": packed},
    )
    engine = BakeEngine()
    result = engine.bake(
        BakeRequest(
            map_type=map_type,
            method_id=method_id,
            device="cpu",
            inputs=bake_input,
        )
    )
    return packed_gray_to_bpy_image(
        result.output.packed,
        width=width,
        height=height,
        valid=valid,
    )

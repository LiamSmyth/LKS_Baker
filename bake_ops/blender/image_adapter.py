"""Convert Blender bake images + TBN raster into BakeMapInput."""
from __future__ import annotations

from array import array
from typing import TYPE_CHECKING

import numpy as np

from ..engine.bake_map import BakeMapInput
from ..engine.settings.curvature_settings import Backend, CurvatureSettings
from ..engine.static_utilities.images import (
    blender_pixels_to_png_rows,
    decode_object_normal,
    decode_position,
    decode_tangent_normal,
    png_rows_to_blender_pixels,
    resize_rgba01,
    resolve_bake_valid_mask,
)

if TYPE_CHECKING:
    import bpy

    from lks_baker.bake_ops.static_utilities.bake_texture_derivatives import LKS_TBNRaster


def bpy_image_to_rgba(image: bpy.types.Image, *, width: int | None = None, height: int | None = None) -> np.ndarray:
    src_w, src_h = int(image.size[0]), int(image.size[1])
    if src_w <= 0 or src_h <= 0:
        raise RuntimeError(f"Image '{image.name}' has invalid dimensions")
    pixels = np.empty(src_w * src_h * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    rgba = blender_pixels_to_png_rows(pixels.reshape((src_h, src_w, 4)))
    if width is None:
        width = src_w
    if height is None:
        height = src_h
    if width == src_w and height == src_h:
        return rgba
    return resize_rgba01(rgba, width, height)


def island_id_from_tbn(tbn: LKS_TBNRaster) -> tuple[np.ndarray, np.ndarray]:
    """Return island_id H×W in internal PNG row order (row 0 = UV top)."""
    height, width = tbn.height, tbn.width
    island = np.asarray(tbn.island_id, dtype=np.int32).reshape(height, width)
    valid = island >= 0
    return island, valid


def island_id_blender_pixels_flat(tbn: LKS_TBNRaster) -> array:
    """Flat island ids in Blender ``Image.pixels`` order (bottom row first).

    ``LKS_TBNRaster`` stores PNG row order from ``raster_tbn_from_low_mesh``; dilate
    and post-process walk ``image.pixels`` in Blender order — flip once here.
    """
    height, width = tbn.height, tbn.width
    island = np.asarray(tbn.island_id, dtype=np.int32).reshape(height, width)
    return array("i", np.flipud(island).reshape(-1).tolist())


def tbn_arrays_from_raster(tbn: LKS_TBNRaster) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode flat TBN raster buffers into H×W×3 float32 arrays in -1..1."""
    height, width = tbn.height, tbn.width
    count = width * height

    def _decode(channel: object) -> np.ndarray:
        flat = np.asarray(channel, dtype=np.float32)
        rgb = flat.reshape(count, 4)[..., :3]
        return (rgb * 2.0 - 1.0).reshape(height, width, 3)

    return _decode(tbn.tangent), _decode(tbn.bitangent), _decode(tbn.normal)


def tbn_fields_png_rows(
    tbn: LKS_TBNRaster,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return island_id, valid, and T/B/N arrays in PNG row order (row 0 = UV top).

    ``raster_tbn_from_low_mesh`` already writes OpenGL/PNG layout via ``_uv_to_pixel_xy``.
    Do not flip here — ``bpy_image_to_rgba`` is the only ingest flip for Cycles images.
    """
    island_id, valid = island_id_from_tbn(tbn)
    tbn_tangent, tbn_bitangent, tbn_normal = tbn_arrays_from_raster(tbn)
    return island_id, valid, tbn_tangent, tbn_bitangent, tbn_normal


def build_bake_input_from_bpy(
    input_images: dict[str, bpy.types.Image],
    tbn: LKS_TBNRaster,
    settings: CurvatureSettings | None = None,
    *,
    low_mesh: bpy.types.Object | None = None,
    engine_method_id: str | None = None,
) -> BakeMapInput | None:
    """Build BakeMapInput from derive inputs and optional low-poly mesh."""
    settings = settings or CurvatureSettings()
    height, width = tbn.height, tbn.width

    normal_img = input_images.get("normal")
    object_img = input_images.get("normal_object")
    if engine_method_id == "soft_curvature":
        if object_img is None:
            return None
    elif normal_img is None:
        return None

    if normal_img is not None:
        normal_rgba = bpy_image_to_rgba(normal_img, width=width, height=height)
        tangent_normal = decode_tangent_normal(normal_rgba)
    else:
        normal_rgba = bpy_image_to_rgba(object_img, width=width, height=height)
        tangent_normal = decode_tangent_normal(normal_rgba)

    if object_img is not None:
        object_rgba = bpy_image_to_rgba(object_img, width=width, height=height)
        object_normal = decode_object_normal(object_rgba)
    else:
        object_rgba = normal_rgba
        object_normal = decode_object_normal(object_rgba)

    position = np.zeros_like(tangent_normal)
    position_rgba = np.zeros_like(normal_rgba)
    position_rgba[..., :3] = 0.5
    position_rgba[..., 3] = 1.0
    position_img = input_images.get("position")
    if position_img is not None:
        position_rgba = bpy_image_to_rgba(position_img, width=width, height=height)
        position = decode_position(position_rgba)

    island_id, tbn_valid = island_id_from_tbn(tbn)
    valid = resolve_bake_valid_mask(normal_rgba, object_rgba, position_rgba) & tbn_valid

    low_mesh_data = None
    if low_mesh is not None and low_mesh.type == "MESH":
        from lks_baker.bake_ops.engine.static_utilities.blender_mesh import (
            meshdata_from_object,
        )

        mesh_space = "object" if engine_method_id == "soft_curvature" else "world"
        low_mesh_data = meshdata_from_object(low_mesh, label="low", space=mesh_space)

    if engine_method_id == "soft_curvature" and low_mesh_data is None:
        return None

    return BakeMapInput(
        valid=valid,
        island_id=island_id,
        tangent_normal=tangent_normal,
        object_normal=object_normal,
        position=position,
        normal_rgba=normal_rgba,
        object_rgba=object_rgba,
        position_rgba=position_rgba,
        low_mesh=low_mesh_data,
        mesh=low_mesh_data,
        image_size=height,
        settings=settings,
    )


def resolve_engine_method_id(
    input_images: dict[str, bpy.types.Image],
    *,
    preferred: str = "auto",
) -> str | None:
    if preferred not in ("auto", ""):
        if preferred in ("soft_curvature", "object_normal_sd"):
            if input_images.get("normal_object") is not None:
                return "soft_curvature"
            return None
        return None
    if input_images.get("normal_object") is not None:
        return "soft_curvature"
    return None


def resolve_engine_device(device: str) -> str | Backend:
    if device.upper() == "AUTO":
        return Backend.AUTO
    if device.upper() == "GPU":
        return Backend.GPU
    return "cpu"


def packed_gray_to_bpy_image(
    packed: np.ndarray,
    *,
    width: int,
    height: int,
    valid: np.ndarray,
    name: str = "_LKS_BAKE_ENGINE_CURVATURE",
) -> bpy.types.Image:
    import bpy

    out = np.zeros((height, width, 4), dtype=np.float32)
    gray = np.clip(packed, 0.0, 1.0)
    out[..., 0] = gray
    out[..., 1] = gray
    out[..., 2] = gray
    out[..., 3] = 1.0
    out[~valid] = 0.0
    flat = png_rows_to_blender_pixels(out)
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(flat)
    image.update()
    return image


def rgba01_to_bpy_image(
    rgba: np.ndarray,
    *,
    width: int,
    height: int,
    valid: np.ndarray,
    name: str = "_LKS_BAKE_ENGINE_RGBA",
) -> bpy.types.Image:
    """Write H×W×4 float01 RGBA into a new Blender image."""
    import bpy

    out = np.clip(rgba.astype(np.float32, copy=False), 0.0, 1.0)
    if out.shape[0] != height or out.shape[1] != width:
        raise RuntimeError(f"rgba shape {out.shape[:2]} != ({height}, {width})")
    out = out.copy()
    out[~valid] = 0.0
    flat = png_rows_to_blender_pixels(out)
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(flat)
    image.update()
    return image

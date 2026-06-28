"""Bake texture file format and bit-depth output settings."""

from __future__ import annotations

from pathlib import Path

from lks_baker.shared_utilities.lks_constants import (
    BAKE_IMAGE_BLENDER_FILE_FORMAT,
    BAKE_IMAGE_COLOR_DEPTH_DEFAULT,
    BAKE_IMAGE_COLOR_DEPTH_DEFAULTS_BY_FILE_TYPE,
    BAKE_IMAGE_COLOR_DEPTHS_BY_FILE_TYPE,
    BAKE_IMAGE_FILE_TYPE_DEFAULT,
    BAKE_IMAGE_SAVE_SCENE_NAME,
)


def bake_image_file_type(project) -> str:
    return getattr(project, 'lks_image_file_type', BAKE_IMAGE_FILE_TYPE_DEFAULT)


def bake_image_blender_file_format(image_file_type: str) -> str:
    return BAKE_IMAGE_BLENDER_FILE_FORMAT.get(image_file_type, 'PNG')


def bake_image_color_depth_items_for_file_type(image_file_type: str):
    return BAKE_IMAGE_COLOR_DEPTHS_BY_FILE_TYPE.get(
        image_file_type,
        BAKE_IMAGE_COLOR_DEPTHS_BY_FILE_TYPE['PNG'],
    )


def bake_image_color_depth_default_for_file_type(image_file_type: str) -> str:
    return BAKE_IMAGE_COLOR_DEPTH_DEFAULTS_BY_FILE_TYPE.get(
        image_file_type,
        BAKE_IMAGE_COLOR_DEPTH_DEFAULT,
    )


def valid_bake_image_color_depths(image_file_type: str) -> set[str]:
    return {item[0] for item in bake_image_color_depth_items_for_file_type(image_file_type)}


def resolve_bake_image_color_depth(project) -> str:
    """Coerce stored depth to a value valid for the project's file type."""
    file_type = bake_image_file_type(project)
    depth = getattr(project, 'lks_image_color_depth', BAKE_IMAGE_COLOR_DEPTH_DEFAULT)
    valid = valid_bake_image_color_depths(file_type)
    if depth in valid:
        return depth
    return bake_image_color_depth_default_for_file_type(file_type)


def bake_image_wants_float_buffer(project) -> bool:
    return resolve_bake_image_color_depth(project) in {'16', '32'}


def apply_bake_image_output_settings(image, project) -> None:
    image.file_format = bake_image_blender_file_format(bake_image_file_type(project))


def _bake_image_save_scene():
    """Dedicated scene for ``save_render`` so user render output (e.g. FFMPEG) is untouched."""
    import bpy

    scene = bpy.data.scenes.get(BAKE_IMAGE_SAVE_SCENE_NAME)
    if scene is None:
        scene = bpy.data.scenes.new(BAKE_IMAGE_SAVE_SCENE_NAME)
    return scene


def save_bake_image_to_disk(
    image,
    filepath: Path,
    project,
) -> None:
    """Save baked pixels using project format + bit depth via an isolated save scene."""
    import bpy

    file_type = bake_image_file_type(project)
    blender_format = bake_image_blender_file_format(file_type)
    color_depth = resolve_bake_image_color_depth(project)

    filepath.parent.mkdir(parents=True, exist_ok=True)
    abs_path = bpy.path.abspath(str(filepath))
    image.filepath_raw = abs_path
    image.file_format = blender_format

    save_scene = _bake_image_save_scene()
    settings = save_scene.render.image_settings
    settings.file_format = blender_format
    settings.color_depth = color_depth
    image.save_render(filepath=abs_path, scene=save_scene)

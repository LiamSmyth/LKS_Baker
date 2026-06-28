"""Post-bake image denoise helpers — compositor OIDN (phase 1)."""

from __future__ import annotations

import logging
import os
import tempfile

import bpy

from .bake_map_catalog import get_bake_map_spec

_log = logging.getLogger(__name__)

_POST_DENOISE_ELIGIBLE_MAP_IDS: frozenset[str] = frozenset({'ao', 'ao_2'})


def post_denoise_eligible(map_id: str) -> bool:
    """Return whether ``map_id`` may use post-bake denoise (catalog or phase-1 set)."""
    spec = get_bake_map_spec(map_id)
    if spec is not None and spec.post_denoise_eligible:
        return True
    return map_id in _POST_DENOISE_ELIGIBLE_MAP_IDS


def denoise_bake_image(
    image: bpy.types.Image,
    *,
    map_id: str,
    strength: float = 1.0,
) -> bool:
    """Denoise bake ``image`` in-place. Returns True when pixels updated."""
    del map_id  # retained for call-site compatibility; gating is per-map RNA flag
    if strength <= 0.0:
        return False
    return denoise_image_oidn_compositor(image)


def _flip_rgba_rows_bottom_first(
    rgba: list[float],
    width: int,
    height: int,
) -> list[float]:
    """OIIO / file buffers are top-first; ``Image.pixels`` is bottom-first."""
    row_stride = width * 4
    return [
        rgba[src_row * row_stride + col]
        for src_row in range(height - 1, -1, -1)
        for col in range(row_stride)
    ]


def _read_rgba_from_exr(filepath: str, width: int, height: int) -> list[float] | None:
    """Read flat RGBA pixels from compositor EXR (``Image.load`` is unreliable on ML EXR)."""
    try:
        import OpenImageIO as oiio
    except ImportError:
        return None

    buf = oiio.ImageBuf(filepath)
    if buf.has_error:
        _log.warning('OpenImageIO read failed: %s', buf.geterror())
        return None
    spec = buf.spec()
    if spec.width != width or spec.height != height:
        _log.warning(
            'OpenImageIO size mismatch %sx%s vs %sx%s',
            spec.width, spec.height, width, height,
        )
        return None
    channels = spec.nchannels
    pixels = buf.get_pixels(oiio.FLOAT)
    flat = pixels.astype('f').ravel().tolist()
    expected = width * height * 4
    if len(flat) == expected:
        return _flip_rgba_rows_bottom_first(flat, width, height)
    if channels == 3 and len(flat) == width * height * 3:
        rgba: list[float] = []
        for i in range(0, len(flat), 3):
            rgba.extend((flat[i], flat[i + 1], flat[i + 2], 1.0))
        return _flip_rgba_rows_bottom_first(rgba, width, height)
    _log.warning('OpenImageIO channel count unexpected: %s floats', len(flat))
    return None


def denoise_image_oidn_compositor(image: bpy.types.Image) -> bool:
    """Ephemeral scene compositor: Image -> OIDN Denoise -> temp EXR -> pixels.

    Blender 5.1 uses ``Scene.compositing_node_group`` (``Scene.node_tree`` removed).
    ``CompositorNodeComposite`` is gone; File Output writes via ``file_output_items``.
    EXR readback uses bundled ``OpenImageIO`` because ``bpy.data.images.load`` leaves
    multilayer EXR at 0×0. On failure logs a warning and returns False.
    """
    width, height = image.size[0], image.size[1]
    if width < 1 or height < 1:
        return False

    scene_name = '_lks_bake_denoise'
    tree_name = '_lks_bake_denoise_tree'

    scene: bpy.types.Scene | None = None
    tree: bpy.types.NodeTree | None = None
    prev_scene = bpy.context.window.scene if bpy.context.window else None
    tmpdir: str | None = None

    try:
        scene = bpy.data.scenes.new(scene_name)
        scene.render.engine = 'CYCLES'
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.use_compositing = True

        tree = bpy.data.node_groups.new(tree_name, 'CompositorNodeTree')
        scene.compositing_node_group = tree
        tree.nodes.clear()

        img_in = tree.nodes.new('CompositorNodeImage')
        img_in.image = image
        denoise = tree.nodes.new('CompositorNodeDenoise')
        file_out = tree.nodes.new('CompositorNodeOutputFile')
        tmpdir = tempfile.mkdtemp(prefix='lks_bake_denoise_')
        file_out.directory = tmpdir + os.sep
        file_out.file_name = 'denoised'

        if hasattr(file_out, 'file_output_items'):
            file_out.file_output_items.new('RGBA', 'Image')

        tree.links.new(img_in.outputs['Image'], denoise.inputs['Image'])
        file_in = file_out.inputs[0] if len(file_out.inputs) else file_out.inputs['Image']
        tree.links.new(denoise.outputs['Image'], file_in)

        if bpy.context.window is not None:
            bpy.context.window.scene = scene
        bpy.ops.render.render(write_still=False)

        written_path: str | None = None
        if tmpdir and os.path.isdir(tmpdir):
            for entry in sorted(os.listdir(tmpdir)):
                if entry.endswith(('.exr', '.png', '.tif', '.tiff')):
                    written_path = os.path.join(tmpdir, entry)
                    break

        if written_path is None:
            _log.warning('OIDN compositor denoise produced no output file — skipping')
            return False

        rgba = _read_rgba_from_exr(written_path, width, height)
        if rgba is None:
            _log.warning('OIDN compositor denoise EXR readback failed — skipping')
            return False

        image.pixels.foreach_set(rgba)
        image.update()
        return True
    except Exception as exc:
        _log.warning('OIDN compositor denoise failed (%s) — skipping', exc)
        return False
    finally:
        if prev_scene is not None and bpy.context.window is not None:
            bpy.context.window.scene = prev_scene
        if scene is not None and scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(scene)
        if tree is not None and tree.name in bpy.data.node_groups:
            bpy.data.node_groups.remove(tree)
        if tmpdir and os.path.isdir(tmpdir):
            for entry in os.listdir(tmpdir):
                try:
                    os.remove(os.path.join(tmpdir, entry))
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass


def should_denoise_map_entry(map_entry, map_id: str) -> bool:
    """Gate denoise on per-map RNA flag (catalog eligibility is advisory only)."""
    del map_id  # retained for call-site compatibility
    return map_entry is not None and getattr(map_entry, 'lks_post_denoise', False)

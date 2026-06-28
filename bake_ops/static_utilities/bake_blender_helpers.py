"""Cycles bake compile + execute — dispatch table keyed by catalog map_id."""

from __future__ import annotations

import os
from array import array
from dataclasses import dataclass, field
from pathlib import Path

import bpy
import numpy as np

from .bake_export_helpers import ensure_export_directory
from .bake_low_material_helpers import (
    bake_image_file_extension,
    ensure_bake_project_low_material,
)
from ..engine.planner import (
    compile_bake_job_steps,
    resolve_map_backend_preference,
    select_map_backend,
)
from .bake_map_catalog import LKS_BakeMapSpec, get_bake_map_spec, resolve_engine_map_type
from .bake_margin_helpers import (
    resolve_bake_margin_pixels,
    resolve_cycles_bake_margin_pixels,
    resolve_dilate_config,
)
from .bake_resolution_helpers import resolve_bake_texture_dimensions
from .bake_shader_override_helpers import BakeMaterialOverrideStack
from .bake_shader_profiles import (
    apply_bbox_position_emit_profile,
    apply_emit_profile_for_map,
    map_id_uses_emit_profile,
)
from .bake_texture_derivatives import (
    LKS_TBNRaster,
    TextureDeriveSkip,
    execute_texture_derive,
    raster_tbn_from_low_mesh,
)
from .bake_post_process_helpers import apply_map_post_process
from .bake_texture_dilate_helpers import dilate_bake_image
from .bake_debug_log_helpers import log_step, timed_step
from .bake_progress_helpers import bake_progress_map_label, bake_progress_report
from .bake_method_catalog import resolve_map_entry_bake_method
from .bake_timing_helpers import BACKEND_DERIVE, BACKEND_ENGINE, BACKEND_MESH, BakeMapTimingState, record_bake_map_timing
from .bake_view_layer_helpers import (
    ensure_bake_targets_visible,
    ensure_objects_in_active_view_layer,
    isolate_scene_to_bake_targets,
    restore_scene_object_visibility,
)
from lks_baker.bake_ops.engine.map_types.lighting.lighting_pass_filter import (
    apply_combined_pass_filter,
    resolve_lighting_pass_filter,
    uses_cycles_combined_backend,
)
from lks_baker.bake_ops.engine.map_types.lighting.blender_cfg import (
    LightingBakeConfig,
    config_from_entry as lighting_config_from_entry,
)
from lks_baker.shared_utilities.filepath_helpers import get_abspath_from_relpath
from lks_baker.shared_utilities.group_empty_helpers import bbox_min_max, combined_world_bbox_corners

_MAP_BAKE_BLOCKERS: dict[str, str] = {
    'thickness': 'Thickness bake backend not chosen',
    'height': 'Height emit profile requires resources/bake_shaders.blend',
}


def _bake_image_output_helpers():
    """Lazy import — reload order can leave a stale ``save_bake_image_to_disk`` on module import."""
    from . import bake_image_output_helpers

    return bake_image_output_helpers


def _bake_image_float_buffer_mismatch(
    image: bpy.types.Image | None,
    project,
) -> bool:
    if not bake_image_datablock_valid(image):
        return False
    return bool(image.is_float) != _bake_image_output_helpers().bake_image_wants_float_buffer(project)


@dataclass
class LKS_BakedMapResult:
    """One saved bake output on disk."""

    map_id: str
    group_name: str
    filepath: Path
    image: bpy.types.Image


@dataclass
class LKS_BakeGroupMeshes:
    """Resolved high/low mesh targets for one bake group."""

    group_name: str
    low_meshes: list[bpy.types.Object] = field(default_factory=list)
    high_meshes: list[bpy.types.Object] = field(default_factory=list)

    @property
    def is_bakable(self) -> bool:
        return bool(self.low_meshes) and bool(self.high_meshes)


@dataclass
class _RenderBakeState:
    engine: str
    bake_type: str
    use_selected_to_active: bool
    use_cage: bool
    cage_extrusion: float
    max_ray_distance: float
    margin: int
    normal_space: str
    samples: int
    use_pass_direct: bool
    use_pass_indirect: bool
    use_pass_color: bool
    use_pass_diffuse: bool
    use_pass_glossy: bool
    use_pass_transmission: bool
    use_pass_emit: bool
    use_denoising: bool
    max_bounces: int
    sample_clamp_direct: float
    sample_clamp_indirect: float


def _mesh_uv_names(mesh: bpy.types.Mesh) -> list[str]:
    return [layer.name for layer in mesh.uv_layers]


def _resolve_map_resolution(
    project,
    map_entry,
    group_resolution: int,
) -> tuple[int, int]:
    return resolve_bake_texture_dimensions(
        project,
        map_entry,
        group_resolution=group_resolution,
    )


def _resolve_map_samples(project, map_entry) -> int:
    if map_entry is not None and map_entry.samples > 0:
        return map_entry.samples
    return project.default_bake_samples


def get_map_bake_blocker(map_id: str) -> str | None:
    """Human-readable reason when a catalog map cannot be baked yet."""
    return _MAP_BAKE_BLOCKERS.get(map_id)


def map_id_is_bakeable(map_id: str) -> bool:
    spec = get_bake_map_spec(map_id)
    return spec is not None and spec.implemented



def collect_enabled_bake_specs(
    project,
    map_ids: list[str] | None = None,
    *,
    require_enabled: bool = True,
) -> list[LKS_BakeMapSpec]:
    """Enabled + implemented catalog specs from compiled job steps."""
    group_name = getattr(project, 'name', 'BakeProject')
    return [step.spec for step in compile_bake_job_steps(
        project,
        group_name,
        map_ids=map_ids,
        require_enabled=require_enabled,
    )]


def _resolve_input_image(
    project,
    group_name: str,
    map_id: str,
    available: dict[str, LKS_BakedMapResult],
) -> bpy.types.Image | None:
    if map_id in available:
        return available[map_id].image
    spec = get_bake_map_spec(map_id)
    if spec is None:
        return None
    image_name = bake_image_datablock_name(project.name, group_name, spec.output_suffix)
    image = bpy.data.images.get(image_name)
    if image is not None and not bake_image_needs_recreate(image):
        return image
    filepath = bake_output_filepath(project, group_name, spec.output_suffix)
    if filepath.is_file():
        try:
            return bpy.data.images.load(str(filepath), check_existing=True)
        except RuntimeError:
            return None
    return None


def seed_available_results_from_disk(
    project,
    group_name: str,
    map_ids: set[str],
    available: dict[str, LKS_BakedMapResult],
) -> None:
    """Load existing on-disk bake outputs into ``available`` for derive inputs."""
    for map_id in map_ids:
        if map_id in available:
            continue
        spec = get_bake_map_spec(map_id)
        if spec is None:
            continue
        filepath = bake_output_filepath(project, group_name, spec.output_suffix)
        if not filepath.is_file():
            continue
        image = _resolve_input_image(project, group_name, map_id, available)
        if image is None:
            continue
        available[map_id] = LKS_BakedMapResult(
            map_id=map_id,
            group_name=group_name,
            filepath=get_abspath_from_relpath(str(filepath)),
            image=image,
        )


def _report_skipped_map(
    spec: LKS_BakeMapSpec,
    skip_message: str,
    *,
    skipped_map_reports: list[str] | None,
    log_ctx: dict,
) -> None:
    """Record a skipped derive/compute map without failing the bake run."""
    if skipped_map_reports is not None:
        skipped_map_reports.append(f'{spec.map_id}: {skip_message}')
    log_step(
        f'WARNING: skipping {spec.map_id} — {skip_message}',
        **log_ctx,
    )
    bake_progress_report(
        f'Skipped {bake_progress_map_label(spec.map_id)} — {skip_message}…',
    )


def _run_derive_pass(
    spec: LKS_BakeMapSpec,
    *,
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    input_images: dict[str, bpy.types.Image],
    tbn_cache: LKS_TBNRaster | None,
    map_entry=None,
) -> bpy.types.Image:
    return execute_texture_derive(
        spec.map_id,
        spec,
        low_mesh=low_mesh,
        width=width,
        height=height,
        input_images=input_images,
        tbn_cache=tbn_cache,
        map_entry=map_entry,
    )


def _collect_enabled_phase1_specs(project) -> list[LKS_BakeMapSpec]:
    """Legacy alias — all enabled implemented specs (native + emit)."""
    return collect_enabled_bake_specs(project)


def bake_output_filepath(
    project,
    group_name: str,
    output_suffix: str,
) -> Path:
    """``{output_dir}/{group}/{group}_{suffix}.{ext}``."""
    ext = bake_image_file_extension(project)
    root = ensure_export_directory(project.output_dir)
    group_dir = root / group_name
    group_dir.mkdir(parents=True, exist_ok=True)
    return group_dir / f'{group_name}_{output_suffix}.{ext}'


def bake_image_datablock_name(
    project_name: str,
    group_name: str,
    output_suffix: str,
) -> str:
    return f'{project_name}_{group_name}_{output_suffix}'


def bake_image_datablock_valid(image: bpy.types.Image | None) -> bool:
    """True when ``image`` still refers to a live ``bpy.data.images`` entry."""
    if image is None:
        return False
    try:
        return bpy.data.images.get(image.name) is image
    except ReferenceError:
        return False


def bake_image_filepath_on_disk(image: bpy.types.Image) -> str:
    """Absolute path when the image datablock references a file, else empty."""
    if not bake_image_datablock_valid(image):
        return ''
    try:
        raw = (getattr(image, 'filepath_raw', None) or image.filepath or '').strip()
    except ReferenceError:
        return ''
    return bpy.path.abspath(raw) if raw else ''


def bake_image_disk_file_missing(image: bpy.types.Image) -> bool:
    """True when datablock points at a filepath that no longer exists on disk."""
    if not bake_image_datablock_valid(image):
        return True
    disk_path = bake_image_filepath_on_disk(image)
    return bool(disk_path) and not os.path.isfile(disk_path)


def _read_bake_image_from_disk(
    abs_path: str,
    *,
    color_space: str = 'Non-Color',
) -> bpy.types.Image | None:
    """Load a bake file with the intended color space (internal helper)."""
    try:
        image = bpy.data.images.load(abs_path, check_existing=False)
    except RuntimeError:
        return None

    image.colorspace_settings.name = color_space
    try:
        image.reload()
    except RuntimeError:
        bpy.data.images.remove(image)
        return None

    image.update()
    return image


def load_bake_image_pixels_from_disk(
    image: bpy.types.Image,
    filepath: Path | str,
    *,
    color_space: str = 'Non-Color',
) -> bool:
    """Load on-disk bake pixels into an existing image datablock."""
    abs_path = bpy.path.abspath(str(filepath))
    if not os.path.isfile(abs_path):
        return False

    if image.colorspace_settings.name != color_space:
        image.colorspace_settings.name = color_space

    source = _read_bake_image_from_disk(abs_path, color_space=color_space)
    if source is None:
        return False

    try:
        if tuple(source.size) != tuple(image.size):
            image.scale(source.size[0], source.size[1])
        image.pixels[:] = source.pixels[:]
    finally:
        bpy.data.images.remove(source)

    return True


def open_bake_image_from_disk(
    filepath: Path | str,
    *,
    color_space: str = 'Non-Color',
    check_existing: bool = True,
) -> bpy.types.Image | None:
    """Open a baked texture file with catalog-appropriate color space."""
    abs_path = bpy.path.abspath(str(filepath))
    if not os.path.isfile(abs_path):
        return None

    if check_existing:
        for existing in bpy.data.images:
            if not bake_image_datablock_valid(existing):
                continue
            existing_path = bake_image_filepath_on_disk(existing)
            if existing_path != abs_path:
                continue
            if existing.colorspace_settings.name == color_space and existing.has_data:
                return existing
            if existing.colorspace_settings.name != color_space:
                existing.colorspace_settings.name = color_space
            try:
                existing.reload()
            except RuntimeError:
                return load_bake_image_pixels_from_disk(
                    existing,
                    abs_path,
                    color_space=color_space,
                ) and existing
            existing.update()
            return existing

    return _read_bake_image_from_disk(abs_path, color_space=color_space)


def bake_image_needs_recreate(image: bpy.types.Image | None) -> bool:
    """True when an existing bake-target image cannot be used safely."""
    if not bake_image_datablock_valid(image):
        return True
    if bake_image_disk_file_missing(image):
        return True
    try:
        if image.size[0] <= 0 or image.size[1] <= 0:
            return True
        disk_path = bake_image_filepath_on_disk(image)
        if disk_path and not image.has_data:
            color_space = getattr(image.colorspace_settings, 'name', None) or 'Non-Color'
            if not load_bake_image_pixels_from_disk(
                image,
                disk_path,
                color_space=color_space,
            ):
                return True
            if not image.has_data:
                return True
    except ReferenceError:
        return True
    return False


def recreate_bake_image_datablock(
    image_name: str,
    width: int,
    height: int,
    *,
    stale: bpy.types.Image | None = None,
    float_buffer: bool = False,
) -> bpy.types.Image:
    """Remove a stale datablock (if any) and return a fresh in-memory bake target."""
    if stale is not None:
        bpy.data.images.remove(stale, do_unlink=True)
    return bpy.data.images.new(
        image_name,
        width=width,
        height=height,
        alpha=True,
        float_buffer=float_buffer,
    )


def _ensure_bake_image(
    project,
    group_name: str,
    spec: LKS_BakeMapSpec,
    width: int,
    height: int,
) -> tuple[bpy.types.Image, Path]:
    filepath = bake_output_filepath(project, group_name, spec.output_suffix)
    image_name = bake_image_datablock_name(project.name, group_name, spec.output_suffix)
    image = bpy.data.images.get(image_name)
    wants_float = _bake_image_output_helpers().bake_image_wants_float_buffer(project)
    if bake_image_needs_recreate(image) or _bake_image_float_buffer_mismatch(image, project):
        image = recreate_bake_image_datablock(
            image_name,
            width,
            height,
            stale=image,
            float_buffer=wants_float,
        )
    elif image.size[0] != width or image.size[1] != height:
        image = recreate_bake_image_datablock(
            image_name,
            width,
            height,
            stale=image,
            float_buffer=wants_float,
        )

    if image.colorspace_settings.name != spec.color_space:
        image.colorspace_settings.name = spec.color_space
    image.filepath_raw = bpy.path.abspath(str(filepath))
    _bake_image_output_helpers().apply_bake_image_output_settings(image, project)
    return image, filepath


def _find_or_create_image_texture_node(
    material: bpy.types.Material,
    image: bpy.types.Image,
) -> bpy.types.ShaderNodeTexImage:
    material.use_nodes = True
    tree = material.node_tree
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image == image:
            tree.nodes.active = node
            return node

    nodes = tree.nodes
    links = tree.links
    img_node = nodes.new('ShaderNodeTexImage')
    img_node.image = image
    img_node.label = 'Bake Target'
    img_node.location = (-300, 300)

    principled = nodes.get('Principled BSDF')
    if principled is not None:
        links.new(img_node.outputs['Color'], principled.inputs['Base Color'])

    for node in nodes:
        node.select = False
    img_node.select = True
    tree.nodes.active = img_node
    return img_node


def _ensure_low_mesh_bake_material(
    project,
    low_obj: bpy.types.Object,
    image: bpy.types.Image,
    scene: bpy.types.Scene,
) -> bpy.types.Material:
    material = ensure_bake_project_low_material(project, scene)
    if low_obj.type != 'MESH' or low_obj.data is None:
        return material
    mesh = low_obj.data
    if len(mesh.materials) == 0:
        mesh.materials.append(material)
    elif mesh.materials[0] != material:
        mesh.materials[0] = material
    _find_or_create_image_texture_node(material, image)
    return material


def _capture_render_bake_state(scene: bpy.types.Scene) -> _RenderBakeState:
    return _RenderBakeState(
        engine=scene.render.engine,
        bake_type=scene.cycles.bake_type,
        use_selected_to_active=scene.render.bake.use_selected_to_active,
        use_cage=scene.render.bake.use_cage,
        cage_extrusion=scene.render.bake.cage_extrusion,
        max_ray_distance=scene.render.bake.max_ray_distance,
        margin=scene.render.bake.margin,
        normal_space=scene.render.bake.normal_space,
        samples=scene.cycles.samples,
        use_pass_direct=scene.render.bake.use_pass_direct,
        use_pass_indirect=scene.render.bake.use_pass_indirect,
        use_pass_color=scene.render.bake.use_pass_color,
        use_pass_diffuse=scene.render.bake.use_pass_diffuse,
        use_pass_glossy=scene.render.bake.use_pass_glossy,
        use_pass_transmission=scene.render.bake.use_pass_transmission,
        use_pass_emit=scene.render.bake.use_pass_emit,
        use_denoising=scene.cycles.use_denoising,
        max_bounces=scene.cycles.max_bounces,
        sample_clamp_direct=scene.cycles.sample_clamp_direct,
        sample_clamp_indirect=scene.cycles.sample_clamp_indirect,
    )


def _restore_render_bake_state(scene: bpy.types.Scene, state: _RenderBakeState) -> None:
    scene.render.engine = state.engine
    scene.cycles.bake_type = state.bake_type
    scene.render.bake.use_selected_to_active = state.use_selected_to_active
    scene.render.bake.use_cage = state.use_cage
    scene.render.bake.cage_extrusion = state.cage_extrusion
    scene.render.bake.max_ray_distance = state.max_ray_distance
    scene.render.bake.margin = state.margin
    scene.render.bake.normal_space = state.normal_space
    scene.cycles.samples = state.samples
    scene.render.bake.use_pass_direct = state.use_pass_direct
    scene.render.bake.use_pass_indirect = state.use_pass_indirect
    scene.render.bake.use_pass_color = state.use_pass_color
    scene.render.bake.use_pass_diffuse = state.use_pass_diffuse
    scene.render.bake.use_pass_glossy = state.use_pass_glossy
    scene.render.bake.use_pass_transmission = state.use_pass_transmission
    scene.render.bake.use_pass_emit = state.use_pass_emit
    scene.cycles.use_denoising = state.use_denoising
    scene.cycles.max_bounces = state.max_bounces
    scene.cycles.sample_clamp_direct = state.sample_clamp_direct
    scene.cycles.sample_clamp_indirect = state.sample_clamp_indirect


def _resolve_high_mesh_world_bbox(
    context: bpy.types.Context,
    high_meshes: list[bpy.types.Object],
):
    """Evaluated world AABB of all high bake sources."""
    depsgraph = context.evaluated_depsgraph_get()
    corners = combined_world_bbox_corners(high_meshes, depsgraph)
    return bbox_min_max(corners)


def _apply_lighting_cycles_config(scene: bpy.types.Scene, config: LightingBakeConfig) -> None:
    if config.max_bounce_override > 0:
        scene.cycles.max_bounces = config.max_bounce_override
    if config.clamp_direct > 0.0:
        scene.cycles.sample_clamp_direct = config.clamp_direct
    if config.clamp_indirect > 0.0:
        scene.cycles.sample_clamp_indirect = config.clamp_indirect


def _configure_cycles_combined_bake(
    scene: bpy.types.Scene,
    project,
    spec: LKS_BakeMapSpec,
    samples: int,
    margin: int,
    *,
    map_entry=None,
) -> None:
    scene.render.engine = 'CYCLES'
    scene.cycles.bake_type = 'COMBINED'
    scene.cycles.samples = samples
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = project.use_cage
    scene.render.bake.cage_extrusion = project.cage_extrusion
    scene.render.bake.max_ray_distance = project.max_ray_distance
    scene.render.bake.margin = margin
    scene.cycles.use_denoising = True
    pass_filter = resolve_lighting_pass_filter(spec.map_id, spec=spec)
    apply_combined_pass_filter(scene, pass_filter)
    if map_entry is not None:
        _apply_lighting_cycles_config(scene, lighting_config_from_entry(map_entry))


def _configure_cycles_bake(
    scene: bpy.types.Scene,
    project,
    spec: LKS_BakeMapSpec,
    samples: int,
    margin: int,
) -> None:
    scene.render.engine = 'CYCLES'
    scene.cycles.bake_type = spec.cycles_type or 'NORMAL'
    scene.cycles.samples = samples
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = project.use_cage
    scene.render.bake.cage_extrusion = project.cage_extrusion
    scene.render.bake.max_ray_distance = project.max_ray_distance
    scene.render.bake.margin = margin
    if spec.normal_space:
        scene.render.bake.normal_space = spec.normal_space
    if spec.cycles_type == 'AO':
        scene.cycles.use_denoising = True
    # Reset EMIT-only pass flags left by position / shader bakes earlier in the batch.
    scene.render.bake.use_pass_direct = True
    scene.render.bake.use_pass_indirect = True
    scene.render.bake.use_pass_color = True


def _configure_cycles_emit_bake(
    scene: bpy.types.Scene,
    project,
    samples: int,
    margin: int,
) -> None:
    scene.render.engine = 'CYCLES'
    scene.cycles.bake_type = 'EMIT'
    scene.cycles.samples = samples
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = project.use_cage
    scene.render.bake.cage_extrusion = project.cage_extrusion
    scene.render.bake.max_ray_distance = project.max_ray_distance
    scene.render.bake.margin = margin
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True


def _select_highs_active_low(
    context: bpy.types.Context,
    high_meshes: list[bpy.types.Object],
    low_mesh: bpy.types.Object,
) -> None:
    targets = list(high_meshes) + [low_mesh]
    ensure_objects_in_active_view_layer(context, context.scene, targets)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in high_meshes:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    context.view_layer.objects.active = low_mesh


def _save_bake_image(
    image: bpy.types.Image,
    filepath: Path,
    project,
) -> None:
    _bake_image_output_helpers().save_bake_image_to_disk(image, filepath, project)


def _project_object_names(project) -> set[str]:
    """Object names under the bake project root (collections + parented descendants)."""
    from .bake_view_layer_helpers import object_names_in_collection_tree

    return object_names_in_collection_tree(getattr(project, 'root_collection', None))


def _ao_force_hide_project_stragglers(
    project,
    bake_targets: list[bpy.types.Object],
) -> set[str]:
    """Project members that are not direct bake targets (duplicate source highs/lows)."""
    direct_names = {obj.name for obj in bake_targets}
    return _project_object_names(project) - direct_names


_TBN_DERIVE_METHODS = frozenset({
    'normal_object_from_tangent',
    'curvature_from_normal',
    'uv_island_from_mesh',
})


def _ensure_tbn_cache(
    tbn_cache: LKS_TBNRaster | None,
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    *,
    project=None,
    group_name: str | None = None,
    map_id: str | None = None,
) -> LKS_TBNRaster | None:
    """Return cached TBN raster for resolution, rasterizing once on miss."""
    if tbn_cache is not None and tbn_cache.width == width and tbn_cache.height == height:
        log_step(
            'TBN cache hit',
            project=project,
            group_name=group_name,
            map_id=map_id,
        )
        return tbn_cache
    log_ctx = dict(project=project, group_name=group_name, map_id=map_id)
    log_step('TBN cache miss — rasterizing', **log_ctx)
    try:
        with timed_step('TBN raster', **log_ctx):
            return raster_tbn_from_low_mesh(low_mesh, width, height)
    except RuntimeError:
        return None


def _resolve_island_buf_for_map(
    tbn_cache: LKS_TBNRaster | None,
    width: int,
    height: int,
) -> array | None:
    if tbn_cache is not None and tbn_cache.width == width and tbn_cache.height == height:
        from lks_baker.bake_ops.blender.image_adapter import (
            island_id_blender_pixels_flat,
        )

        return island_id_blender_pixels_flat(tbn_cache)
    return None


def _finalize_bake_output_image(
    image: bpy.types.Image,
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    margin_pixels: int,
    tbn_cache: LKS_TBNRaster | None,
    *,
    map_entry=None,
    spec: LKS_BakeMapSpec | None = None,
    project=None,
    group_name: str | None = None,
) -> LKS_TBNRaster | None:
    """Island-aware dilation, optional antialias, optional denoise before disk save."""
    map_id = spec.map_id if spec is not None else None
    map_label = bake_progress_map_label(map_id) if map_id else 'map'
    dilate_config = resolve_dilate_config(map_entry, width, height, project)
    if dilate_config is not None:
        tbn_cache = _ensure_tbn_cache(
            tbn_cache,
            low_mesh,
            width,
            height,
            project=project,
            group_name=group_name,
            map_id=map_id,
        )
    island_buf = _resolve_island_buf_for_map(tbn_cache, width, height)
    use_gpu = bool(getattr(project, 'use_gpu_bake', True)) if project is not None else True
    if dilate_config is not None:
        bake_progress_report(f'Dilating margins ({map_label})…', advance=False)
        with timed_step('dilate', map_id=map_id):
            # TBN island_buf supplies UV ray-hit coverage when baked RGBA lacks a usable
            # alpha mask (tangent normal: alpha=1 + flat blue padding). Without it,
            # binary_mask_from_rgba marks the whole image valid and BFS has no frontier.
            # One dilate pass uses the combined coverage footprint (all islands).
            dilate_bake_image(
                image,
                config=dilate_config,
                island_buf=island_buf,
                use_gpu=use_gpu,
            )
    bake_progress_report(f'Post-processing {map_label}…', advance=False)
    with timed_step('post-process aa/denoise', map_id=map_id):
        apply_map_post_process(
            image,
            map_entry,
            spec=spec,
            island_buf=island_buf,
            width=width,
            height=height,
        )
    return tbn_cache


def _dilate_disk_loaded_parent(
    parent_image: bpy.types.Image,
    parent_id: str,
    project,
    low_mesh: bpy.types.Object,
    tbn_cache: LKS_TBNRaster | None,
    *,
    group_name: str | None = None,
) -> LKS_TBNRaster | None:
    parent_entry = next(
        (e for e in project.map_entries if e.map_id == parent_id),
        None,
    )
    parent_w, parent_h = parent_image.size[0], parent_image.size[1]
    parent_margin = resolve_bake_margin_pixels(
        parent_entry, parent_w, parent_h, project,
    )
    parent_spec = get_bake_map_spec(parent_id)
    return _finalize_bake_output_image(
        parent_image,
        low_mesh,
        parent_w,
        parent_h,
        parent_margin,
        tbn_cache,
        map_entry=parent_entry,
        spec=parent_spec,
        project=project,
        group_name=group_name,
    )


def _bake_type_for_spec(spec: LKS_BakeMapSpec) -> str:
    if uses_cycles_combined_backend(spec):
        return 'COMBINED'
    if spec.blender_backend == 'cycles_emit':
        return 'EMIT'
    return spec.cycles_type or 'NORMAL'


def _uses_emit_bake(spec: LKS_BakeMapSpec) -> bool:
    if uses_cycles_combined_backend(spec):
        return False
    return (
        spec.map_id == 'position'
        or spec.blender_backend == 'cycles_emit'
        or map_id_uses_emit_profile(spec.map_id)
    )


def _run_bake_pass(
    spec: LKS_BakeMapSpec,
    high_meshes: list[bpy.types.Object],
    *,
    material_stack: BakeMaterialOverrideStack | None = None,
    position_bbox: tuple | None = None,
) -> None:
    if spec.map_id == 'position':
        if material_stack is not None and position_bbox is not None:
            apply_bbox_position_emit_profile(
                high_meshes, position_bbox[0], position_bbox[1], material_stack,
            )
        bpy.ops.object.bake(type='EMIT')
        return
    if spec.blender_backend == 'cycles_emit' or map_id_uses_emit_profile(spec.map_id):
        if material_stack is not None:
            apply_emit_profile_for_map(high_meshes, spec.map_id, material_stack)
        bpy.ops.object.bake(type='EMIT')
        return
    bpy.ops.object.bake(type=_bake_type_for_spec(spec))


def run_blender_cycles_bake_step(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    project,
    spec: LKS_BakeMapSpec,
    group_meshes: LKS_BakeGroupMeshes,
    low_mesh: bpy.types.Object,
    image: bpy.types.Image,
    samples: int,
    cycles_margin_pixels: int,
    material_stack: BakeMaterialOverrideStack,
    position_bbox: tuple | None,
    *,
    log_ctx: dict[str, object] | None = None,
) -> None:
    """Run one Cycles selected-to-active bake (canonical Blender builtin path)."""
    log_kwargs = log_ctx or {}
    ao_visibility_snapshot = None
    if spec.map_id == 'ao':
        ensure_bake_targets_visible(group_meshes.high_meshes)
        ao_receiver_names = {obj.name for obj in group_meshes.low_meshes}
        with timed_step('AO visibility isolation', **log_kwargs):
            ao_visibility_snapshot = isolate_scene_to_bake_targets(
                scene,
                group_meshes.low_meshes + group_meshes.high_meshes,
                force_hide_names=_ao_force_hide_project_stragglers(
                    project,
                    group_meshes.low_meshes + group_meshes.high_meshes,
                ),
                ao_receiver_names=ao_receiver_names,
            )
    try:
        _ensure_low_mesh_bake_material(project, low_mesh, image, scene)
        map_entry = next(
            (entry for entry in project.map_entries if entry.map_id == spec.map_id),
            None,
        )
        if _uses_emit_bake(spec):
            _configure_cycles_emit_bake(scene, project, samples, cycles_margin_pixels)
        elif uses_cycles_combined_backend(spec):
            _configure_cycles_combined_bake(
                scene,
                project,
                spec,
                samples,
                cycles_margin_pixels,
                map_entry=map_entry,
            )
        else:
            _configure_cycles_bake(scene, project, spec, samples, cycles_margin_pixels)
        _select_highs_active_low(context, group_meshes.high_meshes, low_mesh)
        with timed_step(f'Cycles bake (samples={samples})', **log_kwargs):
            _run_bake_pass(
                spec,
                group_meshes.high_meshes,
                material_stack=material_stack,
                position_bbox=position_bbox,
            )
    finally:
        material_stack.restore_all()
        if ao_visibility_snapshot is not None:
            with timed_step('AO visibility restore', **log_kwargs):
                restore_scene_object_visibility(ao_visibility_snapshot, scene=scene)


def bake_group_maps(
    context: bpy.types.Context,
    project,
    group_meshes: LKS_BakeGroupMeshes,
    *,
    group_resolution: int | None = None,
    map_ids: list[str] | None = None,
    require_enabled: bool = True,
    reuse_existing_dependencies: bool = False,
    skipped_map_reports: list[str] | None = None,
) -> list[LKS_BakedMapResult]:
    """Run Cycles bakes for one group; returns saved map outputs."""
    if not group_meshes.is_bakable:
        raise RuntimeError(
            f"Bake group '{group_meshes.group_name}' needs at least one high and one low mesh",
        )

    scene = context.scene
    job_steps = compile_bake_job_steps(
        project,
        group_meshes.group_name,
        map_ids=map_ids,
        require_enabled=require_enabled,
        reuse_existing_dependencies=reuse_existing_dependencies,
    )
    if not job_steps:
        label = ', '.join(map_ids) if map_ids else 'implemented maps'
        raise RuntimeError(f'No enabled bake maps to run ({label})')

    resolution = group_resolution or 0
    results: list[LKS_BakedMapResult] = []
    available: dict[str, LKS_BakedMapResult] = {}
    scheduled_step_ids = {step.map_id for step in job_steps}
    if reuse_existing_dependencies and map_ids is not None:
        from ..engine.planner import expand_bake_map_prerequisites

        expanded = expand_bake_map_prerequisites(set(map_ids))
        reuse_ids = expanded - scheduled_step_ids
        if reuse_ids:
            seed_available_results_from_disk(
                project,
                group_meshes.group_name,
                reuse_ids,
                available,
            )
    bake_targets = group_meshes.low_meshes + group_meshes.high_meshes
    render_state = _capture_render_bake_state(scene)
    material_stack = BakeMaterialOverrideStack()
    tbn_cache: LKS_TBNRaster | None = None
    position_bbox = _resolve_high_mesh_world_bbox(context, group_meshes.high_meshes)

    step_labels = ', '.join(step.map_id for step in job_steps)
    log_step(
        f'{len(job_steps)} job steps: {step_labels}',
        project=project,
        group_name=group_meshes.group_name,
    )

    try:
        ensure_bake_targets_visible(bake_targets)
        ensure_objects_in_active_view_layer(context, scene, bake_targets)
        for low_mesh in group_meshes.low_meshes:
            if low_mesh.type != 'MESH' or low_mesh.data is None:
                continue
            if not _mesh_uv_names(low_mesh.data):
                raise RuntimeError(
                    f"Low mesh '{low_mesh.name}' has no UV layer — assign UVs before baking",
                )

            for step in job_steps:
                spec = step.spec
                map_label = bake_progress_map_label(spec.map_id)
                map_entry = next(
                    (e for e in project.map_entries if e.map_id == spec.map_id),
                    None,
                )
                map_width, map_height = _resolve_map_resolution(project, map_entry, resolution)
                samples = _resolve_map_samples(project, map_entry)
                margin_pixels = resolve_bake_margin_pixels(
                    map_entry, map_width, map_height, project,
                )
                cycles_margin_pixels = resolve_cycles_bake_margin_pixels(margin_pixels)
                image, filepath = _ensure_bake_image(
                    project, group_meshes.group_name, spec, map_width, map_height,
                )

                scheduled = set(available.keys())
                available_on_disk = {
                    mid for mid, res in available.items()
                    if res.filepath.is_file()
                }
                backend = select_map_backend(
                    map_entry,
                    spec,
                    project=project,
                    group_name=group_meshes.group_name,
                    scheduled=scheduled,
                    available_on_disk=available_on_disk,
                )
                method_id = (
                    resolve_map_entry_bake_method(map_entry)
                    if map_entry is not None
                    else ''
                )
                log_ctx = dict(
                    project=project,
                    group_name=group_meshes.group_name,
                    map_id=spec.map_id,
                )

                timing_state = BakeMapTimingState(
                    method_id=method_id,
                    backend=(
                        BACKEND_DERIVE if backend == 'derive'
                        else BACKEND_ENGINE if backend == 'engine'
                        else BACKEND_MESH
                    ),
                )

                try:
                    with record_bake_map_timing(
                        map_id=spec.map_id,
                        method_id=method_id,
                        backend=timing_state.backend,
                        width=map_width,
                        height=map_height,
                        project=project,
                        group_name=group_meshes.group_name,
                        internal_prerequisite=step.internal_prerequisite,
                        timing_state=timing_state,
                    ):
                        bake_ok = False
                        if backend == 'derive':
                            bake_progress_report(f'Deriving {map_label}…')
                            input_images: dict[str, bpy.types.Image] = {}
                            if spec.derive_method == 'curvature_from_normal':
                                from lks_baker.shared_utilities.lks_constants import BAKE_CURVATURE_USE_BAKE_ENGINE

                                parent_ids = ('normal_object', 'normal')
                                if BAKE_CURVATURE_USE_BAKE_ENGINE:
                                    parent_ids = ('position', 'normal_object', 'normal')
                                for parent_id in parent_ids:
                                    parent_image = _resolve_input_image(
                                        project, group_meshes.group_name, parent_id, available,
                                    )
                                    if parent_image is None:
                                        continue
                                    if parent_id not in available:
                                        with timed_step(
                                            f'dilate parent {parent_id}',
                                            **log_ctx,
                                        ):
                                            tbn_cache = _dilate_disk_loaded_parent(
                                                parent_image,
                                                parent_id,
                                                project,
                                                low_mesh,
                                                tbn_cache,
                                                group_name=group_meshes.group_name,
                                            )
                                    input_images[parent_id] = parent_image
                                parents_ready = bool(input_images)
                            else:
                                parents = spec.derive_from or ()
                                parents_ready = False
                                for parent_id in parents:
                                    parent_image = _resolve_input_image(
                                        project, group_meshes.group_name, parent_id, available,
                                    )
                                    if parent_image is None:
                                        break
                                    if parent_id not in available:
                                        with timed_step(
                                            f'dilate parent {parent_id}',
                                            **log_ctx,
                                        ):
                                            tbn_cache = _dilate_disk_loaded_parent(
                                                parent_image,
                                                parent_id,
                                                project,
                                                low_mesh,
                                                tbn_cache,
                                                group_name=group_meshes.group_name,
                                            )
                                    input_images[parent_id] = parent_image
                                else:
                                    parents_ready = True
                            if not parents_ready:
                                missing = (
                                    ', '.join(parent_ids)
                                    if spec.derive_method == 'curvature_from_normal'
                                    else ', '.join(spec.derive_from or ())
                                )
                                raise TextureDeriveSkip(
                                    f"{spec.map_id}: missing derive inputs ({missing or 'none'})",
                                )
                            try:
                                if spec.derive_method in _TBN_DERIVE_METHODS:
                                    tbn_cache = _ensure_tbn_cache(
                                        tbn_cache,
                                        low_mesh,
                                        map_width,
                                        map_height,
                                        **log_ctx,
                                    )
                                with timed_step('bake engine (derive)', **log_ctx):
                                    derived = _run_derive_pass(
                                        spec,
                                        low_mesh=low_mesh,
                                        width=map_width,
                                        height=map_height,
                                        input_images=input_images,
                                        tbn_cache=tbn_cache,
                                        map_entry=map_entry,
                                    )
                                if derived.size[0] != map_width or derived.size[1] != map_height:
                                    raise RuntimeError('derived image size mismatch')
                                image.pixels.foreach_set(derived.pixels[:])
                                image.update()
                                bake_ok = True
                            except RuntimeError as exc:
                                pref = resolve_map_backend_preference(map_entry)
                                if pref == 'DERIVE_ONLY':
                                    raise RuntimeError(
                                        f"Derive-only bake failed for '{spec.map_id}' — {exc}",
                                    ) from exc
                                log_step(
                                    'derive failed — falling back to mesh bake',
                                    **log_ctx,
                                )
                                timing_state.backend = BACKEND_MESH

                        elif backend == 'engine':
                            bake_progress_report(f'Computing {map_label}…')
                            from lks_baker.bake_ops.blender.engine_bridge import (
                                run_engine_method_to_bpy_image,
                            )
                            from lks_baker.bake_ops.static_utilities.bake_method_catalog import (
                                engine_method_prerequisites,
                            )

                            parent_ids = engine_method_prerequisites(spec.map_id, method_id)
                            input_images = {}
                            parents_ready = True
                            for parent_id in parent_ids:
                                parent_image = _resolve_input_image(
                                    project, group_meshes.group_name, parent_id, available,
                                )
                                if parent_image is None:
                                    parents_ready = False
                                    break
                                if parent_id not in available:
                                    with timed_step(
                                        f'dilate parent {parent_id}',
                                        **log_ctx,
                                    ):
                                        tbn_cache = _dilate_disk_loaded_parent(
                                            parent_image,
                                            parent_id,
                                            project,
                                            low_mesh,
                                            tbn_cache,
                                            group_name=group_meshes.group_name,
                                        )
                                input_images[parent_id] = parent_image
                            if not parents_ready:
                                raise RuntimeError(
                                    f"Engine bake for '{spec.map_id}' / '{method_id}' missing prerequisites: "
                                    f"{', '.join(parent_ids)}",
                                )
                            tbn_cache = _ensure_tbn_cache(
                                tbn_cache,
                                low_mesh,
                                map_width,
                                map_height,
                                **log_ctx,
                            )
                            high_mesh_obj = group_meshes.high_meshes[0] if group_meshes.high_meshes else None
                            with timed_step('bake engine (compute)', **log_ctx):
                                derived = run_engine_method_to_bpy_image(
                                    spec.map_id,
                                    method_id,
                                    low_mesh=low_mesh,
                                    width=map_width,
                                    height=map_height,
                                    input_images=input_images,
                                    tbn_cache=tbn_cache,
                                    map_entry=map_entry,
                                    high_mesh=high_mesh_obj,
                                    project=project,
                                )
                            if derived.size[0] != map_width or derived.size[1] != map_height:
                                raise RuntimeError('engine image size mismatch')
                            image.pixels.foreach_set(derived.pixels[:])
                            image.update()
                            bake_ok = True

                        if not bake_ok:
                            bake_progress_report(f'Baking {map_label} (Cycles)…')
                            from lks_baker.bake_ops.engine.bake_map import BakeMapInput
                            from lks_baker.bake_ops.engine.blender_bake import (
                                BLENDER_BUILTIN_DEVICE,
                                BLENDER_BUILTIN_METHOD_ID,
                                BlenderBakeExecutionContext,
                                is_blender_builtin_map_id,
                            )
                            from lks_baker.bake_ops.engine.orchestrator import BakeEngine, BakeRequest

                            if not is_blender_builtin_map_id(spec.map_id):
                                raise RuntimeError(
                                    f"No blender builtin bake-engine method for '{spec.map_id}'",
                                )
                            selected_method = (
                                resolve_map_entry_bake_method(map_entry)
                                if map_entry is not None
                                else BLENDER_BUILTIN_METHOD_ID
                            )
                            timing_state.method_id = selected_method
                            if selected_method != BLENDER_BUILTIN_METHOD_ID:
                                raise RuntimeError(
                                    f"Mesh bake for '{spec.map_id}' requires method "
                                    f"{BLENDER_BUILTIN_METHOD_ID!r}, got {selected_method!r}",
                                )
                            blender_ctx = BlenderBakeExecutionContext(
                                context=context,
                                scene=scene,
                                project=project,
                                spec=spec,
                                group_meshes=group_meshes,
                                low_mesh=low_mesh,
                                image=image,
                                filepath=filepath,
                                samples=samples,
                                cycles_margin_pixels=cycles_margin_pixels,
                                material_stack=material_stack,
                                position_bbox=position_bbox,
                                log_ctx=log_ctx,
                            )
                            dummy_valid = np.ones((map_height, map_width), dtype=bool)
                            with timed_step('bake engine (blender)', **log_ctx):
                                BakeEngine().bake(
                                    BakeRequest(
                                        map_type=resolve_engine_map_type(spec.map_id),
                                        method_id=BLENDER_BUILTIN_METHOD_ID,
                                        device=BLENDER_BUILTIN_DEVICE,
                                        inputs=BakeMapInput(
                                            valid=dummy_valid,
                                            island_id=np.zeros((map_height, map_width), dtype=np.int32),
                                            image_size=map_width,
                                            extra={"blender_context": blender_ctx},
                                        ),
                                    ),
                                )

                        bake_progress_report(f'Post-processing {map_label}…')
                        with timed_step('post-process', **log_ctx):
                            tbn_cache = _finalize_bake_output_image(
                                image,
                                low_mesh,
                                map_width,
                                map_height,
                                margin_pixels,
                                tbn_cache,
                                map_entry=map_entry,
                                spec=spec,
                                project=project,
                                group_name=group_meshes.group_name,
                            )
                        bake_progress_report(f'Saving {map_label}…')
                        with timed_step('save to disk', **log_ctx):
                            _save_bake_image(image, filepath, project)
                            log_step(f'wrote {filepath}', **log_ctx)
                        result = LKS_BakedMapResult(
                            map_id=spec.map_id,
                            group_name=group_meshes.group_name,
                            filepath=get_abspath_from_relpath(str(filepath)),
                            image=image,
                        )
                        available[spec.map_id] = result
                        if not step.internal_prerequisite:
                            results.append(result)
                except TextureDeriveSkip as exc:
                    _report_skipped_map(
                        spec,
                        str(exc),
                        skipped_map_reports=skipped_map_reports,
                        log_ctx=log_ctx,
                    )
                    continue
    finally:
        material_stack.restore_all()
        _restore_render_bake_state(scene, render_state)

    return results


def bake_group_cycles(
    context: bpy.types.Context,
    project,
    group_meshes: LKS_BakeGroupMeshes,
    *,
    group_resolution: int | None = None,
) -> list[LKS_BakedMapResult]:
    """Legacy alias for project-wide enabled implemented maps."""
    return bake_group_maps(
        context,
        project,
        group_meshes,
        group_resolution=group_resolution,
    )


def _resolve_bake_group_resolution_override(project, group_name: str) -> int:
    """Return group-level square resolution override (0 = inherit project Texture Outputs)."""
    for group in project.bake_groups:
        if group.name == group_name:
            return group.resolution_override or 0
    return 0


def execute_bake_groups(
    context: bpy.types.Context,
    project,
    group_meshes_list: list[LKS_BakeGroupMeshes],
    *,
    map_ids: list[str] | None = None,
    require_enabled: bool = True,
    reuse_existing_dependencies: bool = False,
) -> list[LKS_BakedMapResult]:
    """Bake all provided groups; raises when nothing is baked."""
    all_results: list[LKS_BakedMapResult] = []
    errors: list[str] = []
    skipped_reports: list[str] = []
    map_filter = ', '.join(map_ids) if map_ids else 'all enabled'

    log_step(
        f'execute {len(group_meshes_list)} group(s), maps={map_filter}',
        project=project,
    )

    for group_meshes in group_meshes_list:
        if not group_meshes.is_bakable:
            msg = f"Skipped '{group_meshes.group_name}' — missing high or low meshes"
            errors.append(msg)
            log_step(msg, project=project, group_name=group_meshes.group_name)
            continue
        group_resolution = _resolve_bake_group_resolution_override(
            project,
            group_meshes.group_name,
        )
        try:
            with timed_step(
                f'bake group {group_meshes.group_name}',
                project=project,
                group_name=group_meshes.group_name,
            ):
                group_results = bake_group_maps(
                    context,
                    project,
                    group_meshes,
                    group_resolution=group_resolution or None,
                    map_ids=map_ids,
                    require_enabled=require_enabled,
                    reuse_existing_dependencies=reuse_existing_dependencies,
                    skipped_map_reports=skipped_reports,
                )
                all_results.extend(group_results)
                log_step(
                    f'baked {len(group_results)} map(s)',
                    project=project,
                    group_name=group_meshes.group_name,
                )
        except TextureDeriveSkip as exc:
            skip_message = str(exc)
            skipped_reports.append(skip_message)
            log_step(
                f'WARNING: derive skip — {skip_message}',
                project=project,
                group_name=group_meshes.group_name,
            )
        except RuntimeError as exc:
            errors.append(str(exc))
            log_step(f'failed: {exc}', project=project, group_name=group_meshes.group_name)

    if not all_results:
        if skipped_reports and not errors:
            skip_detail = (
                skipped_reports[0]
                if len(skipped_reports) == 1
                else '; '.join(skipped_reports)
            )
            log_step(
                f'WARNING: no maps baked — skipped: {skip_detail}',
                project=project,
            )
            return all_results
        detail = '; '.join(errors) if errors else 'no bake groups with high and low geometry'
        if skipped_reports:
            detail = f"{detail}; skipped: {'; '.join(skipped_reports)}"
        raise RuntimeError(f'Bake produced no images — {detail}')
    log_step(f'finished — {len(all_results)} map result(s)', project=project)
    return all_results

"""Wire baked image outputs into the baker-managed low material (Principled BSDF)."""

from __future__ import annotations

import bpy

from .bake_blender_helpers import (
    LKS_BakedMapResult,
    bake_image_datablock_valid,
    bake_image_needs_recreate,
    bake_output_filepath,
    open_bake_image_from_disk,
)
from .bake_map_catalog import BAKE_MAP_CATALOG, get_bake_map_spec
from .bake_low_material_helpers import (
    ensure_bake_project_low_material,
    uniquify_and_apply_bake_low_material,
)
from .bake_node_layout_helpers import layout_bake_material_nodes

_PREVIEW_DEFAULT_BASE_COLOR = (1.0, 1.0, 1.0, 1.0)
_PREVIEW_DEFAULT_ROUGHNESS = 0.2
_PREVIEW_DEFAULT_METALLIC = 0.0
_PREVIEW_DEFAULT_EMISSION_COLOR = (0.0, 0.0, 0.0, 1.0)
_PREVIEW_DEFAULT_EMISSION_STRENGTH = 0.0
_PREVIEW_NO_PBR_METALLIC = 1.0
_COMPOSITE_EMISSION_STRENGTH = 1.0

# Post-bake composite: PBR Principled inputs; Base Color resolved separately (albedo → ao → white).
_COMPOSITE_MAP_WIRING: dict[str, str] = {
    'normal': 'normal_tangent',
    'roughness': 'roughness',
    'metalness': 'metallic',
    'emissive': 'emission',
}
_COMPOSITE_BASE_COLOR_PRIORITY: tuple[str, ...] = ('albedo', 'ao')

# Solo eyeball: every catalog map bypasses Material Output via a dedicated Principled BSDF
# (texture → Emission, black base, max roughness, no specular) for Material Preview / EEVEE.
# Only composite ``_COMPOSITE_MAP_WIRING`` may wire tangent ``normal`` to Principled Normal.
_SOLO_PREVIEW_WIRING_MODE = 'principled'
_SOLO_PREVIEW_MAP_WIRING: dict[str, str] = {
    map_id: _SOLO_PREVIEW_WIRING_MODE for map_id in BAKE_MAP_CATALOG
}

_PREVIEW_PRINCIPLED_INPUTS = ('Base Color', 'Normal', 'Roughness', 'Metallic')
_SOLO_PREVIEW_LABEL_PREFIX = 'Solo Preview '
_SOLO_PREVIEW_BLACK_BASE = (0.0, 0.0, 0.0, 1.0)
_SOLO_PREVIEW_MAX_ROUGHNESS = 1.0
_SOLO_PREVIEW_EMISSION_STRENGTH = 1.0
_SOLO_PREVIEW_NO_SPECULAR = 0.0

_PROJECT_BAKED_RESULTS_CACHE: dict[str, list[LKS_BakedMapResult]] = {}


def _project_cache_key(scene: bpy.types.Scene, project) -> str:
    return f'{scene.name}::{project.name}'


def _sanitize_baked_result(result: LKS_BakedMapResult) -> LKS_BakedMapResult:
    """Drop stale ``Image`` pointers so restore paths can reload from disk."""
    if result.image is not None and not bake_image_datablock_valid(result.image):
        return LKS_BakedMapResult(
            map_id=result.map_id,
            group_name=result.group_name,
            filepath=result.filepath,
            image=None,
        )
    return result


def merge_project_baked_results_cache(
    scene: bpy.types.Scene,
    project,
    baked_results: list[LKS_BakedMapResult],
    *,
    replace: bool = False,
) -> None:
    """Merge bake outputs into the per-project composite restore cache."""
    if not baked_results:
        return
    key = _project_cache_key(scene, project)
    if replace:
        by_map_id: dict[str, LKS_BakedMapResult] = {}
    else:
        by_map_id = {
            result.map_id: result
            for result in _PROJECT_BAKED_RESULTS_CACHE.get(key, [])
        }
    for result in baked_results:
        by_map_id[result.map_id] = _sanitize_baked_result(result)
    _PROJECT_BAKED_RESULTS_CACHE[key] = list(by_map_id.values())


def merge_cached_baked_results_with_disk(
    cached: list[LKS_BakedMapResult],
    disk: list[LKS_BakedMapResult],
) -> list[LKS_BakedMapResult]:
    """Overlay on-disk filepaths onto cached map ids; ignore disk-only stale outputs."""
    if not cached:
        return list(disk)
    if not disk:
        return list(cached)

    disk_by_map_id = {result.map_id: result for result in disk}
    merged: list[LKS_BakedMapResult] = []
    for result in cached:
        disk_result = disk_by_map_id.get(result.map_id)
        if disk_result is None:
            merged.append(result)
            continue
        merged.append(
            LKS_BakedMapResult(
                map_id=result.map_id,
                group_name=result.group_name,
                filepath=disk_result.filepath,
                image=(
                    result.image
                    if result.image is not None and not bake_image_needs_recreate(result.image)
                    else None
                ),
            ),
        )
    return merged


def get_cached_project_baked_results(
    scene: bpy.types.Scene,
    project,
) -> list[LKS_BakedMapResult]:
    """Return cached bake results merged with on-disk outputs for composite restore."""
    key = _project_cache_key(scene, project)
    cached = [
        _sanitize_baked_result(result)
        for result in _PROJECT_BAKED_RESULTS_CACHE.get(key, [])
    ]
    if cached:
        _PROJECT_BAKED_RESULTS_CACHE[key] = cached
    disk = collect_baked_results_from_disk(project)
    return merge_cached_baked_results_with_disk(cached, disk)


def collect_baked_results_from_disk(project) -> list[LKS_BakedMapResult]:
    """Build composite restore entries from existing project texture-set files."""
    group_name = project.name
    results: list[LKS_BakedMapResult] = []
    for map_id, spec in BAKE_MAP_CATALOG.items():
        filepath = bake_output_filepath(project, group_name, spec.output_suffix)
        if not filepath.is_file():
            continue
        results.append(
            LKS_BakedMapResult(
                map_id=map_id,
                group_name=group_name,
                filepath=filepath,
                image=None,
            ),
        )
    return results


def bake_map_image_exists_on_disk(project, map_id: str) -> bool:
    """True when the project texture-set file for ``map_id`` exists on disk."""
    spec = get_bake_map_spec(map_id)
    if spec is None:
        return False
    return bake_output_filepath(project, project.name, spec.output_suffix).is_file()


def _get_or_create_principled(material: bpy.types.Material) -> bpy.types.ShaderNodeBsdfPrincipled:
    material.use_nodes = True
    node = material.node_tree.nodes.get('Principled BSDF')
    if node is None:
        node = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
    return node


def _get_or_create_normal_map_node(
    tree: bpy.types.NodeTree,
    *,
    label: str,
) -> bpy.types.ShaderNodeNormalMap:
    for node in tree.nodes:
        if node.type == 'NORMAL_MAP' and node.label == label:
            return node
    node = tree.nodes.new('ShaderNodeNormalMap')
    node.label = label
    return node


def _resolve_preview_image(result: LKS_BakedMapResult) -> bpy.types.Image | None:
    """Return a usable image for preview wiring; never raises on missing disk files."""
    spec = get_bake_map_spec(result.map_id)
    color_space = spec.color_space if spec is not None else 'Non-Color'

    image = result.image
    if (
        image is not None
        and bake_image_datablock_valid(image)
        and not bake_image_needs_recreate(image)
        and image.has_data
    ):
        if image.colorspace_settings.name != color_space:
            image.colorspace_settings.name = color_space
        return image

    if not result.filepath.is_file():
        return None

    return open_bake_image_from_disk(
        result.filepath,
        color_space=color_space,
        check_existing=True,
    )


def _disconnect_input_links(
    tree: bpy.types.NodeTree,
    socket: bpy.types.NodeSocket,
) -> None:
    for link in list(socket.links):
        tree.links.remove(link)


def _get_principled_emission_color_socket(
    principled: bpy.types.ShaderNodeBsdfPrincipled,
) -> bpy.types.NodeSocket | None:
    emission_color = principled.inputs.get('Emission Color')
    if emission_color is not None:
        return emission_color
    return principled.inputs.get('Emission')


def _reset_principled_preview_defaults(
    principled: bpy.types.ShaderNodeBsdfPrincipled,
) -> None:
    principled.inputs['Base Color'].default_value = _PREVIEW_DEFAULT_BASE_COLOR
    principled.inputs['Roughness'].default_value = _PREVIEW_DEFAULT_ROUGHNESS
    principled.inputs['Metallic'].default_value = _PREVIEW_DEFAULT_METALLIC
    emission_color = _get_principled_emission_color_socket(principled)
    if emission_color is not None:
        emission_color.default_value = _PREVIEW_DEFAULT_EMISSION_COLOR
    emission_strength = principled.inputs.get('Emission Strength')
    if emission_strength is not None:
        emission_strength.default_value = _PREVIEW_DEFAULT_EMISSION_STRENGTH


def _is_pbr_baked_result(result: LKS_BakedMapResult) -> bool:
    spec = get_bake_map_spec(result.map_id)
    return spec is not None and spec.category == 'pbr'


def _has_baked_pbr_maps(baked_results: list[LKS_BakedMapResult]) -> bool:
    return any(_is_pbr_baked_result(result) for result in baked_results)


def _clear_preview_material_wiring(
    tree: bpy.types.NodeTree,
    principled: bpy.types.ShaderNodeBsdfPrincipled,
) -> None:
    """Disconnect bake/preview links and restore fixed Principled defaults."""
    for input_name in _PREVIEW_PRINCIPLED_INPUTS:
        socket = principled.inputs.get(input_name)
        if socket is not None:
            _disconnect_input_links(tree, socket)
    emission_color = _get_principled_emission_color_socket(principled)
    if emission_color is not None:
        _disconnect_input_links(tree, emission_color)
    _reset_principled_preview_defaults(principled)


def _get_or_create_material_output(
    tree: bpy.types.NodeTree,
) -> bpy.types.ShaderNodeOutputMaterial:
    output = tree.nodes.get('Material Output')
    if output is None:
        output = tree.nodes.new('ShaderNodeOutputMaterial')
    return output


def _disconnect_output_surface(
    tree: bpy.types.NodeTree,
    output: bpy.types.ShaderNodeOutputMaterial,
) -> None:
    socket = output.inputs.get('Surface')
    if socket is not None:
        _disconnect_input_links(tree, socket)


def _connect_principled_to_output(
    tree: bpy.types.NodeTree,
    principled: bpy.types.ShaderNodeBsdfPrincipled,
    output: bpy.types.ShaderNodeOutputMaterial,
) -> None:
    _disconnect_output_surface(tree, output)
    tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])


def _remove_stale_solo_preview_nodes(tree: bpy.types.NodeTree) -> None:
    remove = [
        node
        for node in tree.nodes
        if (node.label or '').startswith(_SOLO_PREVIEW_LABEL_PREFIX)
    ]
    for node in remove:
        tree.nodes.remove(node)


def _set_solo_principled_no_specular(
    principled: bpy.types.ShaderNodeBsdfPrincipled,
) -> None:
    level_socket = principled.inputs.get('Specular IOR Level')
    if level_socket is not None:
        level_socket.default_value = _SOLO_PREVIEW_NO_SPECULAR
        return
    specular_socket = principled.inputs.get('Specular')
    if specular_socket is not None:
        specular_socket.default_value = _SOLO_PREVIEW_NO_SPECULAR


def _wire_solo_principled_preview(
    tree: bpy.types.NodeTree,
    output: bpy.types.ShaderNodeOutputMaterial,
    image: bpy.types.Image,
    map_id: str,
) -> bool:
    """Bypass Material Output through a solo Principled BSDF (emission-only flat view)."""
    tex = tree.nodes.new('ShaderNodeTexImage')
    try:
        tex.image = image
    except RuntimeError:
        tree.nodes.remove(tex)
        return False
    tex.label = f'{_SOLO_PREVIEW_LABEL_PREFIX}{map_id}'

    solo_principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
    solo_principled.label = f'{_SOLO_PREVIEW_LABEL_PREFIX}Principled'
    solo_principled.inputs['Base Color'].default_value = _SOLO_PREVIEW_BLACK_BASE
    solo_principled.inputs['Roughness'].default_value = _SOLO_PREVIEW_MAX_ROUGHNESS
    _set_solo_principled_no_specular(solo_principled)

    emission_color = solo_principled.inputs.get('Emission Color')
    if emission_color is None:
        emission_color = solo_principled.inputs['Emission']
    emission_strength = solo_principled.inputs.get('Emission Strength')
    if emission_strength is not None:
        emission_strength.default_value = _SOLO_PREVIEW_EMISSION_STRENGTH

    tree.links.new(tex.outputs['Color'], emission_color)
    tree.links.new(solo_principled.outputs['BSDF'], output.inputs['Surface'])
    return True


def _remove_stale_preview_nodes(tree: bpy.types.NodeTree) -> None:
    """Drop prior bake-target and preview nodes before re-wiring."""
    remove: list[bpy.types.Node] = []
    for node in tree.nodes:
        label = node.label or ''
        if (
            label == 'Bake Target'
            or label.startswith('Preview ')
            or label.startswith(_SOLO_PREVIEW_LABEL_PREFIX)
        ):
            remove.append(node)
        elif node.type == 'NORMAL_MAP' and label == 'Preview Normal Map':
            remove.append(node)
    for node in remove:
        tree.nodes.remove(node)


def resolve_composite_base_color_map_id(
    available_map_ids: set[str] | frozenset[str],
) -> str | None:
    """Pick composite Base Color source: albedo when present, else ao."""
    for map_id in _COMPOSITE_BASE_COLOR_PRIORITY:
        if map_id in available_map_ids:
            return map_id
    return None


def _apply_composite_base_color(
    tree: bpy.types.NodeTree,
    principled: bpy.types.ShaderNodeBsdfPrincipled,
    baked_results: list[LKS_BakedMapResult],
) -> None:
    """Wire albedo → Base Color when baked, else ao, else leave white default."""
    by_map_id: dict[str, LKS_BakedMapResult] = {}
    for result in baked_results:
        by_map_id.setdefault(result.map_id, result)

    base_color_map_id = resolve_composite_base_color_map_id(set(by_map_id))
    if base_color_map_id is None:
        return

    result = by_map_id.get(base_color_map_id)
    if result is None:
        return
    image = _resolve_preview_image(result)
    if image is None:
        return
    _connect_image_to_input(tree, principled, image, 'base_color')


def _connect_image_to_input(
    tree: bpy.types.NodeTree,
    principled: bpy.types.ShaderNodeBsdfPrincipled,
    image: bpy.types.Image,
    wiring: str,
) -> None:
    nodes = tree.nodes
    links = tree.links

    tex = nodes.new('ShaderNodeTexImage')
    try:
        tex.image = image
    except RuntimeError:
        nodes.remove(tex)
        return
    tex.label = f'Preview {image.name}'

    if wiring == 'base_color':
        links.new(tex.outputs['Color'], principled.inputs['Base Color'])
    elif wiring == 'roughness':
        links.new(tex.outputs['Color'], principled.inputs['Roughness'])
    elif wiring == 'metallic':
        links.new(tex.outputs['Color'], principled.inputs['Metallic'])
    elif wiring == 'normal_tangent':
        normal_node = _get_or_create_normal_map_node(
            tree,
            label='Preview Normal Map',
        )
        links.new(tex.outputs['Color'], normal_node.inputs['Color'])
        links.new(normal_node.outputs['Normal'], principled.inputs['Normal'])
    elif wiring == 'emission':
        emission_color = _get_principled_emission_color_socket(principled)
        if emission_color is None:
            nodes.remove(tex)
            return
        links.new(tex.outputs['Color'], emission_color)
        emission_strength = principled.inputs.get('Emission Strength')
        if emission_strength is not None:
            emission_strength.default_value = _COMPOSITE_EMISSION_STRENGTH


def apply_baked_maps_to_low_material(
    project,
    baked_results: list[LKS_BakedMapResult],
    low_roots: list[bpy.types.Object],
    scene: bpy.types.Scene | None = None,
) -> int:
    """
    Ensure project low material exists on ``low_roots``, then wire baked images.

    Does not replace ``uniquify_and_apply_bake_low_material`` — composes with it.
    Returns mesh count that received the material.
    """
    if not baked_results or not low_roots:
        return 0

    mesh_count = uniquify_and_apply_bake_low_material(project, low_roots, scene)
    material = ensure_bake_project_low_material(project, scene)
    tree = material.node_tree
    principled = _get_or_create_principled(material)
    output = _get_or_create_material_output(tree)
    _remove_stale_preview_nodes(tree)
    _connect_principled_to_output(tree, principled, output)
    _clear_preview_material_wiring(tree, principled)

    seen_maps: set[str] = set()
    for result in baked_results:
        if result.map_id in seen_maps:
            continue
        wiring = _COMPOSITE_MAP_WIRING.get(result.map_id)
        if wiring is None:
            continue
        seen_maps.add(result.map_id)
        image = _resolve_preview_image(result)
        if image is None:
            continue
        _connect_image_to_input(tree, principled, image, wiring)

    _apply_composite_base_color(tree, principled, baked_results)

    if not _has_baked_pbr_maps(baked_results):
        principled.inputs['Metallic'].default_value = _PREVIEW_NO_PBR_METALLIC

    layout_bake_material_nodes(tree)
    return mesh_count


def nudge_viewport_material_shading(context: bpy.types.Context) -> None:
    """Switch active 3D View from SOLID to MATERIAL so baked textures are visible."""
    area = context.area
    if area is None or area.type != 'VIEW_3D':
        return
    for space in area.spaces:
        if space.type != 'VIEW_3D':
            continue
        shading = space.shading
        if shading.type == 'SOLID':
            shading.type = 'MATERIAL'


def apply_solo_map_preview(
    project,
    map_id: str,
    low_roots: list[bpy.types.Object],
    scene: bpy.types.Scene,
) -> bool:
    """
    Bypass Material Output to a solo baked map texture.

    Preserves Principled BSDF composite links for restore on clear.
    """
    wiring = _SOLO_PREVIEW_MAP_WIRING.get(map_id)
    if wiring != _SOLO_PREVIEW_WIRING_MODE:
        return False

    spec = get_bake_map_spec(map_id)
    if spec is None:
        return False

    filepath = bake_output_filepath(project, project.name, spec.output_suffix)
    if not filepath.is_file():
        return False

    result = LKS_BakedMapResult(
        map_id=map_id,
        group_name=project.name,
        filepath=filepath,
        image=None,
    )
    image = _resolve_preview_image(result)
    if image is None or not low_roots:
        return False

    uniquify_and_apply_bake_low_material(project, low_roots, scene)
    material = ensure_bake_project_low_material(project, scene)
    tree = material.node_tree
    principled = _get_or_create_principled(material)
    output = _get_or_create_material_output(tree)

    _remove_stale_solo_preview_nodes(tree)
    _disconnect_output_surface(tree, output)

    if not _wire_solo_principled_preview(tree, output, image, map_id):
        _connect_principled_to_output(tree, principled, output)
        return False
    layout_bake_material_nodes(tree)
    return True


def _restore_low_material_composite(
    project,
    low_roots: list[bpy.types.Object],
    scene: bpy.types.Scene,
    *,
    baked_results: list[LKS_BakedMapResult] | None = None,
) -> int:
    """Wire composite preview from cache or disk; ignores ``lks_preview_map_id``."""
    if not low_roots:
        return 0
    results = (
        baked_results
        if baked_results is not None
        else get_cached_project_baked_results(scene, project)
    )
    if not results:
        return uniquify_and_apply_bake_low_material(project, low_roots, scene)
    return apply_baked_maps_to_low_material(project, results, low_roots, scene)


def reapply_bake_preview_material(
    context: bpy.types.Context,
    project,
    low_roots: list[bpy.types.Object],
) -> int:
    """
    Fully reconstruct the project low preview material from cached or on-disk bakes.

    When ``lks_preview_map_id`` is set, restores solo preview for that map; otherwise
    wires the full Principled composite.
    """
    mesh_count = refresh_project_low_material_composite(project, low_roots, context.scene)
    nudge_viewport_material_shading(context)
    return mesh_count


def refresh_project_low_material_composite(
    project,
    low_roots: list[bpy.types.Object],
    scene: bpy.types.Scene,
    *,
    baked_results: list[LKS_BakedMapResult] | None = None,
) -> int:
    """Restore low-material wiring from cache or on-disk bakes (composite or solo preview)."""
    if not low_roots:
        return 0

    if baked_results is not None:
        return _restore_low_material_composite(
            project,
            low_roots,
            scene,
            baked_results=baked_results,
        )

    preview_map_id = (getattr(project, 'lks_preview_map_id', None) or '').strip()
    if preview_map_id:
        if apply_solo_map_preview(project, preview_map_id, low_roots, scene):
            return uniquify_and_apply_bake_low_material(project, low_roots, scene)

    return _restore_low_material_composite(project, low_roots, scene)


def clear_solo_map_preview(
    project,
    low_roots: list[bpy.types.Object],
    scene: bpy.types.Scene,
    *,
    cached_results: list[LKS_BakedMapResult] | None = None,
) -> None:
    """Remove solo output bypass and restore post-bake composite wiring."""
    material = ensure_bake_project_low_material(project, scene)
    tree = material.node_tree
    principled = _get_or_create_principled(material)
    output = _get_or_create_material_output(tree)

    _remove_stale_solo_preview_nodes(tree)
    _connect_principled_to_output(tree, principled, output)

    if not low_roots:
        return
    _restore_low_material_composite(
        project,
        low_roots,
        scene,
        baked_results=cached_results,
    )


def enable_solo_map_preview(
    context: bpy.types.Context,
    project,
    map_id: str,
    low_roots: list[bpy.types.Object],
) -> bool:
    """
    Activate solo map preview (non-toggle).

    Clears any prior solo bypass, wires ``map_id``, and sets ``lks_preview_map_id``.
    """
    scene = context.scene
    current = (getattr(project, 'lks_preview_map_id', None) or '').strip()

    if current and current != map_id:
        project.lks_preview_map_id = ''
        clear_solo_map_preview(project, low_roots, scene)

    if not apply_solo_map_preview(project, map_id, low_roots, scene):
        project.lks_preview_map_id = ''
        return False

    project.lks_preview_map_id = map_id
    nudge_viewport_material_shading(context)
    return True


def toggle_solo_map_preview(
    context: bpy.types.Context,
    project,
    map_id: str,
    low_roots: list[bpy.types.Object],
) -> str:
    """
    Radio-toggle solo map preview for a project.

    Returns the new ``lks_preview_map_id`` (empty when cleared).
    """
    scene = context.scene
    current = (getattr(project, 'lks_preview_map_id', None) or '').strip()

    if current == map_id:
        project.lks_preview_map_id = ''
        clear_solo_map_preview(project, low_roots, scene)
        return ''

    if enable_solo_map_preview(context, project, map_id, low_roots):
        return map_id
    return ''

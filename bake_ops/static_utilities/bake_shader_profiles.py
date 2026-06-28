"""Procedural emit-shader profiles for Cycles selected-to-active bakes."""

from __future__ import annotations

import zlib

import bpy
from mathutils import Vector

from .bake_position_helpers import _BBOX_AXIS_EPSILON, longest_world_bbox_extent
from .bake_shader_override_helpers import BakeMaterialOverrideStack

_EMIT_MAT_PREFIX = '_LKS_BAKE_EMIT_'


def _axis_uniform_bbox_map_range(
    tree: bpy.types.NodeTree,
    value_socket: bpy.types.NodeSocket,
    bbox_min: float,
    longest_extent: float,
    *,
    location: tuple[float, float],
) -> bpy.types.NodeSocket:
    if longest_extent <= _BBOX_AXIS_EPSILON:
        value = tree.nodes.new('ShaderNodeValue')
        value.location = location
        value.outputs[0].default_value = 0.0
        return value.outputs[0]
    map_range = tree.nodes.new('ShaderNodeMapRange')
    map_range.location = location
    map_range.inputs['From Min'].default_value = bbox_min
    map_range.inputs['From Max'].default_value = bbox_min + longest_extent
    map_range.inputs['To Min'].default_value = 0.0
    map_range.inputs['To Max'].default_value = 1.0
    tree.links.new(value_socket, map_range.inputs['Value'])
    return map_range.outputs['Result']


def _create_bbox_normalized_position_emit_material(
    name: str,
    bbox_min: Vector,
    bbox_max: Vector,
) -> bpy.types.Material:
    """Emit world position remapped with uniform scale from the longest AABB edge."""
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    longest_extent = longest_world_bbox_extent(
        (bbox_min.x, bbox_min.y, bbox_min.z),
        (bbox_max.x, bbox_max.y, bbox_max.z),
    )

    geometry = tree.nodes.new('ShaderNodeNewGeometry')
    geometry.location = (-700, 0)
    separate = tree.nodes.new('ShaderNodeSeparateXYZ')
    separate.location = (-500, 0)
    tree.links.new(geometry.outputs['Position'], separate.inputs['Vector'])

    mapped_x = _axis_uniform_bbox_map_range(
        tree, separate.outputs['X'], bbox_min.x, longest_extent, location=(-300, 150),
    )
    mapped_y = _axis_uniform_bbox_map_range(
        tree, separate.outputs['Y'], bbox_min.y, longest_extent, location=(-300, 0),
    )
    mapped_z = _axis_uniform_bbox_map_range(
        tree, separate.outputs['Z'], bbox_min.z, longest_extent, location=(-300, -150),
    )

    combine = tree.nodes.new('ShaderNodeCombineColor')
    combine.mode = 'RGB'
    combine.location = (-50, 0)
    tree.links.new(mapped_x, combine.inputs['Red'])
    tree.links.new(mapped_y, combine.inputs['Green'])
    tree.links.new(mapped_z, combine.inputs['Blue'])

    emission = tree.nodes.new('ShaderNodeEmission')
    emission.location = (200, 0)
    emission.inputs['Strength'].default_value = 1.0
    tree.links.new(combine.outputs['Color'], emission.inputs['Color'])
    output = _ensure_material_output(tree)
    output.location = (400, 0)
    tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return material


def apply_bbox_position_emit_profile(
    high_meshes: list[bpy.types.Object],
    bbox_min: Vector,
    bbox_max: Vector,
    stack: BakeMaterialOverrideStack,
) -> None:
    """Swap high mesh materials to uniform-scale world-position emit."""
    for obj in high_meshes:
        if obj.type != 'MESH':
            continue
        emit_materials: list[bpy.types.Material | None] = []
        slot_count = max(1, len(obj.material_slots))
        for slot_index in range(slot_count):
            mat_name = f'{_EMIT_MAT_PREFIX}position_{obj.name}_{slot_index}'
            emit_materials.append(
                _create_bbox_normalized_position_emit_material(mat_name, bbox_min, bbox_max),
            )
        stack.assign_slots(obj, emit_materials)


def _id_color_from_key(key: str) -> tuple[float, float, float, float]:
    digest = zlib.crc32(key.encode('utf-8')) & 0xFFFFFFFF
    return (
        ((digest >> 0) & 0xFF) / 255.0,
        ((digest >> 8) & 0xFF) / 255.0,
        ((digest >> 16) & 0xFF) / 255.0,
        1.0,
    )


def _get_principled(material: bpy.types.Material) -> bpy.types.ShaderNodeBsdfPrincipled | None:
    if not material.use_nodes or material.node_tree is None:
        return None
    node = material.node_tree.nodes.get('Principled BSDF')
    if node is not None and node.type == 'BSDF_PRINCIPLED':
        return node
    for candidate in material.node_tree.nodes:
        if candidate.type == 'BSDF_PRINCIPLED':
            return candidate
    return None


def _ensure_material_output(tree: bpy.types.NodeTree) -> bpy.types.ShaderNodeOutputMaterial:
    output = tree.nodes.get('Material Output')
    if output is None:
        output = tree.nodes.new('ShaderNodeOutputMaterial')
    return output


_SKIP_NODE_MIRROR_PROPS = frozenset({
    'rna_type', 'name', 'label', 'location', 'width', 'height', 'dimensions',
    'inputs', 'outputs', 'internal_links', 'parent', 'warning_propagation',
    'use_custom_color', 'color', 'select', 'show_options', 'show_preview',
    'hide', 'mute', 'is_active_output', 'bl_idname', 'bl_label', 'bl_icon',
    'bl_static_type', 'bl_width_default', 'bl_width_min', 'bl_width_max',
    'bl_height_default', 'bl_height_min', 'bl_height_max', 'node_tree',
})


def _copy_socket_default(
    dst_socket: bpy.types.NodeSocket,
    src_socket: bpy.types.NodeSocket,
) -> None:
    if not hasattr(dst_socket, 'default_value'):
        return
    try:
        dst_socket.default_value = src_socket.default_value
    except (AttributeError, TypeError, ValueError):
        pass


def _copy_shader_node_settings(src: bpy.types.Node, dst: bpy.types.Node) -> None:
    for prop in src.bl_rna.properties:
        ident = prop.identifier
        if ident in _SKIP_NODE_MIRROR_PROPS or prop.is_readonly:
            continue
        if prop.type not in {'STRING', 'ENUM', 'BOOLEAN', 'INT', 'FLOAT', 'POINTER'}:
            continue
        try:
            setattr(dst, ident, getattr(src, ident))
        except (AttributeError, TypeError):
            pass


def _socket_index_in_node(src_socket: bpy.types.NodeSocket) -> int | None:
    """Return src_socket's index in its parent node (Blender 5.1-safe)."""
    socket_index = getattr(src_socket, 'index', None)
    if socket_index is not None:
        return socket_index
    src_node = src_socket.node
    sockets = src_node.outputs if src_socket.is_output else src_node.inputs
    for index, candidate in enumerate(sockets):
        if candidate is src_socket:
            return index
    return None


def _resolve_mirrored_socket(
    mirrored_node: bpy.types.Node,
    src_socket: bpy.types.NodeSocket,
) -> bpy.types.NodeSocket | None:
    """Match a mirrored socket to the source by name, identifier, or index."""
    sockets = mirrored_node.outputs if src_socket.is_output else mirrored_node.inputs
    resolved = sockets.get(src_socket.name)
    if resolved is not None:
        return resolved
    resolved = sockets.get(src_socket.identifier)
    if resolved is not None:
        return resolved
    socket_index = _socket_index_in_node(src_socket)
    if socket_index is not None and 0 <= socket_index < len(sockets):
        return sockets[socket_index]
    if len(sockets) == 1:
        return sockets[0]
    return None


def _mirror_shader_node(
    src_node: bpy.types.Node,
    dest_tree: bpy.types.NodeTree,
    node_map: dict[int, bpy.types.Node],
) -> bpy.types.Node:
    cached = node_map.get(id(src_node))
    if cached is not None:
        return cached

    dst_node = dest_tree.nodes.new(src_node.bl_idname)
    node_map[id(src_node)] = dst_node

    if src_node.type == 'GROUP' and src_node.node_tree is not None:
        dst_node.node_tree = src_node.node_tree

    for src_input in src_node.inputs:
        dst_input = _resolve_mirrored_socket(dst_node, src_input)
        if dst_input is None:
            continue
        if src_input.is_linked:
            link = src_input.links[0]
            mirrored_from = _mirror_shader_node(link.from_node, dest_tree, node_map)
            out_socket = _resolve_mirrored_socket(mirrored_from, link.from_socket)
            if out_socket is None:
                continue
            dest_tree.links.new(out_socket, dst_input)
        else:
            _copy_socket_default(dst_input, src_input)

    _copy_shader_node_settings(src_node, dst_node)
    return dst_node


def _mirror_linked_socket(
    source_socket: bpy.types.NodeSocket,
    dest_tree: bpy.types.NodeTree,
) -> bpy.types.NodeSocket | None:
    """Recreate the upstream node chain from source_socket's tree inside dest_tree."""
    if not source_socket.is_linked:
        return None
    link = source_socket.links[0]
    mirrored = _mirror_shader_node(link.from_node, dest_tree, {})
    return _resolve_mirrored_socket(mirrored, link.from_socket)


def _scalar_to_emit_color(tree: bpy.types.NodeTree, socket: bpy.types.NodeSocket) -> bpy.types.NodeSocket:
    combine = tree.nodes.new('ShaderNodeCombineColor')
    combine.mode = 'RGB'
    tree.links.new(socket, combine.inputs['Red'])
    tree.links.new(socket, combine.inputs['Green'])
    tree.links.new(socket, combine.inputs['Blue'])
    combine.inputs['Alpha'].default_value = 1.0
    return combine.outputs['Color']


def _create_flat_emit_material(name: str, rgba: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = rgba
    emission.inputs['Strength'].default_value = 1.0
    output = _ensure_material_output(tree)
    tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return material


def _build_vertex_color_emit_material(
    mesh: bpy.types.Mesh | None,
    material_name: str,
) -> bpy.types.Material:
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(material_name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.0
    output = _ensure_material_output(tree)
    attr = tree.nodes.new('ShaderNodeAttribute')
    if mesh is not None and mesh.color_attributes:
        attr.attribute_name = mesh.color_attributes.active_color.name
    tree.links.new(attr.outputs['Color'], emission.inputs['Color'])
    tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return material


def _build_emit_from_principled(
    source: bpy.types.Material | None,
    *,
    profile: str,
    material_name: str,
) -> bpy.types.Material:
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(material_name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.0
    output = _ensure_material_output(tree)

    principled = _get_principled(source) if source is not None else None
    if principled is None:
        if profile == 'metalness':
            emission.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
        elif profile == 'specular':
            emission.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1.0)
        elif profile == 'emissive':
            emission.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
        else:
            emission.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1.0)
    elif profile == 'albedo':
        # Single albedo map: Principled Base Color for dielectric and metal regions.
        base_color = principled.inputs['Base Color']
        if base_color.is_linked:
            mirrored = _mirror_linked_socket(base_color, tree)
            if mirrored is not None:
                tree.links.new(mirrored, emission.inputs['Color'])
            else:
                emission.inputs['Color'].default_value = base_color.default_value
        else:
            emission.inputs['Color'].default_value = base_color.default_value
    elif profile == 'metalness':
        metallic = principled.inputs['Metallic']
        if metallic.is_linked:
            mirrored = _mirror_linked_socket(metallic, tree)
            if mirrored is not None:
                color_socket = _scalar_to_emit_color(tree, mirrored)
                tree.links.new(color_socket, emission.inputs['Color'])
            else:
                value = metallic.default_value
                emission.inputs['Color'].default_value = (value, value, value, 1.0)
        else:
            value = metallic.default_value
            emission.inputs['Color'].default_value = (value, value, value, 1.0)
    elif profile == 'emissive':
        emit_color = principled.inputs['Emission Color']
        strength = principled.inputs['Emission Strength']
        if emit_color.is_linked or strength.is_linked:
            multiply = tree.nodes.new('ShaderNodeMath')
            multiply.operation = 'MULTIPLY'
            multiply.inputs[1].default_value = 1.0
            if strength.is_linked:
                mirrored_strength = _mirror_linked_socket(strength, tree)
                if mirrored_strength is not None:
                    tree.links.new(mirrored_strength, multiply.inputs[1])
                else:
                    multiply.inputs[1].default_value = strength.default_value
            else:
                multiply.inputs[1].default_value = strength.default_value
            if emit_color.is_linked:
                mirrored_emit = _mirror_linked_socket(emit_color, tree)
                if mirrored_emit is not None:
                    tree.links.new(mirrored_emit, multiply.inputs[0])
                    color_socket = _scalar_to_emit_color(tree, multiply.outputs['Value'])
                    tree.links.new(color_socket, emission.inputs['Color'])
                else:
                    base = emit_color.default_value
                    scale = multiply.inputs[1].default_value
                    emission.inputs['Color'].default_value = (
                        base[0] * scale,
                        base[1] * scale,
                        base[2] * scale,
                        1.0,
                    )
            else:
                base = emit_color.default_value
                emission.inputs['Color'].default_value = (
                    base[0] * multiply.inputs[1].default_value,
                    base[1] * multiply.inputs[1].default_value,
                    base[2] * multiply.inputs[1].default_value,
                    1.0,
                )
                tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
                return material
        else:
            base = emit_color.default_value
            scale = strength.default_value
            emission.inputs['Color'].default_value = (
                base[0] * scale, base[1] * scale, base[2] * scale, 1.0,
            )
    elif profile == 'specular':
        level_socket = principled.inputs.get('Specular IOR Level')
        if level_socket is None:
            level_socket = principled.inputs.get('Specular')
        tint_socket = principled.inputs.get('Specular Tint')
        if level_socket is None:
            emission.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1.0)
        elif level_socket.is_linked:
            mirrored = _mirror_linked_socket(level_socket, tree)
            if mirrored is not None:
                color_socket = _scalar_to_emit_color(tree, mirrored)
                if tint_socket is not None and tint_socket.is_linked:
                    mirrored_tint = _mirror_linked_socket(tint_socket, tree)
                    if mirrored_tint is not None:
                        multiply = tree.nodes.new('ShaderNodeMath')
                        multiply.operation = 'MULTIPLY'
                        multiply.inputs[1].default_value = 1.0
                        tree.links.new(mirrored_tint, multiply.inputs[0])
                        tree.links.new(color_socket, multiply.inputs[1])
                        color_socket = _scalar_to_emit_color(tree, multiply.outputs['Value'])
                tree.links.new(color_socket, emission.inputs['Color'])
            else:
                level = float(level_socket.default_value)
                tint = tint_socket.default_value if tint_socket is not None else (1.0, 1.0, 1.0, 1.0)
                emission.inputs['Color'].default_value = (
                    level * tint[0],
                    level * tint[1],
                    level * tint[2],
                    1.0,
                )
        else:
            level = float(level_socket.default_value)
            if tint_socket is not None and tint_socket.is_linked:
                mirrored_tint = _mirror_linked_socket(tint_socket, tree)
                if mirrored_tint is not None:
                    multiply = tree.nodes.new('ShaderNodeMath')
                    multiply.operation = 'MULTIPLY'
                    multiply.inputs[1].default_value = level
                    tree.links.new(mirrored_tint, multiply.inputs[0])
                    color_socket = _scalar_to_emit_color(tree, multiply.outputs['Value'])
                    tree.links.new(color_socket, emission.inputs['Color'])
                else:
                    tint = tint_socket.default_value
                    emission.inputs['Color'].default_value = (
                        level * tint[0],
                        level * tint[1],
                        level * tint[2],
                        1.0,
                    )
            else:
                tint = tint_socket.default_value if tint_socket is not None else (1.0, 1.0, 1.0, 1.0)
                emission.inputs['Color'].default_value = (
                    level * tint[0],
                    level * tint[1],
                    level * tint[2],
                    1.0,
                )
    elif profile == 'transparency':
        alpha = principled.inputs['Alpha']
        if alpha.is_linked:
            mirrored = _mirror_linked_socket(alpha, tree)
            if mirrored is not None:
                color_socket = _scalar_to_emit_color(tree, mirrored)
                tree.links.new(color_socket, emission.inputs['Color'])
            else:
                value = alpha.default_value
                emission.inputs['Color'].default_value = (value, value, value, 1.0)
        else:
            value = alpha.default_value
            emission.inputs['Color'].default_value = (value, value, value, 1.0)
    else:
        emission.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1.0)

    tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return material


_MAP_EMIT_PROFILE: dict[str, str] = {
    'albedo': 'albedo',
    'specular': 'specular',
    'metalness': 'metalness',
    'emissive': 'emissive',
    'transparency': 'transparency',
    'vertex_color': 'vertex_color',
}


def emit_rgb_from_principled_material(
    material: bpy.types.Material | None,
    *,
    profile: str,
) -> tuple[float, float, float, float]:
    """Return emit-encoded RGBA for one source material without persisting temp assets."""
    temp_name = f'{_EMIT_MAT_PREFIX}probe_{profile}_{id(material)}'
    emit_mat = _build_emit_from_principled(material, profile=profile, material_name=temp_name)
    for node in emit_mat.node_tree.nodes:
        if node.type == 'EMISSION':
            rgba = node.inputs['Color'].default_value
            return (float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]))
    return (0.5, 0.5, 0.5, 1.0)


def apply_emit_profile_for_map(
    high_meshes: list[bpy.types.Object],
    map_id: str,
    stack: BakeMaterialOverrideStack,
) -> None:
    """Swap high mesh materials to emit-encoding profiles for one map_id."""
    if map_id in _MAP_EMIT_PROFILE:
        profile = _MAP_EMIT_PROFILE[map_id]
        for obj in high_meshes:
            if obj.type != 'MESH':
                continue
            emit_materials: list[bpy.types.Material | None] = []
            if profile == 'vertex_color':
                name = f'{_EMIT_MAT_PREFIX}{map_id}_{obj.name}'
                emit_mat = _build_vertex_color_emit_material(obj.data, name)
                emit_materials = [emit_mat] * max(1, len(obj.material_slots))
            else:
                for slot_index, slot in enumerate(obj.material_slots):
                    source = slot.material
                    name = f'{_EMIT_MAT_PREFIX}{map_id}_{obj.name}_{slot_index}'
                    emit_materials.append(
                        _build_emit_from_principled(source, profile=profile, material_name=name),
                    )
                if not emit_materials:
                    emit_materials.append(
                        _build_emit_from_principled(
                            None,
                            profile=profile,
                            material_name=f'{_EMIT_MAT_PREFIX}{map_id}_{obj.name}_0',
                        ),
                    )
            stack.assign_slots(obj, emit_materials)
        return

    if map_id == 'material_id':
        # Stable RGB per bpy.data.material (same color on every object/slot using that material).
        emit_by_material_key: dict[str, bpy.types.Material] = {}
        for obj in high_meshes:
            if obj.type != 'MESH':
                continue
            emit_materials: list[bpy.types.Material | None] = []
            for slot in obj.material_slots:
                source = slot.material
                cache_key = f'mat:{source.name}' if source is not None else 'mat:__empty__'
                emit_mat = emit_by_material_key.get(cache_key)
                if emit_mat is None:
                    color = _id_color_from_key(cache_key)
                    emit_mat = _create_flat_emit_material(f'{_EMIT_MAT_PREFIX}{cache_key}', color)
                    emit_by_material_key[cache_key] = emit_mat
                emit_materials.append(emit_mat)
            if not emit_materials:
                cache_key = 'mat:__empty__'
                emit_mat = emit_by_material_key.get(cache_key)
                if emit_mat is None:
                    color = _id_color_from_key(cache_key)
                    emit_mat = _create_flat_emit_material(f'{_EMIT_MAT_PREFIX}{cache_key}', color)
                    emit_by_material_key[cache_key] = emit_mat
                emit_materials.append(emit_mat)
            stack.assign_slots(obj, emit_materials)
        return

    if map_id == 'object_id':
        # Stable RGB per mesh object (one flat color for all slots on that object).
        for obj in high_meshes:
            if obj.type != 'MESH':
                continue
            color = _id_color_from_key(f'obj:{obj.name}')
            emit_mat = _create_flat_emit_material(f'{_EMIT_MAT_PREFIX}obj:{obj.name}', color)
            stack.assign_slots(obj, [emit_mat] * max(1, len(obj.material_slots)))


def map_id_uses_emit_profile(map_id: str) -> bool:
    return map_id in _MAP_EMIT_PROFILE or map_id in ('material_id', 'object_id')

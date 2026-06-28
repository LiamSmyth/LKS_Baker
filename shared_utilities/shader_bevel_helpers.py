"""Shader-node bevel setup: mesh attributes and material graph wiring."""

from __future__ import annotations

from dataclasses import dataclass

import bpy
import bmesh
import numpy as np

from .lks_constants import (
    ATTR_SHADER_BEVEL_SIZE,
    MAT_NAME_DEFAULT_BEVEL,
    NODE_NAME_SHADER_BEVEL,
    NODE_NAME_SHADER_BEVEL_ATTR,
)

_DEFAULT_BEVEL_BASE_COLOR = (0.5, 0.5, 0.5, 1.0)
_DEFAULT_BEVEL_ROUGHNESS = 0.15
_DEFAULT_BEVEL_METALLIC = 1.0
_SHADER_BEVEL_SAMPLES_MIN = 2
_SHADER_BEVEL_SAMPLES_MAX = 128
from .material_helpers import new_geometry_node
from .mesh_mode_helpers import edit_mode_for_ops, preserve_mesh_mode

_BSDF_TYPES = frozenset({
    'BSDF_PRINCIPLED',
    'BSDF_DIFFUSE',
    'BSDF_LAMBERT',
    'BSDF_TOON',
    'BSDF_TRANSLUCENT',
    'BSDF_HAIR',
    'BSDF_SHEEN',
})


def iter_mesh_selection(context: bpy.types.Context) -> list[bpy.types.Object]:
    return [obj for obj in context.selected_objects if obj.type == 'MESH']


def _clamp_shader_bevel_samples(samples: int) -> int:
    return max(_SHADER_BEVEL_SAMPLES_MIN, min(_SHADER_BEVEL_SAMPLES_MAX, int(samples)))


def _find_shader_bevel_node(
    node_tree: bpy.types.NodeTree,
) -> bpy.types.ShaderNodeBevel | None:
    node = _find_node_by_name(node_tree.nodes, NODE_NAME_SHADER_BEVEL)
    if node is not None and node.type == 'BEVEL':
        return node
    return None


def _set_bevel_node_samples(
    bevel_node: bpy.types.ShaderNodeBevel,
    samples: int,
) -> None:
    bevel_node.samples = _clamp_shader_bevel_samples(samples)


def get_or_create_default_bevel_material() -> bpy.types.Material:
    """Return chrome-like default material for meshes without material slots."""
    mat = bpy.data.materials.get(MAT_NAME_DEFAULT_BEVEL)
    if mat is not None:
        return mat

    mat = bpy.data.materials.new(name=MAT_NAME_DEFAULT_BEVEL)
    mat.diffuse_color = _DEFAULT_BEVEL_BASE_COLOR
    mat.use_nodes = True

    bsdf = find_surface_bsdf(mat)
    if bsdf is None:
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break

    if bsdf is not None:
        base_color = bsdf.inputs.get('Base Color')
        if base_color is not None:
            base_color.default_value = _DEFAULT_BEVEL_BASE_COLOR
        roughness = bsdf.inputs.get('Roughness')
        if roughness is not None:
            roughness.default_value = _DEFAULT_BEVEL_ROUGHNESS
        metallic = bsdf.inputs.get('Metallic')
        if metallic is not None:
            metallic.default_value = _DEFAULT_BEVEL_METALLIC

    return mat


def assign_default_material_to_objects_without_slots(
    objects: list[bpy.types.Object],
) -> int:
    """Assign default bevel material only to meshes with zero material slots."""
    mat = get_or_create_default_bevel_material()
    assigned = 0
    for obj in objects:
        if obj.type != 'MESH' or len(obj.material_slots) > 0:
            continue
        obj.data.materials.append(mat)
        assigned += 1
    return assigned


def selection_has_shader_bevel_setup(
    objects: list[bpy.types.Object],
) -> bool:
    for obj in objects:
        if mesh_has_shader_bevel_attribute(obj.data):
            return True

    for mat in collect_materials_from_objects(objects):
        if mat.node_tree is None:
            continue
        if _find_shader_bevel_node(mat.node_tree) is not None:
            return True
    return False


def compute_shader_bevel_preset_size(
    context: bpy.types.Context,
    preset_size: float,
    multiply: float,
) -> float:
    """Resolve preset / multiply size for shader bevel (0-1)."""
    scn = context.scene
    if preset_size >= 0.0:
        return preset_size

    if multiply != 1.0:
        selection = iter_mesh_selection(context)
        if selection and not selection_has_shader_bevel_setup(selection):
            base = 0.1
        else:
            base = scn.lks_shader_bevel_size
        return min(1.0, max(0.0, base * multiply))

    return scn.lks_shader_bevel_size


def collect_materials_from_objects(
    objects: list[bpy.types.Object],
) -> set[bpy.types.Material]:
    materials: set[bpy.types.Material] = set()
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material is not None:
                materials.add(slot.material)
    return materials


def mesh_has_shader_bevel_attribute(mesh: bpy.types.Mesh) -> bool:
    return ATTR_SHADER_BEVEL_SIZE in mesh.attributes


def get_or_create_shader_bevel_attribute(mesh: bpy.types.Mesh) -> bpy.types.Attribute:
    attr = mesh.attributes.get(ATTR_SHADER_BEVEL_SIZE)
    if attr is None:
        attr = mesh.attributes.new(
            name=ATTR_SHADER_BEVEL_SIZE,
            type='FLOAT',
            domain='POINT',
        )
    return attr


def _fill_entire_attribute(mesh: bpy.types.Mesh, value: float) -> None:
    attr = get_or_create_shader_bevel_attribute(mesh)
    count = len(mesh.vertices)
    if count == 0:
        return
    values = np.full(count, value, dtype=np.float32)
    attr.data.foreach_set('value', values)
    mesh.update()


def _selected_vert_indices_in_edit_mesh(mesh: bpy.types.Mesh) -> np.ndarray | None:
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    vert_mask = np.zeros(len(bm.verts), dtype=np.bool_)
    has_selection = False

    for vert in bm.verts:
        if vert.select:
            vert_mask[vert.index] = True
            has_selection = True

    for face in bm.faces:
        if face.select:
            for vert in face.verts:
                vert_mask[vert.index] = True
                has_selection = True

    if not has_selection:
        return None
    return np.nonzero(vert_mask)[0]


@dataclass
class _AttributeFillScope:
    fill_entire: bool
    vert_indices: np.ndarray | None = None


def _fill_verts_attribute(
    mesh: bpy.types.Mesh,
    value: float,
    vert_indices: np.ndarray,
) -> None:
    attr = get_or_create_shader_bevel_attribute(mesh)
    values = np.zeros(len(mesh.vertices), dtype=np.float32)
    attr.data.foreach_get('value', values)
    values[vert_indices] = value
    attr.data.foreach_set('value', values)
    mesh.update()


def capture_shader_bevel_fill_scope(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> _AttributeFillScope:
    if obj.mode != 'EDIT':
        return _AttributeFillScope(fill_entire=True)

    with edit_mode_for_ops(context, obj):
        selected_verts = _selected_vert_indices_in_edit_mesh(obj.data)
        if selected_verts is None:
            return _AttributeFillScope(fill_entire=True)
        return _AttributeFillScope(fill_entire=False, vert_indices=selected_verts)


def apply_shader_bevel_attribute(
    obj: bpy.types.Object,
    size: float,
    scope: _AttributeFillScope,
) -> None:
    mesh = obj.data
    if scope.fill_entire:
        _fill_entire_attribute(mesh, size)
    elif scope.vert_indices is not None:
        _fill_verts_attribute(mesh, size, scope.vert_indices)


def remove_shader_bevel_attribute(mesh: bpy.types.Mesh) -> None:
    if ATTR_SHADER_BEVEL_SIZE in mesh.attributes:
        mesh.attributes.remove(mesh.attributes[ATTR_SHADER_BEVEL_SIZE])


def mesh_objects_using_material(mat: bpy.types.Material) -> list[bpy.types.Object]:
    users: list[bpy.types.Object] = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            if slot.material == mat:
                users.append(obj)
                break
    return users


def material_still_needs_shader_bevel(
    mat: bpy.types.Material,
    excluded_objects: set[bpy.types.Object] | None = None,
) -> bool:
    excluded = excluded_objects or set()
    for obj in mesh_objects_using_material(mat):
        if obj in excluded:
            continue
        if mesh_has_shader_bevel_attribute(obj.data):
            return True
    return False


def _bsdf_has_normal_input(node: bpy.types.Node) -> bool:
    return node.inputs.get('Normal') is not None


def _find_bsdf_from_node(node: bpy.types.Node) -> bpy.types.Node | None:
    if node.type in _BSDF_TYPES and _bsdf_has_normal_input(node):
        return node
    if node.type == 'GROUP' and _bsdf_has_normal_input(node):
        return node
    return None


def find_surface_bsdf(mat: bpy.types.Material) -> bpy.types.Node | None:
    if mat is None or mat.node_tree is None:
        return None

    output = None
    for node in mat.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            output = node
            break
    if output is None:
        return None

    surface_input = output.inputs.get('Surface')
    if surface_input is None or not surface_input.links:
        return None

    from_node = surface_input.links[0].from_node
    bsdf = _find_bsdf_from_node(from_node)
    if bsdf is not None:
        return bsdf

    if from_node.type in {'ADD_SHADER', 'MIX_SHADER'}:
        for inp in from_node.inputs:
            if not inp.links:
                continue
            bsdf = _find_bsdf_from_node(inp.links[0].from_node)
            if bsdf is not None:
                return bsdf
    return None


def _find_node_by_name(nodes: bpy.types.Nodes, name: str) -> bpy.types.Node | None:
    return nodes.get(name)


def _get_or_create_attr_node(
    node_tree: bpy.types.NodeTree,
    bsdf_node: bpy.types.Node,
) -> bpy.types.ShaderNodeAttribute:
    attr_node = _find_node_by_name(node_tree.nodes, NODE_NAME_SHADER_BEVEL_ATTR)
    if attr_node is None:
        attr_node = node_tree.nodes.new(type='ShaderNodeAttribute')
        attr_node.name = NODE_NAME_SHADER_BEVEL_ATTR
        attr_node.label = NODE_NAME_SHADER_BEVEL_ATTR
        attr_node.attribute_name = ATTR_SHADER_BEVEL_SIZE
        attr_node.location = (
            bsdf_node.location.x - 300,
            bsdf_node.location.y - 200,
        )
    else:
        attr_node.attribute_name = ATTR_SHADER_BEVEL_SIZE
    return attr_node


def _attribute_scalar_output(attr_node: bpy.types.ShaderNodeAttribute):
    return attr_node.outputs.get('Fac') or attr_node.outputs[0]


def _link_radius_from_attribute(
    node_tree: bpy.types.NodeTree,
    bevel_node: bpy.types.ShaderNodeBevel,
    attr_node: bpy.types.ShaderNodeAttribute,
) -> None:
    radius_input = bevel_node.inputs.get('Radius')
    if radius_input is None:
        return
    for link in list(radius_input.links):
        node_tree.links.remove(link)
    node_tree.links.new(_attribute_scalar_output(attr_node), radius_input)


def setup_shader_bevel_on_material(
    mat: bpy.types.Material,
    samples: int,
) -> str | None:
    """Wire bevel nodes on *mat*. Returns a warning message or None on success."""
    if mat is None or mat.node_tree is None:
        return f"Material '{mat.name}' has no node tree" if mat else "Missing material"

    if not mat.use_nodes:
        mat.use_nodes = True

    node_tree = mat.node_tree
    bsdf = find_surface_bsdf(mat)
    if bsdf is None:
        return f"Material '{mat.name}': no BSDF with Normal input found on Surface output"
    if bsdf.inputs.get('Normal') is None:
        return f"Material '{mat.name}': BSDF has no Normal input"

    normal_input = bsdf.inputs['Normal']
    bevel_node = _find_shader_bevel_node(node_tree)

    if bevel_node is None:
        bevel_node = node_tree.nodes.new(type='ShaderNodeBevel')
        bevel_node.name = NODE_NAME_SHADER_BEVEL
        bevel_node.label = NODE_NAME_SHADER_BEVEL
        bevel_node.location = (
            bsdf.location.x - 150,
            bsdf.location.y - 80,
        )

        incoming_normal = None
        if normal_input.links:
            incoming_normal = normal_input.links[0].from_socket
            node_tree.links.remove(normal_input.links[0])

        bevel_normal = bevel_node.inputs.get('Normal')
        if incoming_normal is not None and bevel_normal is not None:
            node_tree.links.new(incoming_normal, bevel_normal)

        node_tree.links.new(bevel_node.outputs['Normal'], normal_input)
    else:
        bevel_normal = bevel_node.inputs.get('Normal')
        if bevel_normal is not None and not bevel_normal.links:
            geom = new_geometry_node(node_tree.nodes)
            geom.location = (bevel_node.location.x - 180, bevel_node.location.y - 120)
            node_tree.links.new(geom.outputs['Normal'], bevel_normal)

    _set_bevel_node_samples(bevel_node, samples)

    attr_node = _get_or_create_attr_node(node_tree, bsdf)
    _link_radius_from_attribute(node_tree, bevel_node, attr_node)
    return None


def bypass_and_remove_shader_bevel_node(mat: bpy.types.Material) -> bool:
    if mat is None or mat.node_tree is None:
        return False

    node_tree = mat.node_tree
    bevel_node = _find_shader_bevel_node(node_tree)
    if bevel_node is None:
        return False

    bsdf = find_surface_bsdf(mat)
    if bsdf is not None:
        normal_input = bsdf.inputs.get('Normal')
        bevel_normal_in = bevel_node.inputs.get('Normal')
        if normal_input is not None:
            for link in list(normal_input.links):
                if link.from_node == bevel_node:
                    node_tree.links.remove(link)

            if bevel_normal_in is not None and bevel_normal_in.links:
                incoming = bevel_normal_in.links[0].from_socket
                node_tree.links.new(incoming, normal_input)

    attr_node = _find_node_by_name(node_tree.nodes, NODE_NAME_SHADER_BEVEL_ATTR)
    if attr_node is not None:
        node_tree.nodes.remove(attr_node)

    node_tree.nodes.remove(bevel_node)
    return True


def ensure_cycles_render_engine(context: bpy.types.Context) -> None:
    context.scene.render.engine = 'CYCLES'


def apply_shader_bevel_to_selection(
    context: bpy.types.Context,
    size: float,
    samples: int,
    report,
) -> tuple[int, int]:
    selection = iter_mesh_selection(context)
    if not selection:
        report({'WARNING'}, "No mesh objects selected")
        return 0, 0

    ensure_cycles_render_engine(context)
    assign_default_material_to_objects_without_slots(selection)

    fill_scopes = {
        obj.name: capture_shader_bevel_fill_scope(context, obj)
        for obj in selection
    }

    with preserve_mesh_mode(context):
        for obj in selection:
            apply_shader_bevel_attribute(obj, size, fill_scopes[obj.name])

    materials = collect_materials_from_objects(selection)
    warnings = 0
    for mat in materials:
        warning = setup_shader_bevel_on_material(mat, samples)
        if warning:
            report({'WARNING'}, warning)
            warnings += 1

    return len(selection), warnings


def clear_shader_bevel_from_selection(
    context: bpy.types.Context,
    report,
) -> tuple[int, int]:
    selection = iter_mesh_selection(context)
    if not selection:
        report({'WARNING'}, "No mesh objects selected")
        return 0, 0

    selection_set = set(selection)
    materials = collect_materials_from_objects(selection)

    with preserve_mesh_mode(context):
        for obj in selection:
            remove_shader_bevel_attribute(obj.data)

    bypassed = 0
    for mat in materials:
        if material_still_needs_shader_bevel(mat, excluded_objects=selection_set):
            continue
        if bypass_and_remove_shader_bevel_node(mat):
            bypassed += 1

    return len(selection), bypassed

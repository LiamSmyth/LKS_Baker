import bpy


def principled_emission_color_input(node: bpy.types.ShaderNodeBsdfPrincipled):
    """Return the Principled BSDF emission color input (4.0+ compatible)."""
    return node.inputs.get('Emission Color') or node.inputs['Emission']


def set_principled_emission_strength(node: bpy.types.ShaderNodeBsdfPrincipled, strength: float = 1.0) -> None:
    strength_input = node.inputs.get('Emission Strength')
    if strength_input is not None:
        strength_input.default_value = strength


def new_separate_color_node(nodes: bpy.types.Nodes):
    if hasattr(bpy.types, 'ShaderNodeSeparateColor'):
        node = nodes.new(type='ShaderNodeSeparateColor')
        node.mode = 'RGB'
        return node
    return nodes.new(type='ShaderNodeSeparateRGB')


def new_combine_color_node(nodes: bpy.types.Nodes):
    if hasattr(bpy.types, 'ShaderNodeCombineColor'):
        node = nodes.new(type='ShaderNodeCombineColor')
        node.mode = 'RGB'
        return node
    return nodes.new(type='ShaderNodeCombineRGB')


def new_geometry_node(nodes: bpy.types.Nodes):
    if hasattr(bpy.types, 'ShaderNodeGeometry'):
        return nodes.new(type='ShaderNodeGeometry')
    return nodes.new(type='ShaderNodeNewGeometry')


def configure_alpha_clip_material(mat: bpy.types.Material, threshold: float = 0.333333) -> None:
    """Configure material for alpha-clip style rendering in Blender 5.x."""
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'DITHERED'
    elif hasattr(mat, 'blend_method'):
        mat.blend_method = 'CLIP'
        if hasattr(mat, 'alpha_threshold'):
            mat.alpha_threshold = threshold


def configure_alpha_blend_material(mat: bpy.types.Material) -> None:
    """Configure material for alpha-blended transparency in Blender 5.x."""
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'BLENDED'
    elif hasattr(mat, 'blend_method'):
        mat.blend_method = 'BLEND'

import bpy
from typing import List, Optional


def get_or_create_color_attribute(
    mesh: bpy.types.Mesh,
    name: str,
    *,
    domain: str = 'CORNER',
    attr_type: str = 'BYTE_COLOR',
) -> bpy.types.Attribute:
    attr = mesh.color_attributes.get(name)
    if attr is None:
        attr = mesh.color_attributes.new(name=name, type=attr_type, domain=domain)
    return attr


def set_active_color_attribute(mesh: bpy.types.Mesh, name: str) -> Optional[bpy.types.Attribute]:
    attr = mesh.color_attributes.get(name)
    if attr is None:
        return None
    mesh.color_attributes.active_color = attr
    return attr


def get_active_color_attribute(mesh: bpy.types.Mesh) -> Optional[bpy.types.Attribute]:
    return mesh.color_attributes.active_color


def get_attribute_data(mesh: bpy.types.Mesh, attr: bpy.types.Attribute):
    """Return writable attribute data (5.1-safe for color attribute proxies)."""
    return mesh.attributes[attr.name].data


def has_active_color_attribute(mesh: bpy.types.Mesh) -> bool:
    return get_active_color_attribute(mesh) is not None


def set_bake_color_target(context: bpy.types.Context) -> None:
    """Set render bake target to the active color attribute (Blender 4.1+)."""
    bake = context.scene.render.bake
    for target in ('ACTIVE_COLOR_ATTRIBUTE', 'VERTEX_COLORS'):
        try:
            bake.target = target
            return
        except (TypeError, ValueError):
            continue


def setup_named_vertex_color_and_fill_with_color(color: List[float] = [0.5, 0.5, 0.5], vertex_color_name: str = "Col") -> None:
    """
    Sets up a named vertex color layer on selected mesh objects and fills it with the specified color.

    Args:
        color (List[float], optional): The RGB color to fill the vertex color layer with. Defaults to [0.5, 0.5, 0.5].
        vertex_color_name (str, optional): The name of the vertex color layer to create or use. Defaults to "Col".
    """
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.data.brushes["Draw"].color = color

    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            mesh = obj.data
            vertex_color_set = get_or_create_color_attribute(mesh, vertex_color_name)
            mesh.color_attributes.active_color = vertex_color_set

            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='VERTEX_PAINT')
            bpy.ops.paint.vertex_color_set()
            bpy.ops.object.mode_set(mode='OBJECT')


def set_mesh_vcol_count(mesh: bpy.types.Mesh, count: int, prune=True) -> None:
    """
    Sets the number of vertex color attributes on a mesh.

    Args:
        mesh (bpy.types.Mesh): The mesh to modify.
        count (int): The desired number of vertex color attributes.
        prune (bool, optional): Whether to remove excess vertex color attributes if the count is less than the current number. Defaults to True.
    """
    # minimum count is 0, max count is 10
    count = max(0, count)
    count = min(count, 10)

    num_vcol_attributes = len(mesh.color_attributes)

    # If there aren't enough color attributes, add more until there are enough.
    if num_vcol_attributes < count:
        for i in range(count - num_vcol_attributes):
            mesh.color_attributes.new(
                name="Col_" + str(i), type="BYTE_COLOR", domain='CORNER')

    # If there are too many color attributes, remove them until there is the correct number when prune is True
    if prune:
        if num_vcol_attributes > count:
            for i in range(num_vcol_attributes - count):
                mesh.color_attributes.remove(mesh.color_attributes[-1])


def name_vcols_on_mesh(mesh: bpy.types.Mesh, names: List[str] = []) -> None:
    """
    Names the UV channels of the given mesh with the provided names.

    Args:
        mesh (bpy.types.Mesh): The mesh to name the UV channels for.
        names (List[str]): The list of names to assign to the UV channels.

    Returns:
        None
    """
    vcol_attributes: bpy.types.AttributeGroup = mesh.color_attributes
    num_uv_channels = len(vcol_attributes)

    if num_uv_channels == 0:
        return

    # Name all uv channels to something temporary to prevent name clash
    for i in range(num_uv_channels):
        vcol_attributes[i].name = "Temp_" + str(i)

    for i in range(num_uv_channels):
        if i < len(names):
            vcol_attributes[i].name = names[i]
        else:
            if i == 0:
                vcol_attributes[i].name = "Col"
            else:
                vcol_attributes[i].name = "Col_" + str(i - len(names))

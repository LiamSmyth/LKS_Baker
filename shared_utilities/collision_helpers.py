import bpy

from .material_helpers import configure_alpha_blend_material
from .lks_constants import MAT_UCX, PREFIX_UCX

UCX_VIEWPORT_COLOR = (0.2, 1.0, 0.5, 0.5)
UCX_MATERIAL_COLOR = (0.0, 1.0, 0.0, 0.5)


def retrieve_or_create_ucx_material() -> bpy.types.Material:
    """Return the shared UCX collision preview material."""
    material = bpy.data.materials.get(MAT_UCX)
    if material is not None:
        return material

    material = bpy.data.materials.new(name=MAT_UCX)
    material.diffuse_color = UCX_MATERIAL_COLOR
    configure_alpha_blend_material(material)
    if hasattr(material, "use_backface_culling"):
        material.use_backface_culling = True

    principled_node = material.node_tree.nodes.get("Principled BSDF")
    if principled_node is not None:
        principled_node.inputs["Base Color"].default_value = UCX_MATERIAL_COLOR
        principled_node.inputs["Alpha"].default_value = 0.5
        principled_node.inputs["Roughness"].default_value = 0.3
    return material


def setup_ucx_on_obj(obj: bpy.types.Object) -> None:
    """Apply UCX naming, viewport color, and material to a mesh object."""
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if obj.type != "MESH":
        return

    if not obj.name.startswith(PREFIX_UCX):
        obj.name = PREFIX_UCX + obj.name

    obj.color = UCX_VIEWPORT_COLOR
    ucx_material = retrieve_or_create_ucx_material()

    if not obj.material_slots:
        bpy.ops.object.material_slot_add()

    for slot in obj.material_slots:
        slot.material = ucx_material

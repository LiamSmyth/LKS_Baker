"""Resolve material displacement sources and bake them into mesh geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import bpy
from mathutils import Vector

from .mesh_helpers import apply_triangulate_modifier
from .mesh_mode_helpers import preserve_mesh_mode

_VERT_GUARD_THRESHOLD = 50_000_000
_SUBDIV_ANCHORS: tuple[tuple[float, int], ...] = (
    (0.0, 0),
    (12.0, 2),
    (50.0, 4),
)
_TEMP_SUBSURF_NAME = "LKS_DispSubsurf"
_TEMP_DISPLACE_NAME = "LKS_DispDisplace"
_TEMP_TRIANGULATE_NAME = "LKS_DispTriangulate"
_TEMP_DECIMATE_NAME = "LKS_DispDecimate"
_DECIMATION_WEIGHT_GROUP = "DecimationWeight"


@dataclass
class DisplacementSource:
    """Scalar height displacement resolved from a material node tree."""

    image: bpy.types.Image
    scale: float
    midlevel: float
    is_vector: bool = False
    colorspace: str = ""


@dataclass
class DisplacementApplyResult:
    """Per-object outcome from apply_material_displacement_to_object."""

    success: bool
    vert_count_before: int = 0
    vert_count_after: int = 0
    bbox_z_delta: float = 0.0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def detail_percent_to_ppv(detail_percent: float) -> int:
    """Map detail percent to pixels-per-vertex (1 = pixel perfect)."""
    detail = max(0.0, min(100.0, detail_percent))
    if detail >= 100.0:
        return 1
    return max(1, round(256 ** ((100.0 - detail) / 100.0)))


def detail_percent_to_subdiv_levels(
    detail_percent: float,
    *,
    tex_res: int = 512,
) -> int:
    """Map detail percent to added Catmull-Clark subsurf levels."""
    detail = max(0.0, min(100.0, detail_percent))
    if detail <= 0.0:
        return 0
    if detail >= 100.0:
        return min(6, max(1, math.ceil(math.log2(max(tex_res, 2) / 2.0))))

    prev_pct, prev_levels = _SUBDIV_ANCHORS[0]
    for pct, levels in _SUBDIV_ANCHORS[1:]:
        if detail <= pct:
            if pct == prev_pct:
                return levels
            t = (detail - prev_pct) / (pct - prev_pct)
            return max(0, round(prev_levels + t * (levels - prev_levels)))
        prev_pct, prev_levels = pct, levels

    return _SUBDIV_ANCHORS[-1][1]


def predict_vertices_after_subsurf(vert_count: int, subdiv_levels: int) -> int:
    """Rough upper-bound vertex estimate after Catmull-Clark subdiv levels."""
    if subdiv_levels <= 0 or vert_count <= 0:
        return vert_count
    return vert_count * (4 ** subdiv_levels)


def resolve_material_displacement(
    mat: bpy.types.Material | None,
) -> DisplacementSource | None:
    """Walk a material node tree and return scalar displacement source data."""
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return None

    if getattr(mat, "displacement_method", None) == "BUMP":
        return None

    nodes = mat.node_tree.nodes
    output = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)

    candidates: list[bpy.types.NodeSocket] = []
    if output is not None:
        sock = output.inputs.get("Displacement")
        if sock is not None and sock.is_linked:
            candidates.append(sock)
    if principled is not None:
        sock = principled.inputs.get("Displacement")
        if sock is not None and sock.is_linked:
            candidates.append(sock)

    for sock in candidates:
        source = _resolve_from_displacement_socket(sock)
        if source is not None:
            return source

    for node in nodes:
        if node.type != "DISPLACEMENT":
            continue
        source = _resolve_from_displacement_node(node)
        if source is not None:
            return source

    return None


def apply_material_displacement_to_objects(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    *,
    detail_percent: float = 12.0,
    material_slot: int = -1,
    confirm_high_detail: bool = False,
    use_decimate: bool = True,
    target_polycount: int = 10000,
) -> list[DisplacementApplyResult]:
    """Apply material displacement to each mesh object in ``objects``."""
    results: list[DisplacementApplyResult] = []
    with preserve_mesh_mode(context):
        for obj in objects:
            if obj.type != "MESH":
                continue
            results.append(
                apply_material_displacement_to_object(
                    context,
                    obj,
                    detail_percent=detail_percent,
                    material_slot=material_slot,
                    confirm_high_detail=confirm_high_detail,
                    use_decimate=use_decimate,
                    target_polycount=target_polycount,
                )
            )
    return results


def apply_material_displacement_to_object(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    detail_percent: float = 12.0,
    material_slot: int = -1,
    confirm_high_detail: bool = False,
    use_decimate: bool = True,
    target_polycount: int = 10000,
) -> DisplacementApplyResult:
    """Evaluate modifier stack, densify, displace from material height, and apply."""
    if obj.type != "MESH" or obj.data is None:
        return DisplacementApplyResult(success=False, error="Object is not a mesh")

    mesh = obj.data
    uv_layer = _active_uv_layer_name(mesh)
    if uv_layer is None:
        return DisplacementApplyResult(success=False, error="Mesh has no UV layer")

    mat = _material_for_slot(obj, material_slot)
    if mat is None:
        return DisplacementApplyResult(success=False, error="No material on active slot")

    source = resolve_material_displacement(mat)
    if source is None:
        return DisplacementApplyResult(
            success=False,
            error="No displacement height image found in material",
        )

    warnings: list[str] = []
    if source.is_vector:
        warnings.append(
            f"Material '{mat.name}' uses vector displacement; scalar displace only"
        )
    if getattr(mat, "displacement_method", None) == "BUMP":
        warnings.append(f"Material '{mat.name}' is bump-only")

    tex_res = max(source.image.size[0], source.image.size[1], 1)
    subdiv_levels = detail_percent_to_subdiv_levels(detail_percent, tex_res=tex_res)
    vert_before = len(mesh.vertices)
    z_before = _world_bbox_z_extent(obj)

    predicted = predict_vertices_after_subsurf(vert_before, subdiv_levels)
    if detail_percent >= 100.0 and predicted > _VERT_GUARD_THRESHOLD and not confirm_high_detail:
        return DisplacementApplyResult(
            success=False,
            vert_count_before=vert_before,
            warnings=warnings,
            error=(
                f"Predicted {predicted:,} vertices exceeds guard "
                f"({_VERT_GUARD_THRESHOLD:,}); lower detail or confirm"
            ),
        )

    _prepare_object_mesh(context, obj)
    _assign_evaluated_base_mesh(context, obj)

    if subdiv_levels > 0:
        _add_and_apply_subsurf(context, obj, subdiv_levels)

    _add_and_apply_displace(
        context,
        obj,
        source=source,
        uv_layer=uv_layer,
    )

    if use_decimate:
        _apply_post_displacement_decimate(context, obj, target_polycount)

    vert_after = len(obj.data.vertices)
    z_after = _world_bbox_z_extent(obj)

    return DisplacementApplyResult(
        success=True,
        vert_count_before=vert_before,
        vert_count_after=vert_after,
        bbox_z_delta=abs(z_after - z_before),
        warnings=warnings,
    )


def _material_for_slot(
    obj: bpy.types.Object,
    material_slot: int,
) -> bpy.types.Material | None:
    if not obj.material_slots:
        return None
    index = obj.active_material_index if material_slot < 0 else material_slot
    if index < 0 or index >= len(obj.material_slots):
        return None
    return obj.material_slots[index].material


def _active_uv_layer_name(mesh: bpy.types.Mesh) -> str | None:
    if mesh.uv_layers.active is not None:
        return mesh.uv_layers.active.name
    if mesh.uv_layers:
        return mesh.uv_layers[0].name
    return None


def _world_bbox_z_extent(obj: bpy.types.Object) -> float:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    zs = [corner.z for corner in corners]
    return max(zs) - min(zs)


def _resolve_from_displacement_socket(
    socket: bpy.types.NodeSocket,
) -> DisplacementSource | None:
    if not socket.is_linked:
        return None
    from_node = socket.links[0].from_node
    if from_node.type == "DISPLACEMENT":
        return _resolve_from_displacement_node(from_node)
    if from_node.type == "TEX_IMAGE" and from_node.image is not None:
        return _source_from_image_node(from_node)
    if from_node.type == "VECTOR_DISPLACEMENT":
        image = _trace_image_from_socket(from_node.inputs.get("Vector"))
        if image is None:
            return None
        return DisplacementSource(
            image=image,
            scale=from_node.inputs["Scale"].default_value,
            midlevel=from_node.inputs["Midlevel"].default_value,
            is_vector=True,
            colorspace=image.colorspace_settings.name,
        )
    return None


def _resolve_from_displacement_node(
    node: bpy.types.ShaderNodeDisplacement,
) -> DisplacementSource | None:
    height = node.inputs.get("Height")
    if height is None:
        return None
    image = _trace_image_from_socket(height)
    if image is None:
        return None
    return DisplacementSource(
        image=image,
        scale=node.inputs["Scale"].default_value,
        midlevel=node.inputs["Midlevel"].default_value,
        is_vector=False,
        colorspace=image.colorspace_settings.name,
    )


def _source_from_image_node(
    node: bpy.types.ShaderNodeTexImage,
) -> DisplacementSource | None:
    if node.image is None:
        return None
    return DisplacementSource(
        image=node.image,
        scale=0.1,
        midlevel=0.5,
        is_vector=False,
        colorspace=node.image.colorspace_settings.name,
    )


def _trace_image_from_socket(
    socket: bpy.types.NodeSocket | None,
) -> bpy.types.Image | None:
    if socket is None or not socket.is_linked:
        return None
    from_node = socket.links[0].from_node
    if from_node.type == "TEX_IMAGE":
        return from_node.image
    if from_node.type == "DISPLACEMENT":
        return _trace_image_from_socket(from_node.inputs.get("Height"))
    return None


def _prepare_object_mesh(context: bpy.types.Context, obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj
    if obj.data and obj.data.users > 1:
        bpy.ops.object.make_single_user(
            type="SELECTED_OBJECTS",
            object=True,
            obdata=True,
            material=False,
            animation=False,
            obdata_animation=False,
        )


def _assign_evaluated_base_mesh(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> None:
    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    old_mesh = obj.data
    obj.data = new_mesh
    while obj.modifiers:
        obj.modifiers.remove(obj.modifiers[0])
    if old_mesh is not None and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)


def _add_and_apply_subsurf(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    levels: int,
) -> None:
    mod: bpy.types.SubsurfModifier = obj.modifiers.new(
        name=_TEMP_SUBSURF_NAME,
        type="SUBSURF",
    )
    mod.levels = levels
    mod.render_levels = levels
    _apply_modifier(context, obj, mod.name)


def _add_and_apply_displace(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    source: DisplacementSource,
    uv_layer: str,
) -> None:
    texture = _image_texture(source.image)
    mod: bpy.types.DisplaceModifier = obj.modifiers.new(
        name=_TEMP_DISPLACE_NAME,
        type="DISPLACE",
    )
    mod.texture = texture
    mod.texture_coords = "UV"
    mod.uv_layer = uv_layer
    mod.strength = source.scale
    mod.mid_level = source.midlevel
    _apply_modifier(context, obj, mod.name)


def _image_texture(image: bpy.types.Image) -> bpy.types.Texture:
    tex_name = f"LKS_Disp_{image.name}"
    texture = bpy.data.textures.get(tex_name)
    if texture is None:
        texture = bpy.data.textures.new(tex_name, type="IMAGE")
        texture.image = image
    elif texture.image != image:
        texture.image = image
    return texture


def _ensure_decimation_weight_group(obj: bpy.types.Object) -> str:
    """Create a uniform decimation weight vertex group when missing."""
    if _DECIMATION_WEIGHT_GROUP not in obj.vertex_groups:
        group = obj.vertex_groups.new(name=_DECIMATION_WEIGHT_GROUP)
        for vertex in obj.data.vertices:
            group.add([vertex.index], 1.0, "REPLACE")
    return _DECIMATION_WEIGHT_GROUP


def _apply_post_displacement_decimate(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    target_polycount: int,
) -> None:
    """Triangulate and collapse-decimate when above ``target_polycount``."""
    mesh = obj.data
    if mesh is None or target_polycount < 1:
        return

    face_count = len(mesh.polygons)
    if target_polycount >= face_count:
        return

    apply_triangulate_modifier(
        context,
        obj,
        modifier_name=_TEMP_TRIANGULATE_NAME,
    )

    face_count = len(mesh.polygons)
    if target_polycount >= face_count:
        return

    vg_name = _ensure_decimation_weight_group(obj)
    mod: bpy.types.DecimateModifier = obj.modifiers.new(
        name=_TEMP_DECIMATE_NAME,
        type="DECIMATE",
    )
    mod.vertex_group = vg_name
    mod.use_collapse_triangulate = True
    mod.ratio = min(1.0, target_polycount / face_count)
    _apply_modifier(context, obj, mod.name)


def _apply_modifier(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    modifier_name: str,
) -> None:
    try:
        with context.temp_override(
            object=obj,
            active_object=obj,
            selected_objects=[obj],
            selected_editable_objects=[obj],
            view_layer=context.view_layer,
        ):
            bpy.ops.object.modifier_apply(modifier=modifier_name)
    except RuntimeError as exc:
        if modifier_name in obj.modifiers:
            obj.modifiers.remove(obj.modifiers[modifier_name])
        raise RuntimeError(
            f"Could not apply modifier '{modifier_name}' on '{obj.name}': {exc}"
        ) from exc

"""Union mesh attributes across objects before join or export."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import bpy

from . import mesh_uv_helpers, mesh_vcol_helpers, object_helpers
from .geonodes_modifier_helpers import get_nodes_modifier_input
from .mesh_mode_helpers import edit_mode_for_ops
from .shading_helpers import (
    apply_smooth_by_angle,
    find_smooth_by_angle_modifier,
    set_mesh_shade_smooth,
    set_smooth_by_angle_ignore_sharps,
)

_GENERIC_ATTR_TYPES = frozenset({
    'FLOAT',
    'INT',
    'FLOAT_VECTOR',
    'FLOAT2',
    'BOOLEAN',
})
_COLOR_ATTR_TYPES = frozenset({'BYTE_COLOR', 'FLOAT_COLOR'})
_WHITE_COLOR = (1.0, 1.0, 1.0, 1.0)
_DEFAULT_SMOOTH_ANGLE = math.pi


@dataclass(frozen=True)
class ColorAttrSpec:
    name: str
    domain: str
    attr_type: str


@dataclass(frozen=True)
class GenericAttrSpec:
    name: str
    domain: str
    attr_type: str


@dataclass(frozen=True)
class MeshAttributeSchema:
    uv_layer_count: int
    uv_layer_names: tuple[str, ...]
    color_attributes: tuple[ColorAttrSpec, ...]
    generic_attributes: tuple[GenericAttrSpec, ...]
    requires_custom_normals: bool
    requires_smooth_faces: bool = False
    requires_smooth_by_angle: bool = False
    smooth_by_angle: float = _DEFAULT_SMOOTH_ANGLE
    requires_sharp_edges: bool = False

    def union_channel_labels(self) -> list[str]:
        """Human-readable list of attribute channels in this union schema."""
        channels: list[str] = []
        if self.uv_layer_count > 0:
            channels.append(f'uv_layers({self.uv_layer_count})')
        if self.color_attributes:
            names = ', '.join(spec.name for spec in self.color_attributes)
            channels.append(f'color_attributes({names})')
        if self.generic_attributes:
            names = ', '.join(spec.name for spec in self.generic_attributes)
            channels.append(f'generic_attributes({names})')
        if self.requires_custom_normals:
            channels.append('custom_split_normals')
        if self.requires_smooth_faces:
            channels.append('smooth_faces')
        if self.requires_sharp_edges:
            channels.append('sharp_edges')
        if self.requires_smooth_by_angle or self.requires_sharp_edges:
            angle_deg = math.degrees(self.smooth_by_angle)
            channels.append(f'smooth_by_angle({angle_deg:.0f}°)')
        return channels


@dataclass
class MeshAttributeSyncResult:
    mesh_count: int = 0
    uv_layers_added: int = 0
    color_attributes_added: int = 0
    generic_attributes_added: int = 0
    custom_normals_added: int = 0
    smooth_by_angle_added: int = 0
    union_channels: list[str] | None = None

    def attributes_synced(self) -> list[str]:
        """Channels present in the union schema for this sync run."""
        return list(self.union_channels or [])


def _resolve_uvset_count(meshes: list[bpy.types.Object], uvset_count: int | None) -> int:
    if uvset_count is not None:
        return max(uvset_count, 1)
    counts = [len(obj.data.uv_layers) for obj in meshes if obj.data is not None]
    return max(counts) if counts else 1


def _resolve_vcol_count(meshes: list[bpy.types.Object], vcol_count: int | None) -> int:
    if vcol_count is not None:
        return max(vcol_count, 0)
    counts = [len(obj.data.color_attributes) for obj in meshes if obj.data is not None]
    return max(counts) if counts else 0


def _valid_mesh_objects(meshes: list[bpy.types.Object]) -> list[bpy.types.Object]:
    return [
        obj for obj in object_helpers.filter_valid_objects(meshes)
        if obj.type == 'MESH' and obj.data is not None
    ]


def _mesh_has_sharp_edges(mesh: bpy.types.Mesh) -> bool:
    if len(mesh.edges) == 0:
        return False
    sharp = [False] * len(mesh.edges)
    mesh.edges.foreach_get('use_edge_sharp', sharp)
    return any(sharp)


def _mesh_has_smooth_faces(mesh: bpy.types.Mesh) -> bool:
    if len(mesh.polygons) == 0:
        return False
    smooth = [False] * len(mesh.polygons)
    mesh.polygons.foreach_get('use_smooth', smooth)
    return any(smooth)


def _read_smooth_by_angle(mod: bpy.types.Modifier) -> float | None:
    if mod.type != 'NODES' or mod.node_group is None:
        return None
    for item in mod.node_group.interface.items_tree:
        if item.item_type != 'SOCKET' or item.in_out != 'INPUT':
            continue
        if 'angle' not in item.name.lower():
            continue
        value = get_nodes_modifier_input(mod, item.identifier)
        if value is not None:
            return float(value)
    return None


def collect_meshes_from_selection_hierarchy(
    context: bpy.types.Context,
) -> list[bpy.types.Object]:
    """Mesh objects under each selected root, deduplicated."""
    seen: set[int] = set()
    meshes: list[bpy.types.Object] = []
    for root in object_helpers.context_selected_objects(context):
        for obj in object_helpers.collect_all_meshes_in_hierarchy(root):
            if obj.type != 'MESH' or obj.data is None:
                continue
            obj_id = id(obj)
            if obj_id in seen:
                continue
            seen.add(obj_id)
            meshes.append(obj)
    return meshes


def selection_has_mesh_attributes_to_sync(context: bpy.types.Context) -> bool:
    return bool(collect_meshes_from_selection_hierarchy(context))


def collect_mesh_attribute_schema(meshes: list[bpy.types.Object]) -> MeshAttributeSchema:
    """Union UV layers, color attributes, generic attrs, normals, and shading state."""
    valid_meshes = _valid_mesh_objects(meshes)
    uv_layer_count = 0
    uv_layer_names: tuple[str, ...] = ()
    color_specs: dict[str, ColorAttrSpec] = {}
    generic_specs: dict[tuple[str, str, str], GenericAttrSpec] = {}
    requires_custom_normals = False
    requires_smooth_faces = False
    requires_smooth_by_angle = False
    requires_sharp_edges = False
    smooth_by_angle = _DEFAULT_SMOOTH_ANGLE

    for obj in valid_meshes:
        mesh: bpy.types.Mesh = obj.data
        uv_count = len(mesh.uv_layers)
        if uv_count > uv_layer_count:
            uv_layer_count = uv_count
            uv_layer_names = tuple(uv.name for uv in mesh.uv_layers)

        requires_custom_normals = requires_custom_normals or mesh.has_custom_normals
        requires_smooth_faces = requires_smooth_faces or _mesh_has_smooth_faces(mesh)
        if _mesh_has_sharp_edges(mesh):
            requires_sharp_edges = True

        sba_mod = find_smooth_by_angle_modifier(obj)
        if sba_mod is not None:
            requires_smooth_by_angle = True
            angle = _read_smooth_by_angle(sba_mod)
            if angle is not None:
                smooth_by_angle = max(smooth_by_angle, angle)

        color_names = {attr.name for attr in mesh.color_attributes}
        for attr in mesh.color_attributes:
            color_specs.setdefault(
                attr.name,
                ColorAttrSpec(
                    name=attr.name,
                    domain=attr.domain,
                    attr_type=attr.data_type,
                ),
            )

        for attr in mesh.attributes:
            if attr.name in color_names:
                continue
            if attr.name.startswith('.'):
                continue
            if attr.data_type in _COLOR_ATTR_TYPES:
                continue
            if attr.data_type not in _GENERIC_ATTR_TYPES:
                continue
            key = (attr.name, attr.domain, attr.data_type)
            generic_specs.setdefault(
                key,
                GenericAttrSpec(
                    name=attr.name,
                    domain=attr.domain,
                    attr_type=attr.data_type,
                ),
            )

    if requires_sharp_edges and not requires_smooth_by_angle:
        requires_smooth_by_angle = True

    return MeshAttributeSchema(
        uv_layer_count=max(uv_layer_count, 1),
        uv_layer_names=uv_layer_names,
        color_attributes=tuple(color_specs.values()),
        generic_attributes=tuple(generic_specs.values()),
        requires_custom_normals=requires_custom_normals,
        requires_smooth_faces=requires_smooth_faces,
        requires_smooth_by_angle=requires_smooth_by_angle,
        smooth_by_angle=smooth_by_angle,
        requires_sharp_edges=requires_sharp_edges,
    )


def _resolve_schema_with_overrides(
    schema: MeshAttributeSchema,
    *,
    uvset_count: int | None = None,
) -> MeshAttributeSchema:
    if uvset_count is None:
        return schema
    return replace(
        schema,
        uv_layer_count=max(uvset_count, schema.uv_layer_count, 1),
    )


def _ensure_single_user_mesh(context: bpy.types.Context, obj: bpy.types.Object) -> None:
    if obj.type != 'MESH' or obj.data is None or obj.data.users <= 1:
        return
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj
    bpy.ops.object.make_single_user(
        type='SELECTED_OBJECTS',
        object=True,
        obdata=True,
        material=False,
        animation=False,
        obdata_animation=False,
    )


def _fill_color_attribute_white(mesh: bpy.types.Mesh, name: str) -> None:
    attr = mesh.attributes.get(name)
    if attr is None:
        return
    data = mesh.attributes[name].data
    for elem in data:
        elem.color = _WHITE_COLOR


def _fill_generic_attribute_default(mesh: bpy.types.Mesh, spec: GenericAttrSpec) -> None:
    attr = mesh.attributes.get(spec.name)
    if attr is None:
        return
    data = attr.data
    count = len(data)
    if count == 0:
        return

    if spec.attr_type == 'FLOAT':
        data.foreach_set('value', [0.0] * count)
    elif spec.attr_type == 'INT':
        data.foreach_set('value', [0] * count)
    elif spec.attr_type == 'BOOLEAN':
        data.foreach_set('value', [False] * count)
    elif spec.attr_type == 'FLOAT_VECTOR':
        data.foreach_set('vector', [0.0, 0.0, 0.0] * count)
    elif spec.attr_type == 'FLOAT2':
        data.foreach_set('vector', [0.0, 0.0] * count)


def _sync_uv_layers(mesh: bpy.types.Mesh, uv_layer_count: int) -> int:
    result = mesh_uv_helpers.consolidate_uv_layers_on_mesh(
        mesh,
        uv_layer_count,
        active_index=0,
    )
    return result.added


def _sync_vcol_count(mesh: bpy.types.Mesh, vcol_count: int) -> None:
    mesh_vcol_helpers.set_mesh_vcol_count(mesh, vcol_count)
    mesh_vcol_helpers.name_vcols_on_mesh(mesh)


def _sync_color_attributes_by_schema(
    mesh: bpy.types.Mesh,
    color_specs: tuple[ColorAttrSpec, ...],
) -> int:
    added = 0
    for spec in color_specs:
        if mesh.color_attributes.get(spec.name) is not None:
            continue
        mesh_vcol_helpers.get_or_create_color_attribute(
            mesh,
            spec.name,
            domain=spec.domain,
            attr_type=spec.attr_type,
        )
        _fill_color_attribute_white(mesh, spec.name)
        added += 1
    return added


def _sync_generic_attributes_by_schema(
    mesh: bpy.types.Mesh,
    generic_specs: tuple[GenericAttrSpec, ...],
) -> int:
    added = 0
    for spec in generic_specs:
        if spec.name in mesh.attributes:
            continue
        mesh.attributes.new(
            name=spec.name,
            type=spec.attr_type,
            domain=spec.domain,
        )
        _fill_generic_attribute_default(mesh, spec)
        added += 1
    return added


def _ensure_custom_split_normals(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
) -> bool:
    """Add custom split normals initialized from evaluated corner normals."""
    if mesh.has_custom_normals:
        return False

    mesh.update()
    if len(mesh.corner_normals) > 0:
        normals = [tuple(cn.vector) for cn in mesh.corner_normals]
        mesh.normals_split_custom_set(normals)
        if mesh.has_custom_normals:
            return True

    with edit_mode_for_ops(context, obj):
        if bpy.ops.mesh.customdata_custom_splitnormals_add.poll():
            bpy.ops.mesh.customdata_custom_splitnormals_add()
    return mesh.has_custom_normals


def _sync_shading_state(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    schema: MeshAttributeSchema,
) -> int:
    """Ensure smooth-by-angle / smooth shading matches the union schema."""
    needs_sba = (
        schema.requires_smooth_by_angle
        or schema.requires_sharp_edges
        or schema.requires_custom_normals
    )
    smooth_by_angle_added = 0
    if not needs_sba:
        set_mesh_shade_smooth(obj)
        return smooth_by_angle_added

    had_sba = find_smooth_by_angle_modifier(obj) is not None
    smooth_mod = apply_smooth_by_angle(context, obj, schema.smooth_by_angle)
    if smooth_mod is None:
        set_mesh_shade_smooth(obj)
        return smooth_by_angle_added

    if schema.requires_sharp_edges or schema.requires_custom_normals:
        set_smooth_by_angle_ignore_sharps(smooth_mod, False)
    smooth_by_angle_added = 0 if had_sba else 1

    if schema.requires_smooth_faces:
        set_mesh_shade_smooth(obj)
    return smooth_by_angle_added


def _sync_custom_normals_and_shading(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    schema: MeshAttributeSchema,
) -> tuple[int, int]:
    """Promote shading and custom normals without overwriting existing data."""
    mesh: bpy.types.Mesh = obj.data
    smooth_by_angle_added = _sync_shading_state(context, obj, schema)

    custom_normals_added = 0
    if schema.requires_custom_normals and not mesh.has_custom_normals:
        if _ensure_custom_split_normals(context, obj, mesh):
            custom_normals_added = 1

    return custom_normals_added, smooth_by_angle_added


def sync_mesh_attributes(
    context: bpy.types.Context,
    meshes: list[bpy.types.Object],
    *,
    schema: MeshAttributeSchema | None = None,
    uvset_count: int | None = None,
    vcol_count: int | None = None,
) -> MeshAttributeSyncResult:
    """Union missing UV layers, color attrs, generic attrs, normals, and shading."""
    valid_meshes = _valid_mesh_objects(meshes)
    if not valid_meshes:
        return MeshAttributeSyncResult()

    resolved_schema = schema or collect_mesh_attribute_schema(valid_meshes)
    resolved_schema = _resolve_schema_with_overrides(
        resolved_schema,
        uvset_count=uvset_count,
    )

    min_vcol_count = len(resolved_schema.color_attributes)
    if vcol_count is not None:
        min_vcol_count = max(min_vcol_count, vcol_count)

    result = MeshAttributeSyncResult(
        mesh_count=len(valid_meshes),
        union_channels=resolved_schema.union_channel_labels(),
    )

    for obj in valid_meshes:
        _ensure_single_user_mesh(context, obj)
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        mesh: bpy.types.Mesh = obj.data
        result.uv_layers_added += _sync_uv_layers(mesh, resolved_schema.uv_layer_count)
        _sync_vcol_count(mesh, min_vcol_count)
        result.color_attributes_added += _sync_color_attributes_by_schema(
            mesh,
            resolved_schema.color_attributes,
        )
        result.generic_attributes_added += _sync_generic_attributes_by_schema(
            mesh,
            resolved_schema.generic_attributes,
        )
        normals_added, sba_added = _sync_custom_normals_and_shading(
            context,
            obj,
            resolved_schema,
        )
        result.custom_normals_added += normals_added
        result.smooth_by_angle_added += sba_added

    return result


def sync_mesh_attributes_for_join(
    context: bpy.types.Context,
    meshes: list[bpy.types.Object],
    *,
    uvset_count: int | None = None,
    vcol_count: int | None = None,
) -> MeshAttributeSyncResult:
    """Full schema union for join/export (optional UV/vcol count floors)."""
    return sync_mesh_attributes(
        context,
        meshes,
        uvset_count=uvset_count,
        vcol_count=vcol_count,
    )

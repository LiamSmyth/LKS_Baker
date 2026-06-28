from __future__ import annotations

from dataclasses import dataclass
from typing import List

import bpy

from .lks_constants import BAKE_UV_LAYER_COUNT, DEFAULT_UV_LAYER_NAMES


def default_uv_layer_name(
    index: int,
    names: tuple[str, ...] | None = None,
) -> str:
    """Canonical UV layer name for ``index`` (defaults: UVMap, Lightmap, Trim, UVMap_03, …)."""
    layer_names = names if names is not None else DEFAULT_UV_LAYER_NAMES
    if index < len(layer_names):
        return layer_names[index]
    return f'UVMap_{index:02d}'


@dataclass
class ConsolidateUVLayersResult:
    added: int = 0
    removed: int = 0


def consolidate_uv_layers_on_mesh(
    mesh: bpy.types.Mesh,
    count: int,
    *,
    names: tuple[str, ...] | None = None,
    active_index: int = 0,
) -> ConsolidateUVLayersResult:
    """Force UV layer count, rename by index, and set the active layer."""
    before = len(mesh.uv_layers)
    reset_mesh_uv_maps_names(mesh)
    set_uvmap_count_on_mesh(mesh, count, prune=True)
    after = len(mesh.uv_layers)
    name_uvmaps_on_mesh(mesh, names)
    if mesh.uv_layers:
        mesh.uv_layers.active_index = max(0, min(active_index, len(mesh.uv_layers) - 1))
    return ConsolidateUVLayersResult(
        added=max(after - before, 0),
        removed=max(before - after, 0),
    )


def consolidate_uv_layers_on_objects(
    objects: list[bpy.types.Object],
    count: int,
    *,
    names: tuple[str, ...] | None = None,
    active_index: int = 0,
) -> ConsolidateUVLayersResult:
    """Apply :func:`consolidate_uv_layers_on_mesh` to each mesh object."""
    total = ConsolidateUVLayersResult()
    for obj in objects:
        if obj.type != 'MESH' or obj.data is None:
            continue
        result = consolidate_uv_layers_on_mesh(
            obj.data,
            count,
            names=names,
            active_index=active_index,
        )
        total.added += result.added
        total.removed += result.removed
    return total


def consolidate_uv_layers_for_bake(
    objects: list[bpy.types.Object],
    *,
    count: int = BAKE_UV_LAYER_COUNT,
) -> ConsolidateUVLayersResult:
    """Bake prep: one canonical ``UVMap`` layer on every target mesh."""
    return consolidate_uv_layers_on_objects(objects, count, active_index=0)


def reset_mesh_uv_maps_names(mesh: bpy.types.Mesh) -> None:
    """
    Resets the names of all UV maps in the given object's mesh to 'UVMap'.

    Args:
    - obj: The object whose UV maps' names should be reset.

    Returns:
    - None
    """

    if not mesh.uv_layers:
        return

    i: int = 0
    for uv_map in mesh.uv_layers:
        uv_map.name = f'UVMap_{str(i).zfill(2)}'
        i += 1


def name_uvmaps_on_mesh(
    mesh: bpy.types.Mesh,
    names: tuple[str, ...] | None = None,
) -> None:
    """Rename UV layers by index using :func:`default_uv_layer_name`."""
    for index, uv_map in enumerate(mesh.uv_layers):
        uv_map.name = default_uv_layer_name(index, names)


def set_uvmap_count_on_mesh(mesh: bpy.types.Mesh, count: int, prune=True) -> None:
    """
    Sets the number of UV maps on the given object's mesh to the given count.

    Args:
    - obj: The object whose UV maps' count should be set.
    - count: The number of UV maps the object's mesh should have.
    - prune: Whether to remove UV maps if the object's mesh has more than the given count. Defaults to True.

    Returns:
    - None
    """

    # minimum count is 0, max count is 10
    count = max(0, count)
    count = min(count, 10)

    # if not mesh.uv_layers:
    #     return

    num_uv_maps = len(mesh.uv_layers)

    if num_uv_maps < count:
        for _ in range(count - num_uv_maps):
            mesh.uv_layers.new()

    if prune:
        if num_uv_maps > count:
            for _ in range(num_uv_maps - count):
                mesh.uv_layers.remove(mesh.uv_layers[-1])


def pack_mesh_uvs_on_specified_index(uv_index: int = 1, margin=0.001, layout=True, pack_individually=False):
    """
    Packs the UVs of selected meshes onto a specified UV map index.

    Args:
        uv_index (int): The index of the UV map to pack the UVs onto. Defaults to 1.
        margin (float): The margin to use when packing the UVs. Defaults to 0.001.
        layout (bool): Whether to layout the UVs before packing. Defaults to True.
        pack_individually (bool): Whether to pack each mesh individually. Defaults to True.
    """
    editmode_toggled = False

    # Check if in object mode
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.editmode_toggle()
        editmode_toggled = True

    # clamp inputs
    uv_index = max(0, uv_index)
    uv_index = min(uv_index, 9)  # object can have up to 10 uv maps

    # Cache original selection
    original_selection = bpy.context.selected_objects.copy()

    # collect meshes from selection and iterate through them
    mesh_objects: List[bpy.types.Mesh] = []
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            mesh_objects.append(obj)

    # Clear selection
    bpy.ops.object.select_all(action='DESELECT')

    # Prepare meshes for UV layout
    for obj in mesh_objects:
        # Ensure there is the correct number of uv sets so that we can layout on the specified index
        set_uvmap_count_on_mesh(obj.data, uv_index + 1, prune=False)
        obj.data.uv_layers.active_index = uv_index

    # Reset original selection & active object
    def reset_selection():
        for objects in original_selection:
            objects.select_set(True)
        bpy.context.view_layer.objects.active = original_selection[0]

    reset_selection()

    # Layout and pack UVs on one object
    def layout_and_pack_uvs():
        bpy.ops.object.editmode_toggle()
        bpy.ops.mesh.select_all(action='SELECT')
        if layout:
            bpy.ops.uv.smart_project()
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.pin(clear=True)
        bpy.ops.uv.pack_islands(margin=margin)
        bpy.ops.object.editmode_toggle()

    # Pack UVs
    if not pack_individually:
        layout_and_pack_uvs()
    else:
        for obj in mesh_objects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            layout_and_pack_uvs()
            bpy.ops.object.select_all(action='DESELECT')

    reset_selection()

    # Toggle edit mode back if it was toggled
    if editmode_toggled:
        bpy.ops.object.editmode_toggle()


def set_active_uv_index_on_selection(index: bool = 0):

    meshes = []
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            meshes.append(obj)

    for mesh_obj in meshes:
        mesh: bpy.types.Mesh = mesh_obj.data
        mesh.uv_layers
        if not mesh.uv_layers or len(mesh.uv_layers) < index:
            continue

        mesh.uv_layers.active_index = index


def mesh_has_mirror_modifier(obj: bpy.types.Object) -> bool:
    """True when the object has at least one Mirror modifier."""
    if obj.type != 'MESH':
        return False
    return any(mod.type == 'MIRROR' for mod in obj.modifiers)


def collect_subtree_meshes_with_mirror(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    """Mesh objects under roots that have at least one Mirror modifier."""
    from .deep_geometry_phase_helpers import collect_subtree_meshes

    return [
        obj for obj in collect_subtree_meshes(context, roots)
        if mesh_has_mirror_modifier(obj)
    ]


def apply_mirror_uv_unstack_offset(
    obj: bpy.types.Object,
    *,
    u_offset_start: int = 1,
) -> int:
    """Assign whole-number Mirror ``offset_u`` values so stacked mirrors do not overlap UVs.

    Each Mirror modifier in stack order receives a cumulative integer U offset
    (1, 2, 3, …). Matches export/bake prep and ``lks_add_uv_offset_to_mirrors``.
    Returns the number of mirror modifiers updated.
    """
    if obj.type != 'MESH':
        return 0

    updated = 0
    mirror_index = u_offset_start
    for modifier in obj.modifiers:
        if modifier.type != 'MIRROR':
            continue
        mirror_mod: bpy.types.MirrorModifier = modifier
        mirror_mod.use_mirror_u = False
        mirror_mod.use_mirror_v = False
        mirror_mod.use_mirror_udim = False
        mirror_mod.offset_u = float(mirror_index)
        mirror_mod.use_mirror_merge = False
        mirror_mod.use_clip = True
        mirror_index += 1
        updated += 1
    return updated

"""Helpers for LKS-managed Quad Remesh subset workflows.

These utilities are intentionally Blender-context aware because the vendor
Quad Remesher integration relies on active object, selection state, and mode.
The helpers here cover the low-level primitives needed before the higher-level
wrapper orchestration is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import bmesh
import bpy

from . import patch_helpers
from ..lks_object_properties import (
    is_quadremesh_temp_object,
    mark_quadremesh_temp_object,
)
from .lks_constants import ATTR_SCULPT_FACE_SET

WHOLE_OBJECT_SCOPE = 'WHOLE_OBJECT'
SELECTED_FACES_SCOPE = 'SELECTED_FACES'
ACTIVE_FACE_SET_SCOPE = 'ACTIVE_FACE_SET'
VISIBLE_SCULPT_FACES_SCOPE = 'VISIBLE_SCULPT_FACES'

LKS_QUADREMESH_TEMP_OBJECT_PROP = 'lks_quadremesh_temp_object'
LKS_QUADREMESH_TEMP_SOURCE_PROP = 'lks_quadremesh_temp_source'
LKS_QUADREMESH_TEMP_NAME_PREFIX = 'LKS_QR_TEMP__'
LKS_QUADREMESH_SOURCE_FACE_INDEX_ATTR = 'lks_quadremesh_source_face_index'

_MODE_SET_BY_CONTEXT_MODE = {
    'OBJECT': 'OBJECT',
    'EDIT_MESH': 'EDIT',
    'SCULPT': 'SCULPT',
    'VERTEX_PAINT': 'VERTEX_PAINT',
    'WEIGHT_PAINT': 'WEIGHT_PAINT',
    'TEXTURE_PAINT': 'TEXTURE_PAINT',
}


@dataclass(slots=True)
class QuadRemeshUserState:
    """Captured user-facing selection / mode state for later restoration."""

    active_object_name: str | None
    selected_object_names: tuple[str, ...]
    mode: str = 'OBJECT'
    selected_face_indices_by_object: dict[str, tuple[int, ...]] = field(
        default_factory=dict)


@dataclass(slots=True)
class QuadRemeshSubsetSession:
    """Runtime state for an active Quad Remesh subset wrapper session."""

    scope: str
    source_object_name: str
    proxy_object_name: str
    preexisting_object_names: frozenset[str]
    user_state: QuadRemeshUserState


def _get_source_collection(
    context: bpy.types.Context,
    source_obj: bpy.types.Object,
) -> bpy.types.Collection:
    if source_obj.users_collection:
        return source_obj.users_collection[0]
    if context.collection is not None:
        return context.collection
    return context.scene.collection


def _copy_material_slots(
    source_obj: bpy.types.Object,
    target_mesh: bpy.types.Mesh,
) -> None:
    for material in source_obj.data.materials:
        target_mesh.materials.append(material)


def get_session_source_object(
    context: bpy.types.Context,
    session: QuadRemeshSubsetSession | None,
) -> bpy.types.Object | None:
    if session is None:
        return None
    return context.scene.objects.get(session.source_object_name)


def get_session_proxy_object(
    context: bpy.types.Context,
    session: QuadRemeshSubsetSession | None,
) -> bpy.types.Object | None:
    if session is None:
        return None
    return bpy.data.objects.get(session.proxy_object_name)


def create_subset_session(
    scope: str,
    source_obj: bpy.types.Object,
    proxy_obj: bpy.types.Object,
    *,
    preexisting_object_names: set[str],
    user_state: QuadRemeshUserState,
) -> QuadRemeshSubsetSession:
    """Create a tracked subset remesh session descriptor."""
    return QuadRemeshSubsetSession(
        scope=scope,
        source_object_name=source_obj.name,
        proxy_object_name=proxy_obj.name,
        preexisting_object_names=frozenset(preexisting_object_names),
        user_state=user_state,
    )


def select_only_object(
    context: bpy.types.Context,
    target_obj: bpy.types.Object,
) -> None:
    """Make *target_obj* the sole selected active object."""
    for obj in context.scene.objects:
        obj.select_set(False)
    target_obj.select_set(True)
    context.view_layer.objects.active = target_obj


def _write_face_int_attribute(
    mesh: bpy.types.Mesh,
    attr_name: str,
    values,
) -> None:
    if attr_name not in mesh.attributes:
        mesh.attributes.new(name=attr_name, type='INT', domain='FACE')
    attr = mesh.attributes[attr_name]
    data = patch_helpers.np.asarray(values, dtype=patch_helpers.np.int32)
    attr.data.foreach_set('value', data)


def _read_face_int_attribute(
    mesh: bpy.types.Mesh,
    attr_name: str,
) -> object | None:
    if attr_name not in mesh.attributes:
        return None
    values = patch_helpers.np.empty(
        len(mesh.polygons), dtype=patch_helpers.np.int32)
    mesh.attributes[attr_name].data.foreach_get('value', values)
    return values


def _read_face_bool_attribute(
    mesh: bpy.types.Mesh,
    attr_name: str,
):
    if attr_name not in mesh.attributes:
        return None
    values = patch_helpers.np.empty(
        len(mesh.polygons),
        dtype=patch_helpers.np.bool_,
    )
    mesh.attributes[attr_name].data.foreach_get('value', values)
    return values


def _compute_sharp_region_ids(mesh: bpy.types.Mesh):
    """Return per-face region IDs split by sharp edges."""
    region_ids = patch_helpers.np.full(
        len(mesh.polygons),
        -1,
        dtype=patch_helpers.np.int32,
    )
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        next_region_id = 0

        for face in bm.faces:
            if region_ids[face.index] != -1:
                continue

            region_ids[face.index] = next_region_id
            stack = [face]
            while stack:
                current_face = stack.pop()
                for edge in current_face.edges:
                    if not edge.smooth:
                        continue
                    for linked_face in edge.link_faces:
                        if linked_face.index == current_face.index:
                            continue
                        if region_ids[linked_face.index] != -1:
                            continue
                        region_ids[linked_face.index] = next_region_id
                        stack.append(linked_face)

            next_region_id += 1
    finally:
        bm.free()

    return region_ids


def _delete_bmesh_unselected_faces(bm: bmesh.types.BMesh) -> None:
    bm.faces.ensure_lookup_table()
    faces_to_delete = [face for face in bm.faces if not face.select]
    if faces_to_delete:
        bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES')


def _restore_edit_face_selection(
    obj: bpy.types.Object,
    face_indices: tuple[int, ...],
) -> None:
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        face.select = False
    for face_index in face_indices:
        if 0 <= face_index < len(bm.faces):
            bm.faces[face_index].select = True
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def capture_user_state(context: bpy.types.Context) -> QuadRemeshUserState:
    """Capture active object, selection, mode, and edit-face selection state."""
    active_obj = context.active_object
    state = QuadRemeshUserState(
        active_object_name=active_obj.name if active_obj is not None else None,
        selected_object_names=tuple(
            obj.name for obj in context.selected_objects),
        mode=context.mode,
    )

    if active_obj is not None and active_obj.type == 'MESH' and context.mode == 'EDIT_MESH':
        bm = bmesh.from_edit_mesh(active_obj.data)
        bm.faces.ensure_lookup_table()
        state.selected_face_indices_by_object[active_obj.name] = tuple(
            face.index for face in bm.faces if face.select
        )

    return state


def restore_user_state(
    context: bpy.types.Context,
    state: QuadRemeshUserState,
) -> None:
    """Best-effort restoration of object selection and mode state."""
    active_obj = context.active_object
    if active_obj is not None and active_obj.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass

    for obj in context.view_layer.objects:
        obj.select_set(False)

    selected_objects: list[bpy.types.Object] = []
    for obj_name in state.selected_object_names:
        obj = context.scene.objects.get(obj_name)
        if obj is None:
            continue
        obj.select_set(True)
        selected_objects.append(obj)

    active_restore_obj = None
    if state.active_object_name is not None:
        active_restore_obj = context.scene.objects.get(
            state.active_object_name)
    elif selected_objects:
        active_restore_obj = selected_objects[0]

    if active_restore_obj is not None:
        context.view_layer.objects.active = active_restore_obj

    desired_mode = _MODE_SET_BY_CONTEXT_MODE.get(state.mode)
    if active_restore_obj is None or desired_mode is None:
        return

    try:
        bpy.ops.object.mode_set(mode=desired_mode)
    except RuntimeError:
        return

    if desired_mode == 'EDIT':
        face_indices = state.selected_face_indices_by_object.get(
            active_restore_obj.name, ())
        if active_restore_obj.type == 'MESH' and face_indices:
            _restore_edit_face_selection(active_restore_obj, face_indices)


def has_selected_faces(obj: bpy.types.Object) -> bool:
    """Return True when an edit-mode mesh object has any selected faces."""
    if obj is None or obj.type != 'MESH' or obj.mode != 'EDIT':
        return False

    bm = bmesh.from_edit_mesh(obj.data)
    return any(face.select for face in bm.faces)


def has_visible_sculpt_subset(obj: bpy.types.Object) -> bool:
    """Return True when sculpt mode has hidden faces and a visible subset remains."""
    if obj is None or obj.type != 'MESH' or obj.mode != 'SCULPT':
        return False

    hidden_faces = _read_face_bool_attribute(obj.data, '.hide_poly')
    if hidden_faces is None or len(hidden_faces) == 0:
        return False

    has_hidden_faces = bool(hidden_faces.any())
    has_visible_faces = bool((~hidden_faces).any())
    return has_hidden_faces and has_visible_faces


def detect_remesh_scope(context: bpy.types.Context) -> str:
    """Infer the desired remesh scope from the current interaction context."""
    active_obj = context.active_object
    if active_obj is None or active_obj.type != 'MESH':
        return WHOLE_OBJECT_SCOPE

    if context.mode == 'EDIT_MESH' and has_selected_faces(active_obj):
        return SELECTED_FACES_SCOPE

    if context.mode == 'SCULPT' and has_visible_sculpt_subset(active_obj):
        return VISIBLE_SCULPT_FACES_SCOPE

    if context.mode == 'SCULPT' and ATTR_SCULPT_FACE_SET in active_obj.data.attributes:
        return ACTIVE_FACE_SET_SCOPE

    return WHOLE_OBJECT_SCOPE


def mark_as_temp_quadremesh_object(
    obj: bpy.types.Object,
    source_obj: bpy.types.Object,
) -> bpy.types.Object:
    """Tag a wrapper-owned temporary object for later discovery and cleanup."""
    return mark_quadremesh_temp_object(obj, source_obj)


def is_temp_quadremesh_object(obj: bpy.types.Object | None) -> bool:
    """Return True when *obj* is an LKS-created temporary remesh proxy."""
    return is_quadremesh_temp_object(obj)


def create_temp_object_from_source(
    context: bpy.types.Context,
    source_obj: bpy.types.Object,
) -> bpy.types.Object:
    """Create a full-mesh temporary proxy object from *source_obj*."""
    proxy_mesh = source_obj.data.copy()
    proxy_obj = bpy.data.objects.new(
        name=f"{LKS_QUADREMESH_TEMP_NAME_PREFIX}{source_obj.name}",
        object_data=proxy_mesh,
    )
    proxy_obj.matrix_world = source_obj.matrix_world.copy()
    _copy_material_slots(source_obj, proxy_mesh)
    _write_face_int_attribute(
        proxy_mesh,
        LKS_QUADREMESH_SOURCE_FACE_INDEX_ATTR,
        patch_helpers.np.arange(len(proxy_mesh.polygons),
                                dtype=patch_helpers.np.int32),
    )
    _get_source_collection(context, source_obj).objects.link(proxy_obj)
    return mark_as_temp_quadremesh_object(proxy_obj, source_obj)


def create_selected_faces_proxy_object(
    context: bpy.types.Context,
    source_obj: bpy.types.Object,
) -> bpy.types.Object:
    """Create a temporary proxy object containing only the selected faces."""
    if source_obj.type != 'MESH' or source_obj.mode != 'EDIT':
        raise RuntimeError(
            'Selected-face proxy creation requires an edit-mode mesh object.')

    bm = bmesh.from_edit_mesh(source_obj.data)
    if not any(face.select for face in bm.faces):
        raise RuntimeError(
            'No selected faces available for Quad Remesh subset proxy creation.')

    proxy_bm = bm.copy()
    try:
        source_index_layer = proxy_bm.faces.layers.int.new(
            LKS_QUADREMESH_SOURCE_FACE_INDEX_ATTR)
        proxy_bm.faces.ensure_lookup_table()
        for face in proxy_bm.faces:
            face[source_index_layer] = face.index

        _delete_bmesh_unselected_faces(proxy_bm)
        proxy_bm.faces.ensure_lookup_table()
        source_face_indices = [face[source_index_layer]
                               for face in proxy_bm.faces]

        proxy_mesh = bpy.data.meshes.new(
            f"{LKS_QUADREMESH_TEMP_NAME_PREFIX}{source_obj.data.name}")
        proxy_bm.to_mesh(proxy_mesh)
        _write_face_int_attribute(
            proxy_mesh,
            LKS_QUADREMESH_SOURCE_FACE_INDEX_ATTR,
            source_face_indices,
        )
        proxy_mesh.update()
    finally:
        proxy_bm.free()

    _copy_material_slots(source_obj, proxy_mesh)

    proxy_obj = bpy.data.objects.new(
        name=f"{LKS_QUADREMESH_TEMP_NAME_PREFIX}{source_obj.name}",
        object_data=proxy_mesh,
    )
    proxy_obj.matrix_world = source_obj.matrix_world.copy()
    _get_source_collection(context, source_obj).objects.link(proxy_obj)
    return mark_as_temp_quadremesh_object(proxy_obj, source_obj)


def create_visible_sculpt_proxy_object(
    context: bpy.types.Context,
    source_obj: bpy.types.Object,
) -> bpy.types.Object:
    """Create a temporary proxy object from currently visible sculpt faces."""
    if source_obj.type != 'MESH' or source_obj.mode != 'SCULPT':
        raise RuntimeError(
            'Visible-sculpt proxy creation requires a sculpt-mode mesh object.')

    hidden_faces = _read_face_bool_attribute(source_obj.data, '.hide_poly')
    if hidden_faces is None or len(hidden_faces) == 0:
        raise RuntimeError(
            'No hidden sculpt-face data found. Hide part of the sculpt mesh before using sculpt subset remesh.')

    visible_face_indices = patch_helpers.np.flatnonzero(~hidden_faces)
    if len(visible_face_indices) == 0:
        raise RuntimeError(
            'No visible sculpt faces available for Quad Remesh subset proxy creation.')

    source_mesh = source_obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(source_mesh)
        bm.faces.ensure_lookup_table()
        source_index_layer = bm.faces.layers.int.new(
            LKS_QUADREMESH_SOURCE_FACE_INDEX_ATTR)
        visible_face_index_set = set(int(index)
                                     for index in visible_face_indices)
        for face in bm.faces:
            face[source_index_layer] = face.index
            face.select = face.index in visible_face_index_set

        _delete_bmesh_unselected_faces(bm)
        bm.faces.ensure_lookup_table()
        source_face_indices = [face[source_index_layer] for face in bm.faces]

        proxy_mesh = bpy.data.meshes.new(
            f"{LKS_QUADREMESH_TEMP_NAME_PREFIX}{source_obj.data.name}")
        bm.to_mesh(proxy_mesh)
        _write_face_int_attribute(
            proxy_mesh,
            LKS_QUADREMESH_SOURCE_FACE_INDEX_ATTR,
            source_face_indices,
        )
        proxy_mesh.update()
    finally:
        bm.free()

    _copy_material_slots(source_obj, proxy_mesh)

    proxy_obj = bpy.data.objects.new(
        name=f"{LKS_QUADREMESH_TEMP_NAME_PREFIX}{source_obj.name}",
        object_data=proxy_mesh,
    )
    proxy_obj.matrix_world = source_obj.matrix_world.copy()
    _get_source_collection(context, source_obj).objects.link(proxy_obj)
    return mark_as_temp_quadremesh_object(proxy_obj, source_obj)


def cleanup_temp_quadremesh_object(obj: bpy.types.Object | None) -> None:
    """Delete a wrapper-owned temporary object and its mesh data when possible."""
    if not is_temp_quadremesh_object(obj):
        return

    mesh = obj.data if obj.type == 'MESH' else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def prepare_proxy_patch_materials(
    proxy_obj: bpy.types.Object,
    source_obj: bpy.types.Object,
    *,
    use_face_sets: bool,
    use_sharps: bool,
):
    """Compose proxy patch IDs into material slots for Quad Remesher export."""
    source_face_indices = _read_face_int_attribute(
        proxy_obj.data,
        LKS_QUADREMESH_SOURCE_FACE_INDEX_ATTR,
    )
    if source_face_indices is None:
        source_face_indices = patch_helpers.np.arange(
            len(proxy_obj.data.polygons),
            dtype=patch_helpers.np.int32,
        )

    material_ids = patch_helpers.read_patch_ids(
        source_obj, patch_helpers.MODE_MATERIALS)
    if material_ids is None:
        raise RuntimeError(
            'Unable to read source material IDs for Quad Remesh patch preparation.')

    components = [material_ids[source_face_indices]]

    if use_face_sets:
        face_set_ids = patch_helpers.read_patch_ids(
            source_obj, patch_helpers.MODE_FACE_SETS)
        if face_set_ids is not None:
            components.append(face_set_ids[source_face_indices])

    if use_sharps:
        components.append(_compute_sharp_region_ids(proxy_obj.data))

    composite = patch_helpers.np.stack(components, axis=1)
    _unique_keys, patch_ids = patch_helpers.np.unique(
        composite,
        axis=0,
        return_inverse=True,
    )
    patch_ids = patch_ids.astype(patch_helpers.np.int32, copy=False)
    patch_helpers.write_patch_ids(
        proxy_obj, patch_ids, patch_helpers.MODE_MATERIALS)
    return patch_ids

from typing import Callable, Sequence

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import object_helpers
from .lks_constants import (
    TRIANGULATE_NGON_METHOD_DEFAULT,
    TRIANGULATE_QUAD_METHOD_DEFAULT,
)


def make_selected_meshes_unique_and_apply_xforms_and_modifiers() -> None:
    """Make selection unique, mesh-only, with transforms and origin applied."""
    make_selected_objects_single_user()
    convert_selected_objects_to_meshes()
    apply_transforms_on_selected_objects()
    set_origin_to_median_on_selected_objects()
    delete_non_mesh_objects_in_selection()

    if bpy.context.selected_objects:
        bpy.context.view_layer.objects.active = bpy.context.selected_objects[-1]


def perform_action_on_selected_objects(action: Callable[[bpy.types.Object], None]) -> None:
    """Run an action on each selected object while preserving selection state."""
    objs: Sequence[bpy.types.Object] = bpy.context.selected_objects
    active = bpy.context.view_layer.objects.active

    bpy.ops.object.select_all(action='DESELECT')

    for obj in objs:
        obj.select_set(True)
        action(obj)

    # Set selection to objs and set active to last obj
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def make_selected_objects_single_user() -> None:
    """Duplicate object data for each selected object."""
    callable: Callable = bpy.ops.object.make_single_user(
        object=True, obdata=True, material=False, animation=False)
    perform_action_on_selected_objects(callable)


def convert_selected_objects_to_meshes() -> None:
    """Convert each selected object to a mesh."""
    callable: Callable = bpy.ops.object.convert(target='MESH')
    perform_action_on_selected_objects(callable)


def apply_transforms_on_selected_objects() -> None:
    """Apply location, rotation, and scale on each selected object."""
    callable: Callable = bpy.ops.object.transform_apply(
        location=True, rotation=True, scale=True)
    perform_action_on_selected_objects(callable)


def set_origin_to_median_on_selected_objects() -> None:
    """Set each selected object's origin to the 3D cursor median."""
    callable: Callable = bpy.ops.object.origin_set(
        type='ORIGIN_CURSOR', center='MEDIAN')
    perform_action_on_selected_objects(callable)


def delete_non_mesh_objects_in_selection() -> None:
    """Remove non-mesh objects from the current selection."""
    objs_to_delete = [
        obj for obj in bpy.context.selected_objects if obj.type != "MESH"
    ]
    for obj in objs_to_delete:
        bpy.data.objects.remove(obj)


def refresh_object_viewport(
    context: bpy.types.Context | None,
    obj: bpy.types.Object,
) -> None:
    """Invalidate evaluated mesh data and redraw 3D viewports after modifier edits."""
    if obj.type == 'MESH' and obj.data is not None:
        obj.data.update_tag()
        obj.update_tag(refresh={'DATA'})
    else:
        obj.update_tag(refresh={'OBJECT'})

    if context is None:
        return

    view_layer = getattr(context, 'view_layer', None)
    if view_layer is not None:
        view_layer.update()

    screen = getattr(context, 'screen', None)
    if screen is not None:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _bake_modifiers_via_depsgraph(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> None:
    """Fallback when bpy.ops.object.modifier_apply is unavailable or fails."""
    if obj.type != 'MESH' or not obj.modifiers:
        return
    from . import object_helpers as oh

    baked = oh.duplicate_via_depsgraph(obj, context=context)
    old_data = obj.data
    obj.data = baked.data
    while obj.modifiers:
        obj.modifiers.remove(obj.modifiers[0])
    bpy.data.objects.remove(baked, do_unlink=True)
    if old_data is not None and old_data.users == 0:
        bpy.data.meshes.remove(old_data)


def _prepare_object_for_modifier_edits(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> None:
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


def remove_modifiers_of_types(
    obj: bpy.types.Object,
    mod_types: set[str],
) -> int:
    """Remove modifiers of the given types without applying them."""
    if obj.type != "MESH":
        return 0
    removed = 0
    for mod in list(obj.modifiers):
        if mod.type in mod_types:
            obj.modifiers.remove(mod)
            removed += 1
    return removed


def apply_visible_modifiers_delete_hidden(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    exclude_types: set[str] | None = None,
) -> tuple[int, int]:
    """Apply viewport-visible modifiers; remove viewport-hidden ones.

    Returns ``(applied_count, deleted_count)``.
    """
    if obj.type != "MESH":
        return (0, 0)

    exclude_types = exclude_types or set()
    applied = 0
    deleted = 0

    _prepare_object_for_modifier_edits(context, obj)

    for mod in list(obj.modifiers):
        if mod.type in exclude_types:
            continue
        if not mod.show_viewport:
            obj.modifiers.remove(mod)
            deleted += 1
            continue
        try:
            with context.temp_override(
                object=obj,
                active_object=obj,
                selected_objects=[obj],
                view_layer=context.view_layer,
            ):
                bpy.ops.object.modifier_apply(modifier=mod.name)
            applied += 1
        except RuntimeError as exc:
            print(f"Could not apply modifier '{mod.name}' on '{obj.name}': {exc}")

    return (applied, deleted)


def apply_all_modifiers_on_object(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    exclude_types: set[str] | None = None,
) -> None:
    """Apply every modifier on obj except types listed in exclude_types."""
    if obj.type != "MESH":
        return

    exclude_types = exclude_types or set()

    _prepare_object_for_modifier_edits(context, obj)

    for mod in list(obj.modifiers):
        if mod.type in exclude_types:
            continue
        try:
            with context.temp_override(
                object=obj,
                active_object=obj,
                selected_objects=[obj],
                view_layer=context.view_layer,
            ):
                bpy.ops.object.modifier_apply(modifier=mod.name)
        except RuntimeError as exc:
            print(f"Could not apply modifier '{mod.name}' on '{obj.name}': {exc}")


def apply_triangulate_modifier(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    *,
    keep_custom_normals: bool = True,
    min_vertices: int = 4,
    quad_method: str = TRIANGULATE_QUAD_METHOD_DEFAULT,
    ngon_method: str = TRIANGULATE_NGON_METHOD_DEFAULT,
    modifier_name: str = "LKS_Triangulate",
) -> bool:
    """Add a triangulate modifier with export defaults and apply it immediately."""
    if obj.type != "MESH":
        return False

    _prepare_object_for_modifier_edits(context, obj)

    tri_mod: bpy.types.TriangulateModifier = obj.modifiers.new(
        name=modifier_name,
        type="TRIANGULATE",
    )
    tri_mod.keep_custom_normals = keep_custom_normals
    tri_mod.min_vertices = min_vertices
    tri_mod.quad_method = quad_method
    tri_mod.ngon_method = ngon_method

    mod_name = tri_mod.name
    try:
        with context.temp_override(
            object=obj,
            active_object=obj,
            selected_objects=[obj],
            view_layer=context.view_layer,
        ):
            bpy.ops.object.modifier_apply(modifier=mod_name)
        return True
    except RuntimeError as exc:
        print(f"Could not apply triangulate on '{obj.name}': {exc}")
        if mod_name in obj.modifiers:
            obj.modifiers.remove(obj.modifiers[mod_name])
        return False


from .deep_apply_debug import log as _mesh_join_log


def join_mesh_objects(
    context: bpy.types.Context,
    join_meshes: list[bpy.types.Object],
    *,
    scene: bpy.types.Scene | None = None,
    view_layer: bpy.types.ViewLayer | None = None,
) -> tuple[set[str], bpy.types.Object | None]:
    """Join meshes via ``bpy.ops.object.join`` with full selection context overrides."""
    if len(join_meshes) < 2:
        return ({'CANCELLED'}, None)

    target_scene = scene or context.scene
    target_layer = view_layer or (
        context.view_layer
        if context.scene == target_scene
        else target_scene.view_layers[0]
    )

    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    for obj in join_meshes:
        obj.select_set(True)
    target_layer.objects.active = join_meshes[0]

    override = {
        'scene': target_scene,
        'view_layer': target_layer,
        'selected_objects': join_meshes,
        'selected_editable_objects': join_meshes,
        'active_object': join_meshes[0],
        'object': join_meshes[0],
    }
    with context.temp_override(**override):
        if not bpy.ops.object.join.poll():
            return ({'CANCELLED'}, target_layer.objects.active)
        result = bpy.ops.object.join()

    return (result, target_layer.objects.active)


def _join_mesh_objects_via_bmesh(
    join_meshes: list[bpy.types.Object],
    *,
    context: bpy.types.Context,
) -> bpy.types.Object | None:
    """Join mesh objects when ``bpy.ops.object.join`` is unavailable or cancelled."""
    if len(join_meshes) < 2:
        return None

    from .mesh_attribute_sync_helpers import (
        collect_mesh_attribute_schema,
        sync_mesh_attributes,
    )

    join_schema = collect_mesh_attribute_schema(join_meshes)
    base = join_meshes[0]
    target_collections = list(base.users_collection)
    if not target_collections:
        target_collections = [context.scene.collection]

    bm = bmesh.new()
    for obj in join_meshes:
        mesh = obj.data
        if mesh is None or not mesh.vertices:
            continue
        temp_bm = bmesh.new()
        temp_bm.from_mesh(mesh)
        temp_bm.transform(obj.matrix_world.copy())
        vert_map = {vert: bm.verts.new(vert.co) for vert in temp_bm.verts}
        bm.verts.ensure_lookup_table()
        for face in temp_bm.faces:
            try:
                new_face = bm.faces.new([vert_map[vert] for vert in face.verts])
                new_face.smooth = face.smooth
            except ValueError:
                pass
        temp_bm.free()

    if not bm.verts:
        bm.free()
        return None

    bm.normal_update()
    joined_mesh = bpy.data.meshes.new(f'{base.name}_joined')
    bm.to_mesh(joined_mesh)
    bm.free()
    joined_mesh.update()

    joined_obj = bpy.data.objects.new(f'{base.name}_joined', joined_mesh)
    for coll in target_collections:
        if joined_obj.name not in coll.objects:
            coll.objects.link(joined_obj)
    joined_obj.matrix_world = Matrix.Identity(4)

    sync_mesh_attributes(context, [joined_obj], schema=join_schema)

    for obj in join_meshes:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    context.view_layer.objects.active = joined_obj
    context.view_layer.update()
    return joined_obj


def merge_meshes_with_pivot(
    meshes: list[bpy.types.Object],
    pivot: Vector,
    *,
    context: bpy.types.Context | None = None,
) -> bool:
    """Join meshes and set origin to pivot. Returns True when join ran."""

    ctx = context or bpy.context
    view_layer = ctx.view_layer
    view_layer_names = {obj.name for obj in view_layer.objects}

    # cache original selection and active object and restore when finished
    original_selection = [
        obj for obj in ctx.selected_objects
        if obj.name in view_layer_names
    ]
    original_active_object = ctx.active_object
    if (
        original_active_object is not None
        and original_active_object.name not in view_layer_names
    ):
        original_active_object = None

    filtered_meshes = object_helpers.filter_valid_objects(meshes)
    join_meshes = [
        obj for obj in filtered_meshes if obj.name in view_layer_names
    ]
    if len(join_meshes) < 2:
        print("No valid meshes to merge")
        return False

    verts_before = sum(len(obj.data.vertices) for obj in join_meshes)
    _mesh_join_log(
        f'select {len(join_meshes)} mesh(es) verts_before={verts_before} '
        f'names={[obj.name for obj in join_meshes]}',
        stage='join_select',
    )

    # Select all meshes, set the first one to active, and merge them
    # Then, set the pivot point to the cached pivot
    result, merged = join_mesh_objects(
        ctx,
        join_meshes,
        scene=ctx.scene,
        view_layer=view_layer,
    )
    if (
        'CANCELLED' in result
        or merged is None
        or merged.type != 'MESH'
        or merged.data is None
        or len(merged.data.vertices) < verts_before
    ):
        if 'CANCELLED' in result:
            _mesh_join_log(f'join operator cancelled: {result}', stage='join_fail')
        elif merged is not None and merged.data is not None:
            _mesh_join_log(
                f'join lost geometry: {verts_before} -> {len(merged.data.vertices)}',
                stage='join_fail',
            )
        merged = _join_mesh_objects_via_bmesh(join_meshes, context=ctx)
        if merged is None or merged.data is None:
            _mesh_join_log('bmesh join fallback failed', stage='join_fail')
            return False
        _mesh_join_log(
            f'bmesh join ok verts={len(merged.data.vertices)}',
            stage='join_bmesh',
        )

    merged = view_layer.objects.active
    if merged is not None and merged.type == 'MESH' and merged.data is not None:
        if merged.data.users > 1:
            object_helpers.ensure_single_user_mesh_data(merged)
        bpy.ops.object.select_all(action='DESELECT')
        merged.select_set(True)
        view_layer.objects.active = merged

    bpy.ops.object.transform_apply(
        location=True, rotation=True, scale=True)

    # Set cursor to original pivot point and set origin of the combine object to cursor
    ctx.scene.cursor.location = pivot
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

    # restore original selection (joined sources are removed — do not re-select them)
    bpy.ops.object.select_all(action='DESELECT')
    filtered_objects = object_helpers.filter_valid_objects(original_selection)

    for obj in filtered_objects:
        if obj.name in view_layer_names:
            obj.select_set(True)

    try:
        if (
            original_active_object is not None
            and original_active_object.name in view_layer_names
        ):
            view_layer.objects.active = original_active_object
    except ReferenceError:
        if filtered_objects:
            view_layer.objects.active = filtered_objects[-1]
    return True

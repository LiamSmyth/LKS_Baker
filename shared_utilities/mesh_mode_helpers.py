import bpy
from contextlib import contextmanager
from dataclasses import dataclass


_CONTEXT_MODE_TO_MODE_SET: dict[str, str] = {
    'OBJECT': 'OBJECT',
    'EDIT_MESH': 'EDIT',
    'SCULPT': 'SCULPT',
    'VERTEX_PAINT': 'VERTEX_PAINT',
    'WEIGHT_PAINT': 'WEIGHT_PAINT',
    'TEXTURE_PAINT': 'TEXTURE_PAINT',
}


@dataclass
class MeshModeState:
    active_object_name: str | None
    mode: str


def set_mesh_select_mode(context: bpy.types.Context, mode: str = 'VERT') -> None:
    """Set mesh edit select mode (VERT, EDGE, or FACE)."""
    if context.tool_settings:
        if mode == 'VERT':
            context.tool_settings.mesh_select_mode = (True, False, False)
        elif mode == 'EDGE':
            context.tool_settings.mesh_select_mode = (False, True, False)
        elif mode == 'FACE':
            context.tool_settings.mesh_select_mode = (False, False, True)
        else:
            raise ValueError(f"Unsupported mesh select mode: {mode}")
        return

    bpy.ops.mesh.select_mode(type=mode)


def capture_mesh_mode_state(context: bpy.types.Context) -> MeshModeState:
    """Capture active object and context mode for later restoration."""
    active = context.view_layer.objects.active
    return MeshModeState(
        active_object_name=active.name if active is not None else None,
        mode=context.mode,
    )


def restore_mesh_mode_state(
    context: bpy.types.Context,
    state: MeshModeState,
) -> None:
    """Best-effort restore of active object and context mode."""
    active_obj = context.active_object
    if active_obj is not None and active_obj.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass

    restore_obj = None
    if state.active_object_name is not None:
        restore_obj = context.scene.objects.get(state.active_object_name)

    if restore_obj is not None:
        context.view_layer.objects.active = restore_obj

    desired_mode = _CONTEXT_MODE_TO_MODE_SET.get(state.mode)
    if restore_obj is None or desired_mode is None or desired_mode == 'OBJECT':
        return

    try:
        bpy.ops.object.mode_set(mode=desired_mode)
    except RuntimeError:
        return


@contextmanager
def preserve_mesh_mode(context: bpy.types.Context):
    """Exit edit (or other non-object) mode for a block, then restore afterward."""
    state = capture_mesh_mode_state(context)
    if context.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    try:
        yield
    finally:
        restore_mesh_mode_state(context, state)


def _object_ops_override(
    context: bpy.types.Context,
    obj: bpy.types.Object,
) -> dict[str, object]:
    return {
        'active_object': obj,
        'object': obj,
        'selected_objects': [obj],
        'selected_editable_objects': [obj],
    }


@contextmanager
def object_mode_for_ops(context: bpy.types.Context, obj: bpy.types.Object):
    """Temporarily switch to Object mode so object-mode bpy.ops can run."""
    if obj.type != 'MESH':
        yield
        return

    prev_active = context.view_layer.objects.active
    prev_mode = context.mode
    was_object_mode = prev_mode == 'OBJECT'

    if prev_active is not obj:
        context.view_layer.objects.active = obj

    if not was_object_mode:
        bpy.ops.object.mode_set(mode='OBJECT')

    try:
        with context.temp_override(**_object_ops_override(context, obj)):
            yield
    finally:
        if not was_object_mode:
            desired_mode = _CONTEXT_MODE_TO_MODE_SET.get(prev_mode)
            if desired_mode and desired_mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode=desired_mode)
                except RuntimeError:
                    pass
        if prev_active is not None and prev_active is not obj:
            context.view_layer.objects.active = prev_active


@contextmanager
def edit_mode_for_ops(context: bpy.types.Context, obj: bpy.types.Object):
    """Temporarily switch obj to Edit mode so mesh-mode bpy.ops can run."""
    if obj.type != 'MESH':
        yield
        return

    prev_active = context.view_layer.objects.active
    was_edit_mode = context.mode == 'EDIT_MESH' and prev_active is obj

    if prev_active is not obj:
        context.view_layer.objects.active = obj

    if not was_edit_mode:
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode='EDIT')

    try:
        with context.temp_override(**_object_ops_override(context, obj)):
            yield
    finally:
        if not was_edit_mode:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                pass
        if prev_active is not None and prev_active is not obj:
            context.view_layer.objects.active = prev_active

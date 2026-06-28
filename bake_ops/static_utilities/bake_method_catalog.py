"""Discover bake methods per map_type from the engine registry."""
from __future__ import annotations

from lks_baker.bake_ops.engine.blender_bake.catalog import BLENDER_BUILTIN_METHOD_ID
from lks_baker.bake_ops.engine.registry import list_by_map_type
from lks_baker.bake_ops.static_utilities.bake_map_catalog import resolve_engine_map_type

BLENDER_BAKE_LABEL = 'Blender Bake'


def unique_method_ids_for_map_type(map_type: str) -> tuple[str, ...]:
    """Return sorted method ids for *map_type*, with ``blender`` first when present."""
    resolved = resolve_engine_map_type(map_type)
    method_ids = sorted({method_id for _, method_id, _ in list_by_map_type(resolved)})
    if BLENDER_BUILTIN_METHOD_ID in method_ids:
        return (
            BLENDER_BUILTIN_METHOD_ID,
            *(mid for mid in method_ids if mid != BLENDER_BUILTIN_METHOD_ID),
        )
    return tuple(method_ids)


def unique_method_ids_for_map_id(map_id: str) -> tuple[str, ...]:
    """Return registry method ids for the engine map type behind a catalog *map_id*."""
    return unique_method_ids_for_map_type(resolve_engine_map_type(map_id))


def method_display_label(method_id: str) -> str:
    """Human-readable label for a registry *method_id*."""
    if method_id == BLENDER_BUILTIN_METHOD_ID:
        return BLENDER_BAKE_LABEL
    return method_id.replace('_', ' ').title()


def default_bake_method_for_map_type(map_type: str) -> str:
    """Default method id: ``blender`` when registered, else the primary method."""
    methods = unique_method_ids_for_map_type(map_type)
    if not methods:
        return ''
    if BLENDER_BUILTIN_METHOD_ID in methods:
        return BLENDER_BUILTIN_METHOD_ID
    return methods[0]


def default_bake_method_for_map_id(map_id: str) -> str:
    """Default method id for a catalog *map_id*."""
    return default_bake_method_for_map_type(resolve_engine_map_type(map_id))


def map_has_method_selector(map_id: str) -> bool:
    """True when the gear menu should expose a Method dropdown."""
    return len(unique_method_ids_for_map_id(map_id)) >= 1


def map_has_bake_methods(map_id: str) -> bool:
    """Alias for ``map_has_method_selector`` — any registered method shows Method row."""
    return map_has_method_selector(map_id)


def iter_bake_method_enum_items(map_id: str) -> list[tuple[str, str, str]]:
    """Build Blender ``EnumProperty`` items for *map_id*."""
    return [
        (method_id, method_display_label(method_id), '')
        for method_id in unique_method_ids_for_map_id(map_id)
    ]


def resolve_map_entry_bake_method(entry, *, map_id: str | None = None) -> str:
    """Return the effective bake method id for a map entry RNA row."""
    resolved_map_id = map_id or getattr(entry, 'map_id', '') or ''
    methods = unique_method_ids_for_map_id(resolved_map_id)
    if not methods:
        return ''
    stored = getattr(entry, 'lks_bake_method', '') or ''
    if stored in methods:
        return stored
    return default_bake_method_for_map_id(resolved_map_id)


def resolve_map_backend_preference_from_method(entry, *, map_id: str | None = None) -> str:
    """Map gear-menu Method selection to planner backend preference."""
    resolved_map_id = map_id or getattr(entry, 'map_id', '') or ''
    method = resolve_map_entry_bake_method(entry, map_id=resolved_map_id)
    if method == BLENDER_BUILTIN_METHOD_ID:
        return 'MESH_ONLY'
    if method:
        return 'DERIVE_ONLY'
    return 'AUTO'


def is_registered_engine_method(map_id: str, method_id: str) -> bool:
    """True when *method_id* is a CPU/GPU bake-engine implementation for *map_id*."""
    if not method_id or method_id == BLENDER_BUILTIN_METHOD_ID:
        return False
    map_type = resolve_engine_map_type(map_id)
    for _, registered_method, device in list_by_map_type(map_type):
        if registered_method == method_id and device in ('cpu', 'gpu'):
            return True
    return False


def engine_method_prerequisites(map_id: str, method_id: str) -> tuple[str, ...]:
    """Parent map_ids required before a non-blender engine method can run."""
    if not method_id or method_id == BLENDER_BUILTIN_METHOD_ID:
        return ()
    if map_id in ('ao', 'ao_2'):
        if method_id == 'normal_cavity':
            return ('normal',)
        if method_id in (
            'atlas_hbao',
            'normal_height_hbao',
            'height_hbao',
            'ao_composite',
        ):
            return ('normal_object', 'position')
    if map_id == 'bent_normal' and method_id == 'hemisphere_trace':
        return ('normal_object', 'position')
    if map_id == 'bent_normal_object' and method_id == 'bent_normal_object':
        return ('normal_object', 'position')
    return ()

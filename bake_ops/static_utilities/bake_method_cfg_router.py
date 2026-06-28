"""Resolve per-method bake cfg modules and draw gear-popup method settings.

Convention (under ``engine/map_types/<map_type>/``):

- ``<method_id>_cfg.py`` — ``*Config`` dataclass, ``config_from_entry(entry, **kwargs)``
- ``<method_id>_cfg_ui.py`` — ``draw_<method_id>_settings(layout, entry, project)``

Shared ``blender`` method cfg lives in ``engine/blender_bake/`` and is used as fallback
when a map-type folder has no local ``blender_cfg*.py``.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Iterator

from .bake_map_catalog import BAKE_MAP_LIGHTING_IDS, resolve_engine_map_type

if TYPE_CHECKING:
    import bpy

    from ..lks_bake_props import LKS_PG_BakeMapEntry, LKS_PG_BakeProject

_BLENDER_SHARED_CFG = (
    'lks_baker.bake_ops.engine.blender_bake.blender_cfg'
)
_BLENDER_SHARED_CFG_UI = (
    'lks_baker.bake_ops.engine.blender_bake.blender_cfg_ui'
)
_LIGHTING_BLENDER_CFG = (
    'lks_baker.bake_ops.engine.map_types.lighting.blender_cfg'
)
_LIGHTING_BLENDER_CFG_UI = (
    'lks_baker.bake_ops.engine.map_types.lighting.blender_cfg_ui'
)


def _map_type_cfg_module(map_type: str, method_id: str, *, suffix: str) -> str:
    return (
        f'lks_baker.bake_ops.engine.map_types.'
        f'{map_type}.{method_id}_{suffix}'
    )


def _import_first(module_names: tuple[str, ...]) -> Any | None:
    for name in module_names:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    return None


def resolve_method_cfg_module(map_type: str, method_id: str) -> Any | None:
    """Import ``<method_id>_cfg`` for *map_type*, with blender shared fallback."""
    candidates = (_map_type_cfg_module(map_type, method_id, suffix='cfg'),)
    if method_id == 'blender':
        if map_type in BAKE_MAP_LIGHTING_IDS:
            candidates = (_LIGHTING_BLENDER_CFG, *candidates)
        candidates = (*candidates, _BLENDER_SHARED_CFG)
    return _import_first(candidates)


def resolve_method_cfg_ui_module(map_type: str, method_id: str) -> Any | None:
    """Import ``<method_id>_cfg_ui`` for *map_type*, with blender shared fallback."""
    candidates = (_map_type_cfg_module(map_type, method_id, suffix='cfg_ui'),)
    if method_id == 'blender':
        if map_type in BAKE_MAP_LIGHTING_IDS:
            candidates = (_LIGHTING_BLENDER_CFG_UI, *candidates)
        candidates = (*candidates, _BLENDER_SHARED_CFG_UI)
    return _import_first(candidates)


def _resolve_draw_fn(module: Any, method_id: str) -> Any | None:
    draw_fn = getattr(module, f'draw_{method_id}_settings', None)
    return draw_fn if callable(draw_fn) else None


def has_bake_method_settings(map_id: str, method_id: str) -> bool:
    """True when a cfg_ui draw function exists for *(map_id, method_id)*."""
    map_type = resolve_engine_map_type(map_id)
    module = resolve_method_cfg_ui_module(map_type, method_id)
    if module is None:
        return False
    return _resolve_draw_fn(module, method_id) is not None


def draw_bake_method_settings(
    layout: Any,
    entry: Any,
    project: Any,
    *,
    map_id: str | None = None,
    method_id: str | None = None,
) -> None:
    """Draw the dynamic method-settings section below the Method row."""
    from .bake_method_catalog import resolve_map_entry_bake_method

    resolved_map_id = map_id or entry.map_id
    resolved_method = method_id or resolve_map_entry_bake_method(
        entry,
        map_id=resolved_map_id,
    )
    if not resolved_method:
        return

    map_type = resolve_engine_map_type(resolved_map_id)
    module = resolve_method_cfg_ui_module(map_type, resolved_method)
    if module is None:
        return
    draw_fn = _resolve_draw_fn(module, resolved_method)
    if draw_fn is None:
        return
    draw_fn(layout, entry, project)


def config_from_map_entry(
    entry: LKS_PG_BakeMapEntry,
    *,
    map_id: str | None = None,
    method_id: str | None = None,
    **kwargs: Any,
) -> Any | None:
    """Build a method ``*Config`` dataclass from map-entry RNA."""
    from .bake_method_catalog import resolve_map_entry_bake_method

    resolved_map_id = map_id or entry.map_id
    resolved_method = method_id or resolve_map_entry_bake_method(
        entry,
        map_id=resolved_map_id,
    )
    if not resolved_method:
        return None

    map_type = resolve_engine_map_type(resolved_map_id)
    module = resolve_method_cfg_module(map_type, resolved_method)
    if module is None:
        return None
    builder = getattr(module, 'config_from_entry', None)
    if not callable(builder):
        return None
    return builder(entry, **kwargs)


def iter_registered_method_cfg_ui() -> Iterator[tuple[str, str, Any]]:
    """Yield ``(map_type, method_id, cfg_ui_module)`` for registry smoke tests."""
    from lks_baker.bake_ops.engine.registry import list_bake_maps

    seen: set[tuple[str, str]] = set()
    for map_type, method_id, _device in list_bake_maps():
        key = (map_type, method_id)
        if key in seen:
            continue
        seen.add(key)
        module = resolve_method_cfg_ui_module(map_type, method_id)
        if module is not None and _resolve_draw_fn(module, method_id) is not None:
            yield map_type, method_id, module

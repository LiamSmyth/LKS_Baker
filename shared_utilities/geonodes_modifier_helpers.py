"""Read/write geometry-nodes modifier inputs using RNA (Blender 5.x safe)."""
from __future__ import annotations

import bpy


def _modifier_input_identifiers(modifier: bpy.types.Modifier) -> list[str]:
    if modifier.type != "NODES" or modifier.node_group is None:
        return []

    identifiers: list[str] = []
    for item in modifier.node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT":
            identifiers.append(item.identifier)
    return identifiers


def resolve_modifier_input_identifier(
    modifier: bpy.types.Modifier,
    key: str,
) -> str | None:
    """Resolve a legacy Input_N / Socket_N key or socket name to an RNA identifier."""
    if modifier.type != "NODES" or modifier.node_group is None or not key:
        return None

    if hasattr(modifier, key):
        return key

    for item in modifier.node_group.interface.items_tree:
        if item.item_type != "SOCKET" or item.in_out != "INPUT":
            continue
        if item.identifier == key or item.name == key:
            return item.identifier

    if key.startswith(("Input_", "Socket_")):
        try:
            index = int(key.split("_", 1)[1]) - 1
            identifiers = _modifier_input_identifiers(modifier)
            if 0 <= index < len(identifiers):
                return identifiers[index]
        except (ValueError, IndexError):
            pass

    return None


def get_nodes_modifier_input(
    modifier: bpy.types.Modifier,
    key: str,
    default=None,
):
    identifier = resolve_modifier_input_identifier(modifier, key)
    if identifier is None:
        return default

    try:
        return getattr(modifier, identifier)
    except AttributeError:
        try:
            return modifier[identifier]
        except (TypeError, KeyError, AttributeError):
            return default


def set_nodes_modifier_input(
    modifier: bpy.types.Modifier,
    key: str,
    value,
) -> bool:
    identifier = resolve_modifier_input_identifier(modifier, key)
    if identifier is None:
        return False

    try:
        setattr(modifier, identifier, value)
        return True
    except AttributeError:
        try:
            modifier[identifier] = value
            return True
        except (TypeError, KeyError, AttributeError):
            return False


def set_nodes_modifier_inputs(
    modifier: bpy.types.Modifier,
    values: dict[str, object],
) -> None:
    for key, value in values.items():
        set_nodes_modifier_input(modifier, key, value)

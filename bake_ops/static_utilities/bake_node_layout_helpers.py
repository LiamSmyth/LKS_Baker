"""Deterministic column layout for baker-managed low material node trees."""

from __future__ import annotations

import bpy

_BAKE_LAYOUT_COL_TEXTURES = -700
_BAKE_LAYOUT_COL_CONVERT = -350
_BAKE_LAYOUT_COL_BSDF = 0
_BAKE_LAYOUT_COL_OUTPUT = 350
_BAKE_LAYOUT_ROW_SPACING = 280
_SOLO_PREVIEW_LABEL_PREFIX = 'Solo Preview '


def _is_preview_texture_node(node: bpy.types.Node) -> bool:
    if node.type != 'TEX_IMAGE':
        return False
    label = node.label or ''
    return (
        label == 'Bake Target'
        or label.startswith('Preview ')
        or label.startswith(_SOLO_PREVIEW_LABEL_PREFIX)
    )


def _is_convert_node(node: bpy.types.Node) -> bool:
    if node.type == 'NORMAL_MAP':
        return True
    label = node.label or ''
    return label.startswith('Preview ') and 'Normal' in label


def layout_bake_material_nodes(tree: bpy.types.NodeTree) -> None:
    """Place preview / bake-target nodes in non-overlapping columns."""
    textures: list[bpy.types.Node] = []
    converts: list[bpy.types.Node] = []
    solo_nodes: list[bpy.types.Node] = []
    principled: bpy.types.Node | None = None
    output: bpy.types.Node | None = None

    for node in tree.nodes:
        label = node.label or ''
        if node.type == 'BSDF_PRINCIPLED':
            principled = node
        elif node.type == 'OUTPUT_MATERIAL':
            output = node
        elif label.startswith(_SOLO_PREVIEW_LABEL_PREFIX):
            solo_nodes.append(node)
        elif _is_convert_node(node):
            converts.append(node)
        elif _is_preview_texture_node(node):
            textures.append(node)

    textures.sort(key=lambda node: (node.label or node.name).lower())
    converts.sort(key=lambda node: (node.label or node.name).lower())
    solo_nodes.sort(key=lambda node: (node.label or node.name).lower())

    for index, node in enumerate(textures):
        node.location = (
            _BAKE_LAYOUT_COL_TEXTURES,
            -index * _BAKE_LAYOUT_ROW_SPACING,
        )

    for index, node in enumerate(converts):
        node.location = (
            _BAKE_LAYOUT_COL_CONVERT,
            -index * _BAKE_LAYOUT_ROW_SPACING,
        )

    if principled is not None:
        principled.location = (_BAKE_LAYOUT_COL_BSDF, 0)

    if output is not None:
        output.location = (_BAKE_LAYOUT_COL_OUTPUT, 0)

    for index, node in enumerate(solo_nodes):
        node.location = (
            _BAKE_LAYOUT_COL_OUTPUT,
            -(index + 1) * _BAKE_LAYOUT_ROW_SPACING,
        )

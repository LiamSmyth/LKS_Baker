"""Power-of-two bake texture resolution helpers and shared UI drawing."""

from __future__ import annotations

import bpy

from lks_baker.shared_utilities.lks_constants import (
    BAKE_TEXTURE_RESOLUTION_DEFAULT,
    BAKE_TEXTURE_RESOLUTION_ITEMS,
    BAKE_TEXTURE_RESOLUTION_VALUES,
)


def resolution_enum_to_int(value: str) -> int:
    """Convert a bake resolution EnumProperty identifier to pixels."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return BAKE_TEXTURE_RESOLUTION_DEFAULT


def project_default_resolution_xy(project) -> tuple[int, int]:
    """Return project-level default bake texture width and height."""
    return (
        resolution_enum_to_int(project.default_resolution_x),
        resolution_enum_to_int(project.default_resolution_y),
    )


def format_project_default_resolution(project) -> str:
    """Human-readable project default resolution for override popups."""
    width, height = project_default_resolution_xy(project)
    if getattr(project, 'default_resolution_linked', True) or width == height:
        return f'{width}px'
    return f'{width}×{height}px'


def resolve_bake_texture_dimensions(
    project,
    map_entry=None,
    *,
    group_resolution: int = 0,
) -> tuple[int, int]:
    """Map/group square overrides win; otherwise use project X/Y defaults."""
    if map_entry is not None and map_entry.resolution > 0:
        size = map_entry.resolution
        return size, size
    if group_resolution > 0:
        return group_resolution, group_resolution
    return project_default_resolution_xy(project)


def draw_linked_texture_resolution_row(
    layout: bpy.types.UILayout,
    owner: bpy.types.PropertyGroup,
    *,
    x_prop: str,
    y_prop: str,
    linked_prop: str,
    linked: bool,
) -> None:
    """Draw linked or split power-of-two resolution controls with a link toggle."""
    row = layout.row(align=True)
    if linked:
        row.prop(owner, x_prop, text='Resolution')
    else:
        row.prop(owner, x_prop, text='X')
        row.prop(owner, y_prop, text='Y')
    row.prop(
        owner,
        linked_prop,
        text='',
        icon='LINKED' if linked else 'UNLOCKED',
        emboss=False,
    )


def sync_linked_resolution_axis(
    owner: bpy.types.PropertyGroup,
    *,
    source_axis: str,
    x_prop: str,
    y_prop: str,
    linked_prop: str,
) -> None:
    """Keep Y in sync with X (or vice versa) when resolution axes are linked."""
    if not getattr(owner, linked_prop):
        return
    source_value = getattr(owner, x_prop if source_axis == 'x' else y_prop)
    target_prop = y_prop if source_axis == 'x' else x_prop
    if getattr(owner, target_prop) != source_value:
        setattr(owner, target_prop, source_value)


def make_resolution_enum_property(
    *,
    name: str,
    description: str,
    update,
) -> bpy.props.EnumProperty:
    """Shared EnumProperty factory for bake texture resolution RNA."""
    return bpy.props.EnumProperty(
        name=name,
        description=description,
        items=BAKE_TEXTURE_RESOLUTION_ITEMS,
        default=str(BAKE_TEXTURE_RESOLUTION_DEFAULT),
        update=update,
    )

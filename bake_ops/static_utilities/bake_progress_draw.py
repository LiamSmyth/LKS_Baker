"""Viewport HUD overlay for in-progress bake runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import bpy

if TYPE_CHECKING:
    from bpy.types import Area, Context, Region, SpaceView3D

_OVERLAY_BAR_WIDTH_FACTOR = 0.6
_OVERLAY_BOTTOM_MARGIN = 28
_OVERLAY_BAR_HEIGHT = 22
_OVERLAY_PADDING = 6
_OVERLAY_TEXT_SIZE = 14

_BG_COLOR = (0.08, 0.08, 0.08, 0.72)
_FILL_COLOR = (0.22, 0.55, 0.92, 0.92)
_TEXT_COLOR = (0.95, 0.95, 0.95, 1.0)

_overlay_handlers: list[tuple[SpaceView3D, object]] = []
_overlay_target_area_ptr: int | None = None


def _resolve_view3d_area(context: Context) -> Area | None:
    area = context.area
    if area is not None and area.type == 'VIEW_3D':
        return area
    wm = context.window_manager
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for candidate in screen.areas:
            if candidate.type == 'VIEW_3D':
                return candidate
    return None


def _resolve_window_region(area: Area) -> Region | None:
    for region in area.regions:
        if region.type == 'WINDOW':
            return region
    return None


def _uniform_color_shader():
    import gpu

    for name in ('UNIFORM_COLOR', '2D_UNIFORM_COLOR'):
        try:
            return gpu.shader.from_builtin(name)
        except ValueError:
            continue
    raise RuntimeError('No supported gpu uniform color shader')


def _draw_colored_rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    color: tuple[float, float, float, float],
) -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    shader = _uniform_color_shader()
    vertices = (
        (x0, y0),
        (x1, y0),
        (x1, y1),
        (x0, y1),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    batch = batch_for_shader(shader, 'TRIS', {'pos': vertices}, indices=indices)
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float('color', color)
    batch.draw(shader)


def _draw_bake_progress_overlay() -> None:
    context = bpy.context
    wm = context.window_manager
    if not getattr(wm, 'lks_bake_progress_active', False):
        return

    area = context.area
    if area is None or area.type != 'VIEW_3D':
        return
    if _overlay_target_area_ptr is not None and area.as_pointer() != _overlay_target_area_ptr:
        return

    region = _resolve_window_region(area)
    if region is None:
        return

    import blf

    region_width = region.width
    region_height = region.height
    bar_width = region_width * _OVERLAY_BAR_WIDTH_FACTOR
    bar_x0 = (region_width - bar_width) * 0.5
    bar_y0 = _OVERLAY_BOTTOM_MARGIN
    bar_x1 = bar_x0 + bar_width
    bar_y1 = bar_y0 + _OVERLAY_BAR_HEIGHT

    _draw_colored_rect(bar_x0, bar_y0, bar_x1, bar_y1, _BG_COLOR)

    factor = float(getattr(wm, 'lks_bake_progress_factor', 0.0))
    factor = max(0.0, min(factor, 1.0))
    fill_x1 = bar_x0 + _OVERLAY_PADDING + max(
        0.0,
        (bar_width - _OVERLAY_PADDING * 2.0) * factor,
    )
    if fill_x1 > bar_x0 + _OVERLAY_PADDING:
        _draw_colored_rect(
            bar_x0 + _OVERLAY_PADDING,
            bar_y0 + _OVERLAY_PADDING,
            fill_x1,
            bar_y1 - _OVERLAY_PADDING,
            _FILL_COLOR,
        )

    message = wm.lks_bake_progress_message or 'Baking…'
    font_id = 0
    blf.size(font_id, _OVERLAY_TEXT_SIZE)
    text_width, text_height = blf.dimensions(font_id, message)
    text_x = bar_x0 + (bar_width - text_width) * 0.5
    text_y = bar_y1 + 6.0
    if text_y + text_height > region_height - 4.0:
        text_y = bar_y0 - text_height - 4.0
    blf.color(font_id, *_TEXT_COLOR)
    blf.position(font_id, text_x, text_y, 0)
    blf.draw(font_id, message)


def register_viewport_overlay(context: Context) -> None:
    """Attach a POST_PIXEL HUD to the active (or first) 3D viewport."""
    global _overlay_target_area_ptr

    unregister_viewport_overlay()

    area = _resolve_view3d_area(context)
    if area is None:
        return

    space = area.spaces.active
    if space is None or space.type != 'VIEW_3D':
        return

    handler = space.draw_handler_add(
        _draw_bake_progress_overlay,
        (),
        'WINDOW',
        'POST_PIXEL',
    )
    _overlay_handlers.append((space, handler))
    _overlay_target_area_ptr = area.as_pointer()
    _tag_view3d_redraw(context)


def unregister_viewport_overlay() -> None:
    """Remove any bake progress viewport draw handlers."""
    global _overlay_target_area_ptr

    for space, handler in _overlay_handlers:
        try:
            space.draw_handler_remove(handler, 'WINDOW')
        except (AttributeError, TypeError, ValueError):
            pass
    _overlay_handlers.clear()
    _overlay_target_area_ptr = None


def _tag_view3d_redraw(context: Context) -> None:
    wm = context.window_manager
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

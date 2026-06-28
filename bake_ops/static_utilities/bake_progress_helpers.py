"""Blender UI progress for the bake pipeline — no-op without an interactive window manager."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generator

import bpy

from .bake_map_catalog import get_map_display_label
from .bake_progress_draw import (
    register_viewport_overlay,
    unregister_viewport_overlay,
)

if TYPE_CHECKING:
    from ..lks_bake_props import LKS_PG_BakeProject

_BAKE_PROGRESS_PREFIX = 'LKS Bake'
_PREP_STEP_COUNT = 5
_POST_STEP_COUNT = 3
_SUBSTEPS_PER_MAP = 3

_active_session: BakeProgressSession | None = None


class BakeProgressCancelled(RuntimeError):
    """Raised when the user cancels via Blender's progress UI (future hook)."""


@dataclass
class BakeProgressSession:
    """Tracks bake progress for viewport HUD, status bar, header text, and panel RNA."""

    context: bpy.types.Context
    total_steps: int
    current_step: int = 0
    _overlay_registered: bool = field(default=False, init=False)
    _header_areas: list[bpy.types.Area] = field(default_factory=list, init=False)

    def begin(self) -> None:
        if not progress_ui_available(self.context):
            return
        wm = self.context.window_manager
        wm.lks_bake_progress_active = True
        wm.lks_bake_progress_factor = 0.0
        wm.lks_bake_progress_message = 'Starting bake…'
        register_viewport_overlay(self.context)
        self._overlay_registered = True
        self._cache_header_areas()
        self._sync_ui('Starting bake…')

    def report(self, message: str, *, advance: bool = True) -> None:
        if not progress_ui_available(self.context):
            return
        if advance:
            self.current_step = min(self.current_step + 1, self.total_steps)
        self._sync_ui(message)

    def end(self) -> None:
        if not progress_ui_available(self.context):
            return
        wm = self.context.window_manager
        if self._overlay_registered:
            unregister_viewport_overlay()
            self._overlay_registered = False
        wm.lks_bake_progress_active = False
        wm.lks_bake_progress_factor = 0.0
        wm.lks_bake_progress_message = ''
        self._clear_status_text()
        self._tag_redraw()

    def _sync_ui(self, message: str) -> None:
        wm = self.context.window_manager
        factor = self.current_step / max(self.total_steps, 1)
        wm.lks_bake_progress_factor = factor
        wm.lks_bake_progress_message = message
        status = f'{_BAKE_PROGRESS_PREFIX}: {message}'
        workspace = getattr(self.context, 'workspace', None)
        if workspace is not None and hasattr(workspace, 'status_text_set'):
            workspace.status_text_set(status)
        for area in self._header_areas:
            if area is not None:
                area.header_text_set(status)
        self._tag_redraw()

    def _cache_header_areas(self) -> None:
        self._header_areas = []
        wm = self.context.window_manager
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    self._header_areas.append(area)

    def _clear_status_text(self) -> None:
        workspace = getattr(self.context, 'workspace', None)
        if workspace is not None and hasattr(workspace, 'status_text_set'):
            workspace.status_text_set(None)
        for area in self._header_areas:
            if area is not None:
                area.header_text_set(None)
        self._header_areas = []

    def _tag_redraw(self) -> None:
        wm = self.context.window_manager
        for window in wm.windows:
            screen = window.screen
            if screen is None:
                continue
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def progress_ui_available(context: bpy.types.Context | None) -> bool:
    """True when interactive WM progress/status updates are possible."""
    if bpy.app.background:
        return False
    if context is None:
        return False
    wm = getattr(context, 'window_manager', None)
    if wm is None:
        return False
    try:
        return len(wm.windows) > 0
    except (AttributeError, TypeError):
        return False


def active_bake_progress_session() -> BakeProgressSession | None:
    return _active_session


def bake_progress_report(message: str, *, advance: bool = True) -> None:
    """Update the active bake progress session when one is running."""
    session = _active_session
    if session is None:
        return
    session.report(message, advance=advance)


def bake_progress_map_label(map_id: str) -> str:
    """User-facing map name for progress strings."""
    return get_map_display_label(map_id)


def estimate_bake_step_count(
    project: LKS_PG_BakeProject,
    group_name: str,
    *,
    map_ids: list[str] | None = None,
    require_enabled: bool = True,
    reuse_existing_dependencies: bool = False,
) -> int:
    """Rough step budget for progress UI (prep + maps + post)."""
    from ..engine.planner import compile_bake_job_steps

    job_steps = compile_bake_job_steps(
        project,
        group_name,
        map_ids=map_ids,
        require_enabled=require_enabled,
        reuse_existing_dependencies=reuse_existing_dependencies,
    )
    map_count = max(len(job_steps), 1)
    return _PREP_STEP_COUNT + map_count * _SUBSTEPS_PER_MAP + _POST_STEP_COUNT


@contextmanager
def bake_progress_session(
    context: bpy.types.Context,
    *,
    total_steps: int,
) -> Generator[BakeProgressSession, None, None]:
    """Start/end viewport progress HUD around a bake run."""
    global _active_session
    session = BakeProgressSession(context=context, total_steps=max(total_steps, 1))
    previous = _active_session
    _active_session = session
    session.begin()
    try:
        yield session
    finally:
        session.end()
        _active_session = previous


def draw_bake_progress_bar(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
    """Panel progress bar + status line while a bake is running."""
    wm = context.window_manager
    if not getattr(wm, 'lks_bake_progress_active', False):
        return
    message = wm.lks_bake_progress_message or 'Baking…'
    box = layout.box()
    row = box.row()
    row.scale_y = 1.2
    row.progress(
        factor=wm.lks_bake_progress_factor,
        type='BAR',
        text=message,
    )


def register_props() -> None:
    bpy.types.WindowManager.lks_bake_progress_active = bpy.props.BoolProperty(
        name='LKS Bake Progress Active',
        default=False,
        options={'HIDDEN'},
    )
    bpy.types.WindowManager.lks_bake_progress_factor = bpy.props.FloatProperty(
        name='LKS Bake Progress',
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
        options={'HIDDEN'},
    )
    bpy.types.WindowManager.lks_bake_progress_message = bpy.props.StringProperty(
        name='LKS Bake Progress Message',
        default='',
        options={'HIDDEN'},
    )


def unregister_props() -> None:
    unregister_viewport_overlay()
    for prop_name in (
        'lks_bake_progress_message',
        'lks_bake_progress_factor',
        'lks_bake_progress_active',
    ):
        if hasattr(bpy.types.WindowManager, prop_name):
            delattr(bpy.types.WindowManager, prop_name)

"""Verbose tracing for bake pipeline progress. Toggle BAKE_DEBUG off when done."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

BAKE_DEBUG = True
_PREFIX = '[LKS Bake]'


def enabled() -> bool:
    return BAKE_DEBUG


def _context_suffix(
    *,
    project=None,
    group_name: str | None = None,
    map_id: str | None = None,
) -> str:
    parts: list[str] = []
    if project is not None:
        parts.append(f'project={getattr(project, "name", project)}')
    if group_name:
        parts.append(f'group={group_name}')
    if map_id:
        parts.append(f'map={map_id}')
    return f' [{", ".join(parts)}]' if parts else ''


def log_step(
    msg: str,
    *,
    project=None,
    group_name: str | None = None,
    map_id: str | None = None,
) -> None:
    if not BAKE_DEBUG:
        return
    suffix = _context_suffix(project=project, group_name=group_name, map_id=map_id)
    print(f'{_PREFIX}{suffix} {msg}', flush=True)


@contextmanager
def timed_step(
    name: str,
    *,
    project=None,
    group_name: str | None = None,
    map_id: str | None = None,
) -> Generator[None, None, None]:
    if not BAKE_DEBUG:
        yield
        return
    suffix = _context_suffix(project=project, group_name=group_name, map_id=map_id)
    print(f'{_PREFIX}{suffix} ▶ {name}', flush=True)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        print(f'{_PREFIX}{suffix} ◀ {name} ({elapsed:.2f}s)', flush=True)

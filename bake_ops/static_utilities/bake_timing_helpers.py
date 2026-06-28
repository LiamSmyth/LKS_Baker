"""Per-map bake wall-time collection and console summaries."""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Generator

from .bake_debug_log_helpers import BAKE_DEBUG, _PREFIX, log_step, timed_step
from .bake_method_catalog import method_display_label

BAKE_TIMING_REPORT_FILENAME = 'bake_timing.json'

RUN_KIND_PROJECT = 'project'
RUN_KIND_SINGLE_MAP = 'single_map'

BACKEND_MESH = 'mesh'
BACKEND_DERIVE = 'derive'
BACKEND_ENGINE = 'engine'


@dataclass
class BakeMapTimingState:
    """Mutable per-map fields applied when the timing record is finalized."""

    method_id: str
    backend: str


@dataclass(frozen=True)
class BakeMapTiming:
    """One completed or failed map bake attempt."""

    map_id: str
    method_id: str
    backend: str
    width: int
    height: int
    seconds: float
    success: bool
    error: str | None = None
    internal_prerequisite: bool = False
    group_name: str = ''


@dataclass
class BakeTimingSession:
    """Collects per-map timings for one project or single-map bake run."""

    run_kind: str
    project_name: str
    map_id_filter: str | None = None
    records: list[BakeMapTiming] = field(default_factory=list)
    wall_seconds: float = 0.0

    def record(self, timing: BakeMapTiming) -> None:
        self.records.append(timing)


_active_session: BakeTimingSession | None = None


def active_bake_timing_session() -> BakeTimingSession | None:
    return _active_session


@contextmanager
def bake_timing_session(
    *,
    project,
    run_kind: str,
    map_id: str | None = None,
) -> Generator[BakeTimingSession, None, None]:
    """Start timing collection for a full project or single-map bake."""
    global _active_session
    session = BakeTimingSession(
        run_kind=run_kind,
        project_name=getattr(project, 'name', 'BakeProject'),
        map_id_filter=map_id,
    )
    wall_start = time.perf_counter()
    previous = _active_session
    _active_session = session
    try:
        yield session
    finally:
        session.wall_seconds = time.perf_counter() - wall_start
        _active_session = previous


@contextmanager
def record_bake_map_timing(
    *,
    map_id: str,
    method_id: str,
    backend: str,
    width: int,
    height: int,
    project=None,
    group_name: str = '',
    internal_prerequisite: bool = False,
    timing_state: BakeMapTimingState | None = None,
) -> Generator[None, None, None]:
    """Wrap one map bake with ``timed_step`` logging and optional session recording."""
    label_backend = BACKEND_DERIVE if backend == BACKEND_DERIVE else BACKEND_MESH
    step_name = f'bake map {map_id} ({label_backend}, {width}x{height})'
    log_ctx = dict(project=project, group_name=group_name or None, map_id=map_id)
    session = active_bake_timing_session()
    t0 = time.perf_counter()
    success = False
    error: str | None = None
    try:
        with timed_step(step_name, **log_ctx):
            yield
        success = True
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        elapsed = time.perf_counter() - t0
        if session is not None:
            resolved_method = timing_state.method_id if timing_state is not None else method_id
            resolved_backend = timing_state.backend if timing_state is not None else backend
            session.record(
                BakeMapTiming(
                    map_id=map_id,
                    method_id=resolved_method,
                    backend=resolved_backend,
                    width=width,
                    height=height,
                    seconds=elapsed,
                    success=success,
                    error=error,
                    internal_prerequisite=internal_prerequisite,
                    group_name=group_name,
                ),
            )


def _format_summary_header(session: BakeTimingSession) -> str:
    if session.run_kind == RUN_KIND_SINGLE_MAP:
        return 'bake timing summary (single map)'
    return 'bake timing summary (project)'


def _count_outcomes(records: list[BakeMapTiming]) -> tuple[int, int]:
    ok = sum(1 for row in records if row.success)
    failed = len(records) - ok
    return ok, failed


def format_bake_timing_summary(session: BakeTimingSession) -> list[str]:
    """Return human-readable summary lines (longest map bakes first)."""
    records = sorted(session.records, key=lambda row: row.seconds, reverse=True)
    ok, failed = _count_outcomes(records)
    lines: list[str] = [
        f'=== {_format_summary_header(session)} ===',
        f'total wall: {session.wall_seconds:.2f}s | maps: {ok} ok, {failed} failed',
    ]
    if not records:
        lines.append('  (no map bakes recorded)')
        return lines

    if session.run_kind == RUN_KIND_SINGLE_MAP and len(records) == 1:
        row = records[0]
        status = 'ok' if row.success else 'FAIL'
        method_label = method_display_label(row.method_id) if row.method_id else '-'
        lines.append(
            f'  {row.map_id} | {method_label} | {row.backend} | '
            f'{row.width}x{row.height} | {status} | {row.seconds:.2f}s',
        )
        if row.error:
            lines.append(f'  error: {row.error}')
        return lines

    lines.append(
        f'  {"map_id":<18} {"method":<22} {"backend":<8} {"resolution":<12} {"status":<6} time',
    )
    for row in records:
        status = 'ok' if row.success else 'FAIL'
        method_label = method_display_label(row.method_id) if row.method_id else '-'
        resolution = f'{row.width}x{row.height}'
        prefix = '  '
        if row.internal_prerequisite:
            prefix = '* '
        lines.append(
            f'{prefix}{row.map_id:<18} {method_label:<22} {row.backend:<8} '
            f'{resolution:<12} {status:<6} {row.seconds:.2f}s',
        )
        if row.error:
            lines.append(f'    error: {row.error}')
    if any(row.internal_prerequisite for row in records):
        lines.append('  * internal prerequisite step')
    return lines


def log_bake_timing_summary(
    session: BakeTimingSession,
    *,
    project=None,
    map_id: str | None = None,
) -> None:
    """Print timing summary lines through the bake debug log channel."""
    if not BAKE_DEBUG:
        return
    for line in format_bake_timing_summary(session):
        log_step(line, project=project, map_id=map_id)


def coerce_timing_report_directory(resolved: Path) -> Path | None:
    """Normalize an absolute path to a directory for ``bake_timing.json``."""
    path = resolved
    if path.suffix.lower() == '.json':
        path = path.parent
    if not str(path).strip():
        return None
    if os.name == 'nt' and str(resolved).startswith('\\\\') and len(resolved.parts) <= 1:
        return None
    if not path.is_absolute():
        return None
    if os.name == 'nt' and not str(path).startswith('\\\\?\\') and not path.drive:
        return None
    return path


def resolve_timing_report_directory(output_dir: str | Path) -> Path | None:
    """Resolve ``project.output_dir`` to a local directory for timing reports."""
    raw = str(output_dir).strip()
    if not raw:
        return None
    try:
        path_candidate = output_dir if isinstance(output_dir, Path) else Path(raw)
        if path_candidate.is_absolute() and not raw.startswith('//'):
            resolved = path_candidate
        else:
            from lks_baker.shared_utilities.filepath_helpers import (
                get_abspath_from_relpath,
            )

            resolved = get_abspath_from_relpath(raw)
    except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError):
        return None
    return coerce_timing_report_directory(resolved)


def write_bake_timing_report(
    output_dir: str | Path,
    session: BakeTimingSession,
) -> Path | None:
    """Write structured timing JSON under the project output directory."""
    dir_path = resolve_timing_report_directory(output_dir)
    if dir_path is None:
        return None
    path = dir_path / BAKE_TIMING_REPORT_FILENAME
    ok, failed = _count_outcomes(session.records)
    payload = {
        'run_kind': session.run_kind,
        'project_name': session.project_name,
        'map_id_filter': session.map_id_filter,
        'wall_seconds': round(session.wall_seconds, 4),
        'maps_ok': ok,
        'maps_failed': failed,
        'maps': [
            {**asdict(row), 'seconds': round(row.seconds, 4)}
            for row in sorted(session.records, key=lambda item: item.seconds, reverse=True)
        ],
    }
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    except OSError:
        return None
    return path


def finalize_bake_timing(
    session: BakeTimingSession,
    *,
    project=None,
    map_id: str | None = None,
) -> None:
    """Log console summary and optionally persist JSON when output_dir is set."""
    log_bake_timing_summary(session, project=project, map_id=map_id)
    output_dir = getattr(project, 'output_dir', '') if project is not None else ''
    if not output_dir:
        return
    report_path = write_bake_timing_report(output_dir, session)
    if report_path is not None:
        log_step(f'timing report -> {report_path}', project=project, map_id=map_id)
    elif output_dir.strip():
        print(
            f'{_PREFIX} timing report skipped — invalid output directory: {output_dir!r}',
            flush=True,
        )

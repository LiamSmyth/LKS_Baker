"""Timestamped progress logging for Blender test runs."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_START = time.perf_counter()
_RECORDING = False
_RECORDS: list[dict[str, Any]] = []


def log(message: str) -> None:
    """Log.

    Args:
        message: ``str`` value.
    """
    elapsed = time.perf_counter() - _START
    line = f"[bake_engine +{elapsed:7.2f}s] {message}"
    print(line, flush=True)


def log_exception(context: str, exc: BaseException) -> None:
    """Log exception.

    Args:
        context: Blender context or bake context object.
        exc: ``BaseException`` value.
    """
    log(f"ERROR in {context}: {type(exc).__name__}: {exc}")


def begin_performance_recording() -> None:
    """Start collecting timed_step durations (for suite reports)."""
    global _RECORDING, _RECORDS
    _RECORDING = True
    _RECORDS = []


def end_performance_recording() -> list[dict[str, Any]]:
    """Stop collecting and return recorded step timings."""
    global _RECORDING
    _RECORDING = False
    return list(_RECORDS)


def write_performance_report(path: str | Path, *, extra: dict[str, Any] | None = None) -> None:
    """Write collected timings plus optional metadata as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"steps": list(_RECORDS)}
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@contextmanager
def timed_step(name: str):
    """Timed step.

    Args:
        name: ``str`` value.

    Returns:
        ``Any`` result.
    """
    log(f"BEGIN {name}")
    step_start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        log_exception(name, exc)
        raise
    finally:
        elapsed = time.perf_counter() - step_start
        log(f"END {name} ({elapsed:.2f}s)")
        if _RECORDING:
            _RECORDS.append({"step": name, "seconds": round(elapsed, 4)})


def log_progress(label: str, current: int, total: int, *, every: int = 10000) -> None:
    """Log progress.

    Args:
        label: ``str`` value.
        current: ``int`` value.
        total: ``int`` value.
    """
    if total <= 0:
        return
    if current == 0 or current >= total or (every > 0 and current % every == 0):
        pct = 100.0 * current / total
        log(f"{label}: {current}/{total} ({pct:.1f}%)")

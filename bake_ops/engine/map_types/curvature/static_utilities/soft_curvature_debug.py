"""Debug timing + hard timebox for soft_curvature bakes (dev profiling)."""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from lks_baker.bake_ops.engine.static_utilities.runtime_log import log

_DEFAULT_TIMEBOX_SECONDS = 10.0
_active: DebugTimebox | None = None


def _timebox_seconds() -> float | None:
    raw = os.environ.get("LKS_SOFT_CURVATURE_TIMEBOX", "10").strip()
    if raw in ("0", "off", "false", "no"):
        return None
    try:
        return max(0.1, float(raw))
    except ValueError:
        return _DEFAULT_TIMEBOX_SECONDS


class DebugTimebox:
    """Hard deadline — ``os._exit(1)`` when expired (Windows-safe)."""

    def __init__(self, label: str, seconds: float) -> None:
        self.label = label
        self.seconds = seconds
        self.start = time.perf_counter()
        self.deadline = self.start + seconds
        self._timer = threading.Timer(seconds, self._force_exit)
        self._timer.daemon = True
        self._timer.start()
        log(f"soft_curvature TIMEBOX start: {label} ({seconds:.1f}s max)")

    def _force_exit(self) -> None:
        elapsed = time.perf_counter() - self.start
        log(
            f"soft_curvature TIMEBOX EXPIRED: {self.label} after {elapsed:.2f}s "
            f"(limit {self.seconds:.1f}s) — force exit"
        )
        os._exit(1)

    def checkpoint(self, message: str) -> None:
        elapsed = time.perf_counter() - self.start
        log(f"soft_curvature DEBUG [{elapsed:6.2f}s] {message}")
        if time.perf_counter() >= self.deadline:
            self._force_exit()

    def cancel(self) -> None:
        self._timer.cancel()
        elapsed = time.perf_counter() - self.start
        log(f"soft_curvature TIMEBOX ok: {self.label} finished in {elapsed:.2f}s")


@contextmanager
def soft_curvature_timebox(label: str) -> Iterator[DebugTimebox | None]:
    """Optional hard timebox when ``LKS_SOFT_CURVATURE_TIMEBOX`` is enabled (default 10s)."""
    global _active
    seconds = _timebox_seconds()
    if seconds is None:
        log(f"soft_curvature DEBUG: {label} (timebox disabled)")
        yield None
        return

    box = DebugTimebox(label, seconds)
    _active = box
    try:
        yield box
    finally:
        box.cancel()
        _active = None


def soft_curvature_debug(message: str) -> None:
    """Print a timestamped debug line; enforce timebox if active."""
    if _active is not None:
        _active.checkpoint(message)
    else:
        log(f"soft_curvature DEBUG: {message}")

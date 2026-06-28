"""Verbose tracing for deep-apply geometry prep. Toggle DEEP_APPLY_DEBUG off when done."""

from __future__ import annotations

DEEP_APPLY_DEBUG = True
_PREFIX = '[LKS DeepApply]'
_PASS_PREFIX = '[LKS DeepPass]'

_last_stage = 'idle'
_last_detail = ''


def enabled() -> bool:
    return DEEP_APPLY_DEBUG


def last_status() -> tuple[str, str]:
    return _last_stage, _last_detail


def log(msg: str, *, stage: str | None = None) -> None:
    global _last_stage, _last_detail
    if stage is not None:
        _last_stage = stage
    _last_detail = msg
    if DEEP_APPLY_DEBUG:
        print(f'{_PREFIX} {msg}', flush=True)


def log_objects(label: str, objects: list, *, stage: str | None = None) -> None:
    names = [getattr(obj, 'name', repr(obj)) for obj in objects]
    log(f'{label}: {names or "(none)"}', stage=stage)


def log_pass(
    phase: str,
    msg: str,
    *,
    objects: list | None = None,
) -> None:
    """Boundary log for a single deep-apply phase pass."""
    if not DEEP_APPLY_DEBUG:
        return
    suffix = ''
    if objects is not None:
        names = [getattr(obj, 'name', repr(obj)) for obj in objects]
        suffix = f' objects={names or "(none)"}'
    print(f'{_PASS_PREFIX} {phase}: {msg}{suffix}', flush=True)


def reset_status() -> None:
    global _last_stage, _last_detail
    _last_stage = 'start'
    _last_detail = ''

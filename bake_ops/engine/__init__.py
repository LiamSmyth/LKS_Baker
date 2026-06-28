"""Bake orchestration and map-type implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import BakeEngine, BakeRequest, BakeResult
    from .registry import list_bake_maps, resolve_bake_map

__all__ = [
    "BakeEngine",
    "BakeRequest",
    "BakeResult",
    "list_bake_maps",
    "resolve_bake_map",
]


def __getattr__(name: str):
    if name in {"BakeEngine", "BakeRequest", "BakeResult"}:
        from .orchestrator import BakeEngine, BakeRequest, BakeResult

        return locals()[name]
    if name in {"list_bake_maps", "resolve_bake_map"}:
        from .registry import list_bake_maps, resolve_bake_map

        return locals()[name]
    raise AttributeError(name)

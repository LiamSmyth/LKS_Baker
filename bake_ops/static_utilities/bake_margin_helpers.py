"""Bake image margin resolution for post-bake dilate (Cycles margin is always 0).

Effective margin semantics (after resolving per-map override vs project default)
-------------------------------------------------------------------------------
- ``0``   — no dilation; skip dilate post-process entirely.
- ``-1``  — infinite dilation; BFS fill to image bounds (``max(w, h)`` iters).
- ``N > 0`` — dilate by exactly N pixels outward (BFS).

Per-map ``margin`` RNA: ``0`` = use ``project.default_bake_margin`` (same pattern
as samples/resolution). Any non-zero value is an explicit override.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_baker.bake_ops.engine.image_filters.dilate_cpu import DilateConfig

# Keep in sync with ``lks_constants`` (standalone import for pure tests).
BAKE_MARGIN_DEFAULT = 16
BAKE_MARGIN_NONE = 0
BAKE_MARGIN_INFINITE = -1
BAKE_MARGIN_PRE_ERODE_DEFAULT = 3
"""Default seed-mask shrink (px) before dilate; trims aliased UV rim texels."""
BAKE_MARGIN_PRE_ERODE_OFF = 0
"""Per-map ``0`` inherits ``project.default_bake_margin_pre_erode``."""
BAKE_CYCLES_MARGIN_CAP = 64

# Legacy internal dilate sign: negative ``margin_adjust`` = erode inward.
BAKE_MARGIN_ADJUST_DEFAULT = -BAKE_MARGIN_PRE_ERODE_DEFAULT


def resolve_effective_margin(map_entry, project=None) -> int:
    """Return raw margin after per-map override vs project-default resolution.

    Per-map ``margin == 0`` inherits ``project.default_bake_margin`` (or 16 when
    no project). Non-zero per-map values are explicit overrides (including ``-1``).
    """
    if map_entry is not None and int(getattr(map_entry, 'margin', 0)) != 0:
        return int(map_entry.margin)
    if project is not None:
        return int(getattr(project, 'default_bake_margin', BAKE_MARGIN_DEFAULT))
    return BAKE_MARGIN_DEFAULT


def resolve_dilate_pixels(map_entry, project=None) -> int | None:
    """Return ``DilateConfig.dilate_pixels`` value, or ``None`` to skip dilation.

    Effective margin:
    - ``0``   — no dilation (returns ``None``)
    - ``-1``  — infinite fill (returns ``-1``)
    - ``N > 0`` — explicit pixel margin (returns ``N``)
    """
    margin = resolve_effective_margin(map_entry, project)
    if margin == 0:
        return None
    if margin < 0:
        return -1
    return int(margin)


def resolve_bake_margin_pixels(
    map_entry,
    width: int,
    height: int,
    project=None,
) -> int:
    """Return effective post-dilate iteration count for display and TBN gating.

    Returns ``0`` when dilation is disabled (effective margin=0).
    Returns ``max(width, height)`` for infinite margin (effective margin=-1).
    Returns ``N`` for an explicit N-pixel margin.
    """
    dilate_pixels = resolve_dilate_pixels(map_entry, project)
    if dilate_pixels is None:
        return 0
    if dilate_pixels < 0:
        return max(width, height)
    return dilate_pixels


def resolve_margin_pre_erode_pixels(map_entry, project=None) -> int:
    """Return dilate seed-mask shrink in pixels (``0`` = no pre-erode).

    Per-map ``lks_bake_margin_pre_erode == 0`` inherits
    ``project.default_bake_margin_pre_erode``. Legacy per-map
    ``lks_bake_margin_adjust < 0`` is treated as ``abs(value)`` pixels.
    """
    if map_entry is not None:
        pre_erode = int(getattr(map_entry, 'lks_bake_margin_pre_erode', BAKE_MARGIN_PRE_ERODE_OFF))
        if pre_erode > 0:
            return pre_erode
        legacy_adjust = int(getattr(map_entry, 'lks_bake_margin_adjust', 0))
        if legacy_adjust < 0:
            return abs(legacy_adjust)
        if pre_erode == BAKE_MARGIN_PRE_ERODE_OFF and legacy_adjust > 0:
            return BAKE_MARGIN_PRE_ERODE_OFF
    if project is not None:
        return int(
            getattr(project, 'default_bake_margin_pre_erode', BAKE_MARGIN_PRE_ERODE_DEFAULT)
        )
    return BAKE_MARGIN_PRE_ERODE_DEFAULT


def resolve_margin_adjust(map_entry, project=None) -> int:
    """Map UI pre-erode pixels to internal ``DilateConfig.margin_adjust``."""
    pre_erode = resolve_margin_pre_erode_pixels(map_entry, project)
    if pre_erode <= 0:
        return 0
    return -pre_erode


def resolve_dilate_config(
    map_entry,
    width: int,
    height: int,
    project=None,
) -> DilateConfig | None:
    """Build ``DilateConfig`` from resolved margin, or ``None`` to skip dilation."""
    from lks_baker.bake_ops.engine.image_filters.dilate_cpu import DilateConfig

    dilate_pixels = resolve_dilate_pixels(map_entry, project)
    if dilate_pixels is None:
        return None
    return DilateConfig(
        dilate_pixels=dilate_pixels,
        margin_adjust=resolve_margin_adjust(map_entry, project),
        dilate_alpha=True,
    )


def resolve_cycles_bake_margin_pixels(margin_pixels: int) -> int:
    """Cycles native bake margin — always zero; post-bake dilate fills padding."""
    return 0

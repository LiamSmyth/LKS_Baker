"""Engine-agnostic bake job request/result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .planner import LKS_BakeJobStep


@dataclass
class MapBakeConfig:
    """Per-map bake configuration inside a ``BakeJobRequest``.

    Attributes:
        map_id: Catalog map identifier.
        enabled: When False the planner skips this map.
        backend_preference: ``"AUTO"``, ``"mesh"``, or ``"derive"`` export path hint.
        method_id: Optional engine method override for derive maps.
        device: Registry device preference (``"auto"``, ``"cpu"``, ``"gpu"``).
        settings: Method-specific settings dict passed to derive runners.
    """

    map_id: str
    enabled: bool = True
    backend_preference: str = "AUTO"
    method_id: str | None = None
    device: str = "auto"
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class BakeJobRequest:
    """High-level bake job description for the engine planner/runner.

    Attributes:
        project_name: Export project / group name used for output paths.
        output_dir: Root directory for baked textures.
        texture_stem: Filename stem shared by map outputs.
        map_configs: Explicit per-map configs; preferred over ``map_ids``.
        map_ids: Legacy/simple list of map ids when configs omitted.
        force_recook: Re-run all maps even when outputs exist.
        force_recook_maps: Subset of map ids to force refresh.
        reuse_existing_dependencies: Skip prerequisite steps when inputs already on disk.
    """

    project_name: str
    output_dir: str
    texture_stem: str
    map_configs: list[MapBakeConfig] = field(default_factory=list)
    map_ids: list[str] | None = None
    force_recook: bool = False
    force_recook_maps: frozenset[str] = frozenset()
    reuse_existing_dependencies: bool = True


@dataclass
class PlannedStep:
    """One compiled planner step ready for execution or skip reporting.

    Attributes:
        map_id: Target catalog map id.
        method_id: Engine method id when derive-backed.
        device: Resolved registry device when applicable.
        execution_kind: ``"mesh"`` or ``"derive"`` execution category.
        backend: Compiler backend label (``"mesh"`` / ``"derive"``).
        internal_prerequisite: True for auto-injected dependency steps.
        skip_reason: Human-readable reason when the step is skipped.
        compiler_step: Original ``LKS_BakeJobStep`` when available.
    """

    map_id: str
    method_id: str | None
    device: str | None
    execution_kind: str
    backend: str
    internal_prerequisite: bool
    skip_reason: str | None = None
    compiler_step: LKS_BakeJobStep | None = None


@dataclass
class BakeJobResult:
    """Aggregate outcome after running a compiled bake job.

    Attributes:
        steps_run: Ordered list of executed or skipped ``PlannedStep`` records.
        outputs: Map id → output file path for successful writes.
        errors: Non-fatal error messages collected during the job.
    """

    steps_run: list[PlannedStep]
    outputs: dict[str, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

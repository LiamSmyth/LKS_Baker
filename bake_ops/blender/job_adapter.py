"""Blender boundary — compile jobs and execute bakes."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..engine.job_types import BakeJobRequest, BakeJobResult, MapBakeConfig, PlannedStep
from ..engine.planner import compile_bake_job_steps, resolve_map_backend_preference
from ..static_utilities.bake_method_catalog import resolve_map_entry_bake_method
from .cycles_executor import LKS_BakeGroupMeshes, LKS_BakedMapResult, execute_bake_groups

if TYPE_CHECKING:
    import bpy

    from ..lks_bake_props import LKS_PG_BakeProject


def build_bake_job_request(
    project: LKS_PG_BakeProject,
    *,
    map_ids: list[str] | None = None,
    reuse_existing_dependencies: bool = True,
) -> BakeJobRequest:
    map_configs: list[MapBakeConfig] = []
    for entry in project.map_entries:
        method_id = resolve_map_entry_bake_method(entry)
        map_configs.append(
            MapBakeConfig(
                map_id=entry.map_id,
                enabled=entry.enabled,
                backend_preference=resolve_map_backend_preference(entry),
                method_id=method_id or None,
                device='auto',
            ),
        )
    return BakeJobRequest(
        project_name=project.name,
        output_dir=project.output_dir,
        texture_stem=project.name,
        map_configs=map_configs,
        map_ids=map_ids,
        reuse_existing_dependencies=reuse_existing_dependencies,
        force_recook=not reuse_existing_dependencies,
    )


def planned_steps_from_project(
    project: LKS_PG_BakeProject,
    group_name: str,
    *,
    map_ids: list[str] | None = None,
    require_enabled: bool = True,
    reuse_existing_dependencies: bool = False,
) -> list[PlannedStep]:
    compiler_steps = compile_bake_job_steps(
        project,
        group_name,
        map_ids=map_ids,
        require_enabled=require_enabled,
        reuse_existing_dependencies=reuse_existing_dependencies,
    )
    planned: list[PlannedStep] = []
    for step in compiler_steps:
        execution_kind = (
            'derive_2d' if step.backend == 'derive'
            else 'engine_compute' if step.backend == 'engine'
            else 'cycles_raycast'
        )
        planned.append(
            PlannedStep(
                map_id=step.map_id,
                method_id=None,
                device=None,
                execution_kind=execution_kind,
                backend=step.backend,
                internal_prerequisite=step.internal_prerequisite,
                compiler_step=step,
            ),
        )
    return planned


def execute_bake_job(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group_meshes: list[LKS_BakeGroupMeshes],
    *,
    map_ids: list[str] | None = None,
    require_enabled: bool = True,
    reuse_existing_dependencies: bool = False,
) -> list[LKS_BakedMapResult]:
    """Compile via engine planner, execute via Cycles/derive executor."""
    _ = build_bake_job_request(
        project,
        map_ids=map_ids,
        reuse_existing_dependencies=reuse_existing_dependencies,
    )
    return execute_bake_groups(
        context,
        project,
        group_meshes,
        map_ids=map_ids,
        require_enabled=require_enabled,
        reuse_existing_dependencies=reuse_existing_dependencies,
    )

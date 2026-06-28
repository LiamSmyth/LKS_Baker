"""Bake project orchestration — export prep geometry, Cycles bake, preview material."""

from __future__ import annotations

import bpy

from ..shared_utilities import object_helpers
from .blender.cycles_executor import LKS_BakeGroupMeshes, LKS_BakedMapResult
from .blender.job_adapter import execute_bake_job as execute_bake_groups
from .static_utilities.bake_view_layer_helpers import (
    ensure_bake_project_visible,
    ensure_bake_targets_visible,
    ensure_objects_in_active_view_layer,
    make_objects_visible_for_bake,
    restore_bake_visibility,
)
from .static_utilities.bake_map_catalog import seed_bake_project_map_entries_if_needed
from .static_utilities.bake_preview_material_helpers import (
    enable_solo_map_preview,
    merge_project_baked_results_cache,
    nudge_viewport_material_shading,
    refresh_project_low_material_composite,
)
from .static_utilities.bake_debug_log_helpers import log_step, timed_step
from .static_utilities.bake_texture_derivatives import BakeMapSkipped
from .static_utilities.bake_progress_helpers import (
    BakeProgressCancelled,
    bake_progress_report,
    bake_progress_session,
    estimate_bake_step_count,
)
from .static_utilities.bake_lowpoly_visibility_helpers import (
    temporary_suppress_lowpoly_render_influence,
)
from .static_utilities.bake_viewport_shading_helpers import (
    temporary_preserve_viewport_shading,
)
from .static_utilities.bake_timing_helpers import (
    RUN_KIND_PROJECT,
    RUN_KIND_SINGLE_MAP,
    bake_timing_session,
    finalize_bake_timing,
)
from ..shared_utilities.mesh_uv_helpers import consolidate_uv_layers_for_bake
from .helpers_bake_cleanup import (
    delete_bake_pipeline_artifacts_for_project,
    get_low_collections,
    iter_bake_group_low_objects,
    iter_bake_project_collections,
    iter_bake_project_low_objects,
    iter_bake_project_objects,
)
from .helpers_bake_prep import (
    bake_group_high_has_flatten_geometry,
    bake_group_low_has_flatten_geometry,
    generate_extracted_highpoly_for_bake_project,
    generate_merged_lowpoly_for_bake_project,
)
from .lks_bake_props import LKS_PG_BakeGroup, LKS_PG_BakeProject


def bake_group_is_bakable(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bool:
    """True when group has flattenable geometry on both high and low roles."""
    return (
        bake_group_low_has_flatten_geometry(project, group)
        and bake_group_high_has_flatten_geometry(project, group)
    )


def bake_project_has_bakable_groups(project: LKS_PG_BakeProject) -> bool:
    """True when the project has flattenable low and high geometry across its groups."""
    has_low = any(
        bake_group_low_has_flatten_geometry(project, group)
        for group in project.bake_groups
    )
    has_high = any(
        bake_group_high_has_flatten_geometry(project, group)
        for group in project.bake_groups
    )
    return has_low and has_high


def _fallback_project_low_meshes(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    meshes: list[bpy.types.Object] = []
    seen: set[str] = set()
    for group in project.bake_groups:
        if not bake_group_low_has_flatten_geometry(project, group):
            continue
        for obj in iter_bake_group_low_objects(project, group):
            if obj.type != 'MESH' or obj.name in seen:
                continue
            seen.add(obj.name)
            meshes.append(obj)
    return meshes


def _fallback_project_high_meshes(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    from .helpers_bake_cleanup import iter_bake_group_high_objects

    meshes: list[bpy.types.Object] = []
    seen: set[str] = set()
    for group in project.bake_groups:
        if not bake_group_high_has_flatten_geometry(project, group):
            continue
        for obj in iter_bake_group_high_objects(project, group):
            if obj.type != 'MESH' or obj.name in seen:
                continue
            seen.add(obj.name)
            meshes.append(obj)
    return meshes


def _resolve_project_bake_meshes(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
) -> LKS_BakeGroupMeshes | None:
    """Project-wide merged low + extracted highs for one texture-set bake."""
    with timed_step('merged lowpoly', project=project):
        merged = generate_merged_lowpoly_for_bake_project(context, project)
    with timed_step('extracted highpoly', project=project):
        extracted = generate_extracted_highpoly_for_bake_project(context, project)

    low_meshes: list[bpy.types.Object] = []
    if merged is not None:
        low_meshes.append(merged)
    else:
        low_meshes = _fallback_project_low_meshes(project)

    high_meshes = list(extracted) if extracted else _fallback_project_high_meshes(project)

    targets = LKS_BakeGroupMeshes(
        group_name=project.name,
        low_meshes=low_meshes,
        high_meshes=high_meshes,
    )
    if not targets.is_bakable:
        return None
    low_names = [obj.name for obj in low_meshes]
    high_names = [obj.name for obj in high_meshes]
    log_step(
        f'resolved low={low_names} high={high_names}',
        project=project,
    )
    return targets


def _collect_project_low_collections(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Collection]:
    """Unique low-role collections across all bake groups in ``project``."""
    seen: set[str] = set()
    collections: list[bpy.types.Collection] = []
    for group in project.bake_groups:
        for coll in get_low_collections(project, group):
            if coll.name in seen:
                continue
            seen.add(coll.name)
            collections.append(coll)
    return collections


def _bake_target_low_names(
    low_meshes: list[bpy.types.Object],
) -> set[str]:
    """Active low bake targets plus parented descendants (merged low subtree)."""
    roots = object_helpers.filter_valid_objects(low_meshes)
    return {
        obj.name
        for obj in object_helpers.collect_objects_in_subtrees(roots)
    }


def _collect_bake_target_objects(
    project_meshes: LKS_BakeGroupMeshes,
) -> list[bpy.types.Object]:
    """All low/high mesh targets resolved for Cycles bake."""
    objects: list[bpy.types.Object] = []
    seen: set[str] = set()
    for obj in project_meshes.low_meshes + project_meshes.high_meshes:
        if obj.name in seen:
            continue
        seen.add(obj.name)
        objects.append(obj)
    return objects


def _collect_project_low_roots(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    """Low role forest roots across all groups that contributed flattenable geometry."""
    roots: list[bpy.types.Object] = []
    for group in project.bake_groups:
        if not bake_group_low_has_flatten_geometry(project, group):
            continue
        low_objects = iter_bake_group_low_objects(project, group)
        roots.extend(object_helpers.collect_hierarchy_forest_roots(low_objects))
    return roots


collect_project_low_roots = _collect_project_low_roots


def refresh_bake_project_low_material(
    scene: bpy.types.Scene,
    project,
) -> int:
    """Re-wire project low material from on-disk bakes (or solo preview when active)."""
    low_roots = _collect_project_low_roots(project)
    return refresh_project_low_material_composite(project, low_roots, scene)


def refresh_all_bake_projects_low_material(scene: bpy.types.Scene) -> int:
    """Refresh low-material composite wiring for every bake project in ``scene``."""
    total = 0
    for project in scene.lks_bake_projects:
        total += refresh_bake_project_low_material(scene, project)
    return total


def _mark_project_groups_baked(project: LKS_PG_BakeProject) -> None:
    for group in project.bake_groups:
        if (
            bake_group_low_has_flatten_geometry(project, group)
            or bake_group_high_has_flatten_geometry(project, group)
        ):
            group.status_baked = True


def _update_preview_material_after_bake(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    baked_results: list[LKS_BakedMapResult] | None = None,
) -> None:
    """Reassemble full composite preview from this run's bake outputs."""
    low_roots = _collect_project_low_roots(project)
    if not low_roots:
        return

    with timed_step('preview material update', project=project):
        if baked_results is not None:
            mesh_count = refresh_project_low_material_composite(
                project,
                low_roots,
                context.scene,
                baked_results=baked_results,
            )
        else:
            mesh_count = refresh_bake_project_low_material(context.scene, project)
        nudge_viewport_material_shading(context)
        log_step(
            f'reassembled preview material on {mesh_count} low mesh(es)',
            project=project,
        )


def _enable_solo_preview_after_map_bake(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    map_id: str,
) -> None:
    """Enter solo eyeball preview for the map that was just baked."""
    low_roots = _collect_project_low_roots(project)
    if not low_roots:
        return

    with timed_step('solo preview after map bake', project=project, map_id=map_id):
        if enable_solo_map_preview(context, project, map_id, low_roots):
            log_step(
                f'enabled solo preview for {map_id}',
                project=project,
                map_id=map_id,
            )
            return

        log_step(
            f'solo preview unavailable for {map_id}; restoring composite',
            project=project,
            map_id=map_id,
        )
        project.lks_preview_map_id = ''
        _update_preview_material_after_bake(context, project)


def run_bake_project(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
) -> list[LKS_BakedMapResult]:
    """
    Full bake flow: seed maps, project-wide prep meshes, Cycles bake, preview material.

    One bake project = one texture set: all group lows merge to one target; all group
    highs are extracted as bake sources. Bakes all enabled implemented catalog maps.
    """
    if not project.output_dir:
        raise RuntimeError('Bake project output directory is not set')
    if len(project.bake_groups) == 0:
        raise RuntimeError('Bake project has no bake groups')

    collections = iter_bake_project_collections(project)
    project_objects = iter_bake_project_objects(project)
    visibility_snapshot = None

    step_budget = estimate_bake_step_count(project, project.name, require_enabled=True)
    with temporary_preserve_viewport_shading(context):
        with bake_timing_session(project=project, run_kind=RUN_KIND_PROJECT) as timing:
            try:
                with bake_progress_session(context, total_steps=step_budget):
                    with timed_step('bake project', project=project):
                        try:
                            bake_progress_report('Preparing scene visibility…')
                            with timed_step('ensure visibility', project=project):
                                visibility_snapshot = ensure_bake_project_visible(
                                    context, collections, project_objects,
                                )
                            try:
                                with timed_step('seed map entries', project=project):
                                    seed_bake_project_map_entries_if_needed(project)
                                bake_progress_report('Building bake meshes…')
                                with timed_step('resolve bake meshes', project=project):
                                    project_meshes = _resolve_project_bake_meshes(context, project)
                                if project_meshes is None:
                                    raise RuntimeError(
                                        'No bakeable geometry — assign high and low roles with flattenable meshes',
                                    )

                                bake_targets = _collect_bake_target_objects(project_meshes)
                                bake_progress_report('Preparing UV layers…')
                                with timed_step('consolidate bake UV layers', project=project):
                                    consolidate_uv_layers_for_bake(bake_targets)
                                with timed_step('ensure bake targets visible', project=project):
                                    make_objects_visible_for_bake(iter_bake_project_objects(project))
                                    ensure_bake_targets_visible(bake_targets)
                                    ensure_objects_in_active_view_layer(context, context.scene, bake_targets)

                                bake_progress_report('Baking maps…', advance=False)
                                low_objects = iter_bake_project_low_objects(project)
                                low_collections = _collect_project_low_collections(project)
                                target_low_names = _bake_target_low_names(project_meshes.low_meshes)
                                with temporary_suppress_lowpoly_render_influence(
                                    low_objects,
                                    low_collections,
                                    bake_target_low_names=target_low_names,
                                    scene=context.scene,
                                ):
                                    with timed_step('execute bake groups', project=project):
                                        baked = execute_bake_groups(
                                            context,
                                            project,
                                            [project_meshes],
                                            require_enabled=True,
                                            reuse_existing_dependencies=False,
                                        )

                                merge_project_baked_results_cache(
                                    context.scene,
                                    project,
                                    baked,
                                    replace=True,
                                )
                                project.lks_preview_map_id = ''
                                bake_progress_report('Updating preview material…')
                                _update_preview_material_after_bake(context, project, baked)

                                _mark_project_groups_baked(project)
                                log_step(f'success — {len(baked)} map(s) baked', project=project)

                                return baked
                            finally:
                                if visibility_snapshot is not None:
                                    bake_progress_report('Restoring visibility…')
                                    with timed_step('restore visibility', project=project):
                                        restore_bake_visibility(context, visibility_snapshot)
                        finally:
                            bake_progress_report('Cleaning up pipeline artifacts…')
                            with timed_step('cleanup pipeline artifacts', project=project):
                                removed = delete_bake_pipeline_artifacts_for_project(project)
                                log_step(f'removed {removed} artifact(s)', project=project)
            except BakeProgressCancelled:
                raise RuntimeError('Bake cancelled') from None
            finally:
                finalize_bake_timing(timing, project=project)


def run_bake_project_map(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    map_id: str,
    *,
    reuse_existing_dependencies: bool = True,
) -> list[LKS_BakedMapResult]:
    """Bake a single catalog map for the active project (ignores map enabled flag)."""
    from .static_utilities.bake_blender_helpers import (
        get_map_bake_blocker,
        map_id_is_bakeable,
    )

    if not map_id_is_bakeable(map_id):
        blocker = get_map_bake_blocker(map_id) or 'map not implemented yet'
        raise RuntimeError(f"Cannot bake '{map_id}' — {blocker}")

    if not project.output_dir:
        raise RuntimeError('Bake project output directory is not set')
    if len(project.bake_groups) == 0:
        raise RuntimeError('Bake project has no bake groups')

    collections = iter_bake_project_collections(project)
    project_objects = iter_bake_project_objects(project)
    visibility_snapshot = None

    step_budget = estimate_bake_step_count(
        project,
        project.name,
        map_ids=[map_id],
        require_enabled=False,
        reuse_existing_dependencies=reuse_existing_dependencies,
    )
    with temporary_preserve_viewport_shading(context):
        with bake_timing_session(
            project=project,
            run_kind=RUN_KIND_SINGLE_MAP,
            map_id=map_id,
        ) as timing:
            try:
                with bake_progress_session(context, total_steps=step_budget):
                    with timed_step(f'bake project map {map_id}', project=project, map_id=map_id):
                        try:
                            bake_progress_report('Preparing scene visibility…')
                            with timed_step('ensure visibility', project=project, map_id=map_id):
                                visibility_snapshot = ensure_bake_project_visible(
                                    context, collections, project_objects,
                                )
                            try:
                                with timed_step('seed map entries', project=project, map_id=map_id):
                                    seed_bake_project_map_entries_if_needed(project)
                                bake_progress_report('Building bake meshes…')
                                with timed_step('resolve bake meshes', project=project, map_id=map_id):
                                    project_meshes = _resolve_project_bake_meshes(context, project)
                                if project_meshes is None:
                                    raise RuntimeError(
                                        'No bakeable geometry — assign high and low roles with flattenable meshes',
                                    )

                                bake_targets = _collect_bake_target_objects(project_meshes)
                                bake_progress_report('Preparing UV layers…')
                                with timed_step('consolidate bake UV layers', project=project, map_id=map_id):
                                    consolidate_uv_layers_for_bake(bake_targets)
                                with timed_step('ensure bake targets visible', project=project, map_id=map_id):
                                    make_objects_visible_for_bake(iter_bake_project_objects(project))
                                    ensure_bake_targets_visible(bake_targets)
                                    ensure_objects_in_active_view_layer(context, context.scene, bake_targets)

                                bake_progress_report('Baking maps…', advance=False)
                                low_objects = iter_bake_project_low_objects(project)
                                low_collections = _collect_project_low_collections(project)
                                target_low_names = _bake_target_low_names(project_meshes.low_meshes)
                                with temporary_suppress_lowpoly_render_influence(
                                    low_objects,
                                    low_collections,
                                    bake_target_low_names=target_low_names,
                                    scene=context.scene,
                                ):
                                    with timed_step('execute bake groups', project=project, map_id=map_id):
                                        baked = execute_bake_groups(
                                            context,
                                            project,
                                            [project_meshes],
                                            map_ids=[map_id],
                                            require_enabled=False,
                                            reuse_existing_dependencies=reuse_existing_dependencies,
                                        )

                                if not baked:
                                    raise BakeMapSkipped(
                                        f"Map '{map_id}' was skipped — see log for details",
                                    )

                                merge_project_baked_results_cache(context.scene, project, baked)
                                bake_progress_report('Updating preview material…')
                                _enable_solo_preview_after_map_bake(context, project, map_id)

                                _mark_project_groups_baked(project)
                                log_step(
                                    f'success — {len(baked)} map(s) baked',
                                    project=project,
                                    map_id=map_id,
                                )

                                return baked
                            finally:
                                if visibility_snapshot is not None:
                                    bake_progress_report('Restoring visibility…')
                                    with timed_step('restore visibility', project=project, map_id=map_id):
                                        restore_bake_visibility(context, visibility_snapshot)
                        finally:
                            bake_progress_report('Cleaning up pipeline artifacts…')
                            with timed_step('cleanup pipeline artifacts', project=project, map_id=map_id):
                                removed = delete_bake_pipeline_artifacts_for_project(project)
                                log_step(
                                    f'removed {removed} artifact(s)',
                                    project=project,
                                    map_id=map_id,
                                )
            except BakeProgressCancelled:
                raise RuntimeError('Bake cancelled') from None
            finally:
                finalize_bake_timing(timing, project=project, map_id=map_id)

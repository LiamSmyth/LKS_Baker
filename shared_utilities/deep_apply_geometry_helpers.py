"""Generic hierarchy flatten, attribute sync, and deep-apply orchestration."""

from __future__ import annotations

from collections.abc import Callable

import bpy
from mathutils import Vector

from . import mesh_helpers, object_helpers
from .mesh_attribute_sync_helpers import sync_mesh_attributes_for_join
from .deep_apply_debug import (
    log as _deep_apply_log,
    log_objects as _deep_apply_log_objects,
    log_pass as _deep_pass_log,
    reset_status as _deep_apply_reset_status,
)
from .grouppro_helpers import (
    is_exportable_grouppro_group,
    is_grouppro_mesh_group,
    is_grouppro_placeholder_object,
    is_legacy_grouppro_collection_instance,
)
from .hierarchy_flatten_helpers import (
    duplicate_objects_for_hierarchy_flatten,
    flatten_hierarchy_to_world_meshes,
    remove_grouppro_placeholder_objects,
)
from .collection_instance_helpers import is_colinst_object
from .deep_geometry_phase_helpers import (
    bake_collection_instances_for_roots,
    bake_geonodes_collection_instances_for_roots,
    deep_apply_modifiers,
    deep_triangulate_meshes,
    deep_uv_unstack,
    deep_uniquify_geometry,
    move_objects_to_scene_collection,
)
from .selection_preserve_helpers import reselect_objects
_DEEP_APPLY_PREVIEW_KEY = 'lks_deep_apply_preview'
_DEEP_APPLY_DUPLICATE_SUFFIX = '_applied'
_WORK_SCENE_PREFIX = '_LKS_DeepApply'


def duplicate_objects_preserving_hierarchy(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    target_collection: bpy.types.Collection,
    *,
    preserve_modifiers: bool = False,
) -> list[bpy.types.Object]:
    """Duplicate forest roots for flatten; export-style unique instance hierarchies."""
    return duplicate_objects_for_hierarchy_flatten(
        context,
        objects,
        target_collection,
        preserve_modifiers=preserve_modifiers,
    )


def _filtered_scene_meshes(
    scene: bpy.types.Scene,
    object_filter: set[str] | None,
) -> list[bpy.types.Object]:
    meshes = object_helpers.filter_mesh_objects(scene.objects)
    if object_filter is not None:
        meshes = [obj for obj in meshes if obj.name in object_filter]
    return [obj for obj in meshes if not is_grouppro_placeholder_object(obj)]


def flatten_geometry(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    *,
    object_filter: set[str] | None = None,
    uvset_count: int | None = None,
    vcol_count: int | None = None,
    phase_uniquify: bool = True,
    phase_uv_unstack: bool = True,
    phase_flatten_hierarchy: bool = True,
    phase_sync_attributes: bool = False,
    phase_apply_modifiers: bool = True,
    phase_triangulate: bool = True,
    phase_bake_collection_instances: bool = True,
    phase_cleanup_non_geometry: bool = False,
    link_to_scene_collection: bool = False,
    uniquify_roots: list[bpy.types.Object] | None = None,
) -> list[bpy.types.Object]:
    """
    Run deep-apply geometry phases on scene objects.

    Pipeline: uniquify → uv unstack → apply modifiers → triangulate → flatten → sync attributes.
    """
    if phase_uniquify and uniquify_roots:
        deep_uniquify_geometry(context, uniquify_roots)

    if phase_uv_unstack:
        meshes_for_uv = _filtered_scene_meshes(scene, object_filter)
        uv_roots = uniquify_roots or object_helpers.collect_hierarchy_forest_roots(
            meshes_for_uv,
        )
        if uv_roots:
            deep_uv_unstack(context, uv_roots)

    if phase_apply_modifiers:
        for obj in list(_filtered_scene_meshes(scene, object_filter)):
            if obj.name not in bpy.data.objects:
                continue
            if phase_triangulate:
                mesh_helpers.remove_modifiers_of_types(obj, {'TRIANGULATE'})
            mesh_helpers.apply_visible_modifiers_delete_hidden(context, obj)

    if phase_triangulate:
        deep_triangulate_meshes(
            context, _filtered_scene_meshes(scene, object_filter),
        )

    if phase_flatten_hierarchy:
        meshes = flatten_hierarchy_to_world_meshes(
            context,
            scene,
            object_filter=object_filter,
            apply_modifiers=False,
        )
    else:
        meshes = _filtered_scene_meshes(scene, object_filter)

    if not meshes:
        return []

    if phase_sync_attributes:
        sync_mesh_attributes_for_join(
            context,
            meshes,
            uvset_count=uvset_count,
            vcol_count=vcol_count,
        )

    return meshes


def deep_apply_geometry(
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    *,
    scene: bpy.types.Scene | None = None,
    pivot: Vector | None = None,
    result_name: str | None = None,
    uvset_count: int | None = None,
    vcol_count: int | None = None,
    restrict_to_input_names: bool = True,
    join: bool = False,
    phase_uniquify: bool = True,
    phase_uv_unstack: bool = True,
    phase_flatten_hierarchy: bool = True,
    phase_sync_attributes: bool = False,
    phase_apply_modifiers: bool = True,
    phase_triangulate: bool = True,
    phase_bake_collection_instances: bool = True,
    phase_cleanup_non_geometry: bool = False,
    link_to_scene_collection: bool = False,
    uniquify_roots: list[bpy.types.Object] | None = None,
) -> bpy.types.Object | list[bpy.types.Object] | None:
    """Flatten, sync attributes, apply modifiers; optionally join."""
    valid = object_helpers.filter_valid_objects(objects)
    if not valid:
        _deep_apply_log(
            f'deep_apply_geometry: no valid input objects (got {len(objects)})',
            stage='flatten_empty',
        )
        return None if join else []

    work_scene = scene if scene is not None else context.scene
    name_filter = {obj.name for obj in valid} if restrict_to_input_names else None
    _deep_apply_log(
        f'deep_apply_geometry: scene={work_scene.name!r} '
        f'inputs={[o.name for o in valid]} '
        f'scope_names={sorted(name_filter) if name_filter else None} '
        f'restrict_to_input_names={restrict_to_input_names}',
        stage='flatten_start',
    )

    meshes = flatten_geometry(
        context,
        work_scene,
        object_filter=name_filter,
        uvset_count=uvset_count,
        vcol_count=vcol_count,
        phase_uniquify=phase_uniquify,
        phase_uv_unstack=phase_uv_unstack,
        phase_flatten_hierarchy=phase_flatten_hierarchy,
        phase_sync_attributes=phase_sync_attributes,
        phase_apply_modifiers=phase_apply_modifiers,
        phase_triangulate=phase_triangulate,
        uniquify_roots=uniquify_roots,
    )
    if not meshes:
        _deep_apply_log(
            f'flatten_geometry returned no meshes '
            f'(scene objects={[o.name for o in work_scene.objects]})',
            stage='flatten_empty',
        )
        return None if join else []

    if not join:
        return meshes

    pivot_point = pivot.copy() if pivot is not None else meshes[0].location.copy()
    mesh_helpers.merge_meshes_with_pivot(meshes, pivot_point)

    merged = context.view_layer.objects.active
    if merged is None or merged.type != 'MESH':
        return None

    if result_name:
        merged.name = result_name

    return merged


def is_flatten_hierarchy_object(obj: bpy.types.Object) -> bool:
    """Objects eligible for flatten — any hierarchy node except GP bbox shells."""
    if is_grouppro_mesh_group(obj) or is_legacy_grouppro_collection_instance(obj):
        return True
    if is_grouppro_placeholder_object(obj):
        return False
    return True


def object_has_flatten_geometry(obj: bpy.types.Object) -> bool:
    """True when obj or its descendants yield mesh geometry after flatten."""
    if is_exportable_grouppro_group(obj):
        return True
    if obj.instance_collection is not None:
        return True
    if obj.type == 'MESH' and not is_grouppro_placeholder_object(obj):
        return True
    for mesh in object_helpers.collect_all_meshes_in_hierarchy(obj):
        if mesh.type == 'MESH' and not is_grouppro_placeholder_object(mesh):
            return True
    return False


def get_selection_flatten_roots(
    context: bpy.types.Context,
) -> list[bpy.types.Object]:
    """Forest roots from current selection eligible for hierarchy flatten."""
    participants = [
        obj for obj in object_helpers.context_selected_objects(context)
        if is_flatten_hierarchy_object(obj)
    ]
    return object_helpers.collect_hierarchy_forest_roots(participants)


def selection_has_flatten_geometry(context: bpy.types.Context) -> bool:
    """True when selection includes at least one flattenable hierarchy root."""
    roots = get_selection_flatten_roots(context)
    if not roots:
        return False
    return any(object_has_flatten_geometry(root) for root in roots)


def _collection_parent(coll: bpy.types.Collection) -> bpy.types.Collection | None:
    for parent in bpy.data.collections:
        if coll.name in parent.children:
            return parent
    for scene in bpy.data.scenes:
        if coll.name in scene.collection.children:
            return scene.collection
    return None


def anchor_collection_for_objects(
    objects: list[bpy.types.Object],
    *,
    fallback: bpy.types.Collection,
) -> bpy.types.Collection:
    """Collection directly holding the most roots; falls back when unlinked."""
    counts: dict[bpy.types.Collection, int] = {}
    for obj in object_helpers.filter_valid_objects(objects):
        for coll in obj.users_collection:
            counts[coll] = counts.get(coll, 0) + 1
    if not counts:
        return fallback
    return max(counts.keys(), key=lambda coll: counts[coll])


def resolve_output_collection_for_roots(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
) -> bpy.types.Collection:
    """Collection directly holding the most roots (source collection for output)."""
    return anchor_collection_for_objects(roots, fallback=context.scene.collection)


def output_collection_report_path(coll: bpy.types.Collection) -> str:
    parent = _collection_parent(coll)
    if parent is not None:
        return f'{parent.name}/{coll.name}/'
    return f'{coll.name}/'


def _move_objects_to_collection(
    objects: list[bpy.types.Object],
    target_collection: bpy.types.Collection,
) -> None:
    for obj in object_helpers.filter_valid_objects(objects):
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        if obj.name not in target_collection.objects:
            target_collection.objects.link(obj)


def _clear_deep_apply_preview_objects(
    output_coll: bpy.types.Collection,
    *,
    keep: set[bpy.types.Object] | None = None,
) -> None:
    keep_ids = {id(obj) for obj in (keep or ())}
    removed: list[str] = []
    for obj in list(output_coll.objects):
        if id(obj) in keep_ids:
            continue
        if obj.name not in bpy.data.objects:
            continue
        if not obj.get(_DEEP_APPLY_PREVIEW_KEY):
            continue
        removed.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)
    if removed:
        _deep_apply_log(
            f'cleared {len(removed)} preview object(s) from '
            f'{output_collection_report_path(output_coll)}: {removed}',
            stage='preview_clear',
        )


def _move_objects_to_scene(
    objects: list[bpy.types.Object],
    scene: bpy.types.Scene,
) -> None:
    for obj in object_helpers.filter_valid_objects(objects):
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        if obj.name not in scene.collection.objects:
            scene.collection.objects.link(obj)


def _clear_work_scene(
    scene: bpy.types.Scene,
    *,
    pre_pipeline_object_ids: set[int],
    work_initial_ids: set[int],
) -> None:
    """Remove pipeline-owned stragglers only; never delete pre-existing non-selection objects."""
    for obj in list(scene.objects):
        if not object_helpers.is_object_alive(obj):
            continue
        oid = id(obj)
        if oid in pre_pipeline_object_ids and oid not in work_initial_ids:
            continue
        bpy.data.objects.remove(obj, do_unlink=True)


def _release_foreign_work_scene_objects(
    work_scene: bpy.types.Scene,
    original_scene: bpy.types.Scene,
    *,
    work_initial_ids: set[int],
    pre_pipeline_object_ids: set[int],
) -> None:
    """Return pre-existing scene objects that were never moved into the work pipeline."""
    foreign: list[bpy.types.Object] = []
    for obj in list(work_scene.objects):
        if not object_helpers.is_object_alive(obj):
            continue
        oid = id(obj)
        if oid in work_initial_ids:
            continue
        if oid not in pre_pipeline_object_ids:
            continue
        foreign.append(obj)
    if not foreign:
        return
    _move_objects_to_scene(foreign, original_scene)
    _deep_apply_log_objects(
        'released foreign work-scene objects to original scene',
        foreign,
        stage='foreign_release',
    )


def _is_colinst_shell_object(obj: bpy.types.Object) -> bool:
    """ColInst bake empties left after extract — not original hierarchy parents."""
    return obj.type == 'EMPTY' and '_decomposed' in obj.name


def _restore_unprocessed_work_objects(
    work_scene: bpy.types.Scene,
    work_initial_ids: set[int],
    output_coll: bpy.types.Collection,
    *,
    moved_ids: set[int],
) -> None:
    """Move original subtree shells still in the work scene back to the output collection."""
    survivors: list[bpy.types.Object] = []
    for obj in list(work_scene.objects):
        if not object_helpers.is_object_alive(obj):
            continue
        oid = id(obj)
        if oid in moved_ids or oid not in work_initial_ids:
            continue
        if obj.type not in {'MESH', 'EMPTY'}:
            continue
        if _is_colinst_shell_object(obj):
            continue
        survivors.append(obj)
    if not survivors:
        return
    _move_objects_to_collection(survivors, output_coll)
    _deep_apply_log_objects(
        'restored unprocessed work-scene objects', survivors, stage='survivors',
    )


def _restore_work_objects_on_failure(
    work_object_names: set[str],
    output_coll: bpy.types.Collection,
) -> None:
    """Return untouched originals to the output collection when extract produced nothing."""
    live = [
        bpy.data.objects[name]
        for name in work_object_names
        if name in bpy.data.objects
    ]
    if not live:
        return
    _move_objects_to_collection(live, output_coll)
    _deep_apply_log_objects(
        'restored work objects after failed extract', live, stage='restore_failed',
    )


def _unique_object_name(base: str) -> str:
    if base not in bpy.data.objects:
        return base
    index = 1
    while True:
        candidate = f'{base}.{index:03d}'
        if candidate not in bpy.data.objects:
            return candidate
        index += 1


def _mesh_world_vertices(
    obj: bpy.types.Object,
    *,
    evaluated: bool = False,
) -> list[Vector]:
    if obj.type != 'MESH' or obj.data is None:
        return []
    if evaluated and (obj.modifiers or obj.parent):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        try:
            matrix = eval_obj.matrix_world
            return [matrix @ vertex.co for vertex in mesh.vertices]
        finally:
            eval_obj.to_mesh_clear()
    matrix = obj.matrix_world.copy()
    return [matrix @ vertex.co for vertex in obj.data.vertices]


def _max_vertex_delta(
    before: list[Vector],
    after: list[Vector],
) -> float | None:
    if len(before) != len(after):
        return None
    if not before:
        return 0.0
    return max((after_vertex - before_vertex).length for after_vertex, before_vertex in zip(after, before))


def _match_sources_to_results(
    source_names: list[str],
    result_meshes: list[bpy.types.Object],
    before_verts: dict[str, list[Vector]],
) -> dict[str, bpy.types.Object]:
    """Greedy best-first source mesh → flattened result mapping."""
    mapping: dict[str, bpy.types.Object] = {}
    used_results: set[str] = set()
    candidates: list[tuple[float, str, bpy.types.Object]] = []

    for source_name in source_names:
        before = before_verts.get(source_name)
        if before is None:
            continue
        for result in result_meshes:
            if result.name in used_results:
                continue
            delta = _max_vertex_delta(before, _mesh_world_vertices(result))
            if delta is None:
                continue
            candidates.append((delta, source_name, result))

    candidates.sort(key=lambda item: item[0])
    matched_sources: set[str] = set()
    for _delta, source_name, result in candidates:
        if source_name in matched_sources or result.name in used_results:
            continue
        matched_sources.add(source_name)
        used_results.add(result.name)
        mapping[source_name] = result

    return mapping


def _build_duplicate_mode_name_map(
    source_mesh_names: list[str],
    result_meshes: list[bpy.types.Object],
    before_verts: dict[str, list[Vector]],
) -> dict[str, str]:
    """Map flattened source mesh names to their ``_applied`` duplicate results."""
    source_map = _match_sources_to_results(
        source_mesh_names, result_meshes, before_verts,
    )
    return {
        source_name: result.name
        for source_name, result in source_map.items()
    }


def _rename_duplicate_mode_results(result_meshes: list[bpy.types.Object]) -> None:
    for obj in result_meshes:
        base = f'{obj.name}{_DEEP_APPLY_DUPLICATE_SUFFIX}'
        obj.name = _unique_object_name(base)


def _detach_external_parents_preserving_world(
    objects: list[bpy.types.Object],
) -> None:
    """Unparent external CI/GP roots before work-scene processing (keep matrix_world)."""
    name_set = {
        obj.name for obj in objects if object_helpers.is_object_alive(obj)
    }
    for root in object_helpers.collect_hierarchy_forest_roots(
        object_helpers.filter_valid_objects(objects),
    ):
        if not is_colinst_object(root):
            continue
        parent = root.parent
        if parent is None or parent.name in name_set:
            continue
        matrix = root.matrix_world.copy()
        root.parent = None
        root.matrix_world = matrix


def _recompute_roots_after_colinst_bake(
    root_names: set[str],
    baked_roots: list[bpy.types.Object] | tuple[bpy.types.Object, ...],
) -> list[bpy.types.Object]:
    """Forest roots for downstream extract after in-place ColInst dissolve."""
    _ = root_names
    alive_roots = object_helpers.filter_valid_objects(list(baked_roots))
    if not alive_roots:
        return []
    return object_helpers.collect_hierarchy_forest_roots(
        object_helpers.collect_objects_in_subtrees(alive_roots),
    )


def _run_colinst_and_extract(
    context: bpy.types.Context,
    work_roots: list[bpy.types.Object],
    *,
    phase_bake_collection_instances: bool,
    after_bake_roots: Callable[[], list[bpy.types.Object]] | None = None,
) -> list[bpy.types.Object]:
    """ColInst bake, uniquify, and in-place worldspace extract (manual 3-step parity)."""
    root_names = {
        obj.name for obj in work_roots if object_helpers.is_object_alive(obj)
    }
    baked_empties: list[bpy.types.Object] = []
    if phase_bake_collection_instances:
        bake_result = bake_collection_instances_for_roots(context, work_roots)
        baked_empties = list(bake_result.baked_root_empties)
        _deep_pass_log(
            'bake_collection_instances',
            f'baked={bake_result.baked_collection_instances}',
        )

    if after_bake_roots is not None:
        work_roots = after_bake_roots()
    elif baked_empties:
        work_roots = _recompute_roots_after_colinst_bake(root_names, baked_empties)

    if phase_bake_collection_instances:
        gn_bake = bake_geonodes_collection_instances_for_roots(
            context, work_roots,
        )
        _deep_pass_log(
            'bake_geonodes_collection_instances',
            f'baked={gn_bake.baked_geonodes_collection_instances}',
        )
        if after_bake_roots is not None:
            work_roots = after_bake_roots()
        elif baked_empties:
            work_roots = _recompute_roots_after_colinst_bake(
                root_names, baked_empties,
            )

    uniquify_result = deep_uniquify_geometry(context, work_roots)
    _deep_pass_log(
        'uniquify',
        f'meshes={uniquify_result.mesh_count} '
        f'uniquified={uniquify_result.uniquified_count}',
    )

    from .worldspace_extract_helpers import deep_extract_worldspace_geometry

    extract_result = deep_extract_worldspace_geometry(
        context, work_roots, duplicate=False,
    )
    result = list(extract_result.extracted_objects)
    if result:
        sync_mesh_attributes_for_join(context, result)
    _deep_pass_log(
        'extract_worldspace',
        f'targets={extract_result.source_target_count} '
        f'extracted={len(result)}',
        objects=result,
    )
    return result


def deep_apply_roots(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
    output_coll: bpy.types.Collection,
    *,
    preview: bool = True,
    duplicate: bool = False,
    work_scene_name: str | None = None,
    phase_bake_collection_instances: bool = True,
    link_to_scene_collection: bool = False,
) -> list[bpy.types.Object]:
    """Transient work-scene ColInst bake + worldspace extract; in-place or duplicate output."""
    if not roots:
        _deep_apply_log('early exit: no roots', stage='no_roots')
        return []

    _deep_apply_log_objects('forest roots', roots, stage='roots')
    selection_subtree = object_helpers.collect_objects_in_subtrees(roots)
    _deep_apply_log_objects('selection subtree', selection_subtree, stage='subtree')
    _deep_apply_log(
        f'output collection {output_collection_report_path(output_coll)} '
        f'(scene={context.scene.name!r}) duplicate={duplicate}',
        stage='output_coll',
    )

    original_scene = context.scene
    if duplicate:
        work_objects = duplicate_objects_preserving_hierarchy(
            context,
            roots,
            original_scene.collection,
        )
        _deep_apply_log_objects(
            'duplicates after hierarchy copy', work_objects, stage='duplicate',
        )
    else:
        work_objects = list(selection_subtree)
        _deep_apply_log_objects(
            'in-place work objects (originals)', work_objects, stage='in_place',
        )

    if not work_objects:
        _deep_apply_log('early exit: no work objects for flatten', stage='no_work')
        return []

    work_object_names = {
        obj.name for obj in work_objects if object_helpers.is_object_alive(obj)
    }
    pre_pipeline_object_ids = {id(obj) for obj in bpy.data.objects}
    work_initial_ids = {
        id(obj) for obj in work_objects if object_helpers.is_object_alive(obj)
    }

    if preview and not duplicate:
        _clear_deep_apply_preview_objects(output_coll)

    scene_name = work_scene_name or f'{_WORK_SCENE_PREFIX}_{original_scene.name}'
    work_scene = bpy.data.scenes.new(scene_name)
    _deep_apply_log(
        f'work scene {work_scene.name!r} (original={original_scene.name!r})',
        stage='work_scene',
    )

    result: list[bpy.types.Object] = []
    try:
        _detach_external_parents_preserving_world(work_objects)
        _move_objects_to_scene(work_objects, work_scene)
        _deep_apply_log_objects(
            f'work scene objects after move (count={len(work_scene.objects)})',
            list(work_scene.objects),
            stage='work_scene_objects',
        )

        work_view_layer = work_scene.view_layers[0]
        work_roots = object_helpers.collect_hierarchy_forest_roots(work_objects)
        with context.temp_override(scene=work_scene, view_layer=work_view_layer):
            result = _run_colinst_and_extract(
                context,
                work_roots,
                phase_bake_collection_instances=phase_bake_collection_instances,
                after_bake_roots=lambda: object_helpers.collect_hierarchy_forest_roots(
                    list(work_scene.objects),
                ),
            )

        if not result:
            _deep_apply_log(
                f'early exit: deep_apply_geometry returned {result!r}',
                stage='flatten_empty',
            )
            return []

        objects_to_restore = result

        _deep_apply_log_objects('extract result meshes', result, stage='flatten_ok')
        _deep_apply_log_objects('objects processed', objects_to_restore, stage='processed')
        _move_objects_to_collection(objects_to_restore, output_coll)
        if link_to_scene_collection:
            move_objects_to_scene_collection(objects_to_restore, original_scene)
        if not duplicate:
            _restore_unprocessed_work_objects(
                work_scene,
                work_initial_ids,
                output_coll,
                moved_ids={id(obj) for obj in objects_to_restore},
            )
        if duplicate:
            _rename_duplicate_mode_results(result)
            for obj in result:
                obj[_DEEP_APPLY_PREVIEW_KEY] = True
        else:
            for obj in result:
                if _DEEP_APPLY_PREVIEW_KEY in obj:
                    del obj[_DEEP_APPLY_PREVIEW_KEY]
        _deep_apply_log(
            f'moved {len(result)} mesh(es) to {output_collection_report_path(output_coll)} '
            f'(mode={"duplicate" if duplicate else "in_place"})',
            stage='done',
        )
        return result
    finally:
        if not result and not duplicate:
            _restore_work_objects_on_failure(work_object_names, output_coll)
        _release_foreign_work_scene_objects(
            work_scene,
            original_scene,
            work_initial_ids=work_initial_ids,
            pre_pipeline_object_ids=pre_pipeline_object_ids,
        )
        _clear_work_scene(
            work_scene,
            pre_pipeline_object_ids=pre_pipeline_object_ids,
            work_initial_ids=work_initial_ids,
        )
        if work_scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(work_scene)
        window = getattr(context, 'window', None)
        if window is not None and window.scene != original_scene:
            window.scene = original_scene


def deep_apply_selected_geometry(
    context: bpy.types.Context,
    *,
    preview: bool = True,
    duplicate: bool = False,
    phase_bake_collection_instances: bool = True,
    link_to_scene_collection: bool = False,
) -> tuple[list[bpy.types.Object], bpy.types.Collection | None]:
    """
    Deep-apply geometry on the current selection forest roots.

    ``duplicate=False`` (default): flatten in-place on originals — same object
  names, no parallel source+result meshes.
    ``duplicate=True``: keep sources and add ``_applied`` flattened copies.
    """
    _deep_apply_reset_status()
    _deep_apply_log_objects(
        f'selection (mode={context.mode!r}, scene={context.scene.name!r})',
        object_helpers.context_selected_objects(context),
        stage='selection',
    )

    roots = get_selection_flatten_roots(context)
    if not roots:
        _deep_apply_log('early exit: no flatten forest roots in selection', stage='no_roots')
        return [], None

    selection_subtree = object_helpers.collect_objects_in_subtrees(roots)

    _deep_apply_log_objects('computed forest roots', roots, stage='roots')
    _deep_apply_log_objects('selection subtree objects', selection_subtree, stage='subtree')

    output_coll = resolve_output_collection_for_roots(context, roots)
    result = deep_apply_roots(
        context,
        roots,
        output_coll,
        preview=preview,
        duplicate=duplicate,
        work_scene_name=f'{_WORK_SCENE_PREFIX}_Selection',
        phase_bake_collection_instances=phase_bake_collection_instances,
        link_to_scene_collection=link_to_scene_collection,
    )

    if result:
        reselect_objects(context, result)

    return result, output_coll

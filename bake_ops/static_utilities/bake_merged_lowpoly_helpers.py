"""Temporary bake-group extract geometry pipeline (duplicates only)."""

from __future__ import annotations

import re

import bpy

from lks_baker.shared_utilities import object_helpers
from lks_baker.shared_utilities.collection_instance_helpers import is_colinst_object
from lks_baker.shared_utilities.deep_apply_geometry_helpers import duplicate_objects_preserving_hierarchy
from lks_baker.shared_utilities.deep_geometry_phase_helpers import (
    bake_collection_instances_for_roots,
    bake_geonodes_collection_instances_for_roots,
    deep_apply_modifiers,
    deep_triangulate_geometry,
    deep_uv_unstack,
    deep_uniquify_geometry,
    move_objects_to_scene_collection,
)
from lks_baker.shared_utilities.mesh_attribute_sync_helpers import (
    MeshAttributeSchema,
    collect_mesh_attribute_schema,
    sync_mesh_attributes,
    sync_mesh_attributes_for_join,
)
from lks_baker.shared_utilities.deep_apply_debug import log as _extract_log, log_objects as _extract_log_objects
from lks_baker.shared_utilities.mesh_helpers import _join_mesh_objects_via_bmesh, join_mesh_objects
from lks_baker.shared_utilities.grouppro_helpers import (
    get_exportable_grouppro_groups,
    is_grouppro_placeholder_mesh,
    is_grouppro_placeholder_object,
    make_grouppro_groups_unique_manual,
)
from lks_baker.shared_utilities.worldspace_extract_helpers import deep_extract_worldspace_geometry

_MERGED_LOWPOLY_KEY = 'lks_merged_lowpoly'
_EXTRACTED_HIGHPOLY_KEY = 'lks_extracted_highpoly'
_WORK_SCENE_PREFIX = '_LKS_BakeExtract'


def _move_objects_to_collection(
    objects: list[bpy.types.Object],
    target_collection: bpy.types.Collection,
) -> None:
    for obj in object_helpers.filter_valid_objects(objects):
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        if obj.name not in target_collection.objects:
            target_collection.objects.link(obj)


def _move_objects_to_scene(
    objects: list[bpy.types.Object],
    scene: bpy.types.Scene,
) -> None:
    for obj in object_helpers.filter_valid_objects(objects):
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        if obj.name not in scene.collection.objects:
            scene.collection.objects.link(obj)


def _detach_external_parents_preserving_world(
    objects: list[bpy.types.Object],
) -> None:
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


def _work_scene_forest_roots(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    """Forest roots for every object currently in the transient work scene."""
    return object_helpers.collect_hierarchy_forest_roots(
        object_helpers.filter_valid_objects(list(scene.objects)),
    )


def _ensure_objects_in_view_layer(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    objects: list[bpy.types.Object],
) -> None:
    """Link pipeline objects to the work scene root collection for view-layer ops."""
    move_objects_to_scene_collection(objects, scene)
    context.view_layer.update()


def _clear_prior_pipeline_artifacts(
    output_coll: bpy.types.Collection,
    artifact_key: str,
) -> None:
    for obj in list(output_coll.objects):
        if obj.name not in bpy.data.objects:
            continue
        if not obj.get(artifact_key):
            continue
        bpy.data.objects.remove(obj, do_unlink=True)


def _clear_prior_merged_lowpoly(output_coll: bpy.types.Collection) -> None:
    _clear_prior_pipeline_artifacts(output_coll, _MERGED_LOWPOLY_KEY)


def _clear_prior_extracted_highpoly(output_coll: bpy.types.Collection) -> None:
    _clear_prior_pipeline_artifacts(output_coll, _EXTRACTED_HIGHPOLY_KEY)


def _is_joinable_geometry_mesh(obj: bpy.types.Object) -> bool:
    """Real evaluated geometry — not Group Pro placeholder shells."""
    if obj.type != 'MESH' or obj.data is None:
        return False
    if len(obj.data.vertices) == 0:
        return False
    if is_grouppro_placeholder_object(obj):
        return False
    if is_grouppro_placeholder_mesh(obj.data):
        return False
    return True


def _work_scene_extract_mesh_objects(
    scene: bpy.types.Scene,
) -> list[bpy.types.Object]:
    """Live mesh objects in the work scene immediately before worldspace extract."""
    return [
        obj for obj in object_helpers.filter_mesh_objects(list(scene.objects))
        if _is_joinable_geometry_mesh(obj)
    ]


def _detach_parentless_for_join(
    objects: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    """Unparent meshes before join while preserving world transforms."""
    meshes: list[bpy.types.Object] = []
    for obj in object_helpers.filter_valid_objects(objects):
        if not _is_joinable_geometry_mesh(obj):
            continue
        if obj.parent is not None:
            matrix = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = matrix
        meshes.append(obj)
    return meshes


def _safe_join_meshes(
    context: bpy.types.Context,
    meshes: list[bpy.types.Object],
    *,
    scene: bpy.types.Scene | None = None,
    hierarchy_meshes: list[bpy.types.Object] | None = None,
    attribute_schema: MeshAttributeSchema | None = None,
) -> bpy.types.Object | None:
    """Mirror ``object.lks_safe_join``: sync hierarchy attrs, then ``bpy.ops.object.join``."""
    live = _detach_parentless_for_join(meshes)
    if not live:
        return None

    target_scene = scene or context.scene
    view_layer = (
        context.view_layer
        if context.scene == target_scene
        else target_scene.view_layers[0]
    )
    _ensure_objects_in_view_layer(context, target_scene, live)
    context.view_layer.update()
    view_layer_names = {obj.name for obj in view_layer.objects}
    joinable = [
        obj for obj in live
        if obj.name in view_layer_names and _is_joinable_geometry_mesh(obj)
    ]

    if len(joinable) == 1:
        sync_targets = hierarchy_meshes or joinable
        if attribute_schema is not None:
            sync_mesh_attributes(context, sync_targets, schema=attribute_schema)
        else:
            sync_mesh_attributes(context, sync_targets)
        return joinable[0]

    if len(joinable) < 2:
        _extract_log(
            f'join aborted: {len(joinable)}/{len(live)} mesh(es) '
            f'in view layer {view_layer.name!r}',
            stage='join_skip',
        )
        return None

    sync_targets = hierarchy_meshes or joinable
    if attribute_schema is not None:
        sync_mesh_attributes(context, sync_targets, schema=attribute_schema)
    else:
        sync_mesh_attributes(context, sync_targets)

    for obj in joinable:
        object_helpers.ensure_single_user_mesh_data(obj)

    result, merged = join_mesh_objects(
        context,
        joinable,
        scene=target_scene,
        view_layer=view_layer,
    )
    if 'CANCELLED' in result:
        _extract_log(
            f'join poll failed for {len(joinable)} mesh(es); trying bmesh fallback',
            stage='join_fail',
        )
    if (
        'CANCELLED' in result
        or merged is None
        or merged.type != 'MESH'
    ):
        if 'CANCELLED' in result:
            _extract_log(
                f'join cancelled for {len(joinable)} mesh(es); trying bmesh fallback',
                stage='join_fail',
            )
        with context.temp_override(scene=target_scene, view_layer=view_layer):
            merged = _join_mesh_objects_via_bmesh(joinable, context=context)
        if merged is None or merged.type != 'MESH':
            _extract_log('bmesh join fallback failed', stage='join_fail')
            return None
    object_helpers.ensure_single_user_mesh_data(merged)
    return merged


def _extracted_high_name(source_name: str) -> str:
    stem = re.sub(r'_extracted(?:\.\d+)?$', '', source_name)
    return f'{stem}_extracted_high'


def _finalize_extracted_high_objects(
    extracted: list[bpy.types.Object],
    output_coll: bpy.types.Collection,
) -> list[bpy.types.Object]:
    live = object_helpers.filter_valid_objects(extracted)
    if not live:
        return []

    _clear_prior_extracted_highpoly(output_coll)
    results: list[bpy.types.Object] = []
    for obj in live:
        obj.name = _extracted_high_name(obj.name)
        obj[_EXTRACTED_HIGHPOLY_KEY] = True
        results.append(obj)
    _move_objects_to_collection(results, output_coll)
    return results


def bake_extract_geometry_for_roots(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
    output_coll: bpy.types.Collection,
    *,
    merge_at_end: bool = True,
    result_name: str = '',
    work_scene_name: str | None = None,
) -> bpy.types.Object | list[bpy.types.Object] | None:
    """
    Duplicate-only bake prep pipeline ending in worldspace extract.

    When ``merge_at_end`` is True, extracted meshes are joined into one result.
    When False, all extracted meshes are placed in ``output_coll`` unmerged.
    """
    if not roots:
        return None if merge_at_end else []

    _extract_log_objects('merge/extract forest roots', roots, stage='roots')
    original_scene = context.scene
    work_objects = duplicate_objects_preserving_hierarchy(
        context,
        roots,
        original_scene.collection,
        preserve_modifiers=True,
    )
    if not work_objects:
        return None if merge_at_end else []

    _extract_log_objects('work duplicates', work_objects, stage='dupes')
    _extract_log(
        f'duplicated {len(work_objects)} object(s) from {len(roots)} forest root(s)',
        stage='dupes',
    )

    pre_pipeline_object_ids = {id(obj) for obj in bpy.data.objects}
    work_initial_ids = {
        id(obj) for obj in work_objects if object_helpers.is_object_alive(obj)
    }

    scene_name = work_scene_name or f'{_WORK_SCENE_PREFIX}_{original_scene.name}'
    work_scene = bpy.data.scenes.new(scene_name)
    merged: bpy.types.Object | None = None
    extracted_output: list[bpy.types.Object] = []

    try:
        _detach_external_parents_preserving_world(work_objects)
        _move_objects_to_scene(work_objects, work_scene)
        work_view_layer = work_scene.view_layers[0]

        with context.temp_override(scene=work_scene, view_layer=work_view_layer):
            work_roots = _work_scene_forest_roots(work_scene)

            gp_groups = get_exportable_grouppro_groups(list(work_scene.objects))
            if gp_groups:
                unique_count = make_grouppro_groups_unique_manual(work_roots)
                _extract_log(
                    f'GP collection uniquify: {unique_count} group(s) '
                    f'from {len(gp_groups)} instance(s)',
                    stage='gp_unique',
                )

            colinst_result = bake_collection_instances_for_roots(context, work_roots)
            _extract_log(
                f'colinst baked={colinst_result.baked_collection_instances} '
                f'work_roots={len(work_roots)}',
                stage='colinst',
            )
            work_roots = _work_scene_forest_roots(work_scene)

            bake_geonodes_collection_instances_for_roots(context, work_roots)
            work_roots = _work_scene_forest_roots(work_scene)

            _ensure_objects_in_view_layer(
                context, work_scene, list(work_scene.objects),
            )

            work_roots = _work_scene_forest_roots(work_scene)
            deep_uniquify_geometry(context, work_roots)

            work_roots = _work_scene_forest_roots(work_scene)
            deep_uv_unstack(context, work_roots)
            context.view_layer.update()

            work_roots = _work_scene_forest_roots(work_scene)
            deep_apply_modifiers(context, work_roots, defer_triangulate=True)
            deep_triangulate_geometry(context, work_roots)

            work_roots = _work_scene_forest_roots(work_scene)

            pre_extract_meshes = _work_scene_extract_mesh_objects(work_scene)
            extract_attribute_schema: MeshAttributeSchema | None = None
            if pre_extract_meshes:
                extract_attribute_schema = collect_mesh_attribute_schema(
                    pre_extract_meshes,
                )
            extract_result = deep_extract_worldspace_geometry(
                context,
                work_roots,
                duplicate=False,
            )
            extracted = [
                obj for obj in extract_result.extracted_objects
                if _is_joinable_geometry_mesh(obj)
            ]
            if extracted and extract_attribute_schema is not None:
                sync_mesh_attributes(
                    context,
                    extracted,
                    schema=extract_attribute_schema,
                )
            elif extracted:
                sync_mesh_attributes_for_join(context, extracted)
            _extract_log_objects('extract meshes', extracted, stage='pre_join')
            _extract_log(
                f'extract targets={extract_result.source_target_count} '
                f'meshes={len(extracted)} merge={merge_at_end}',
                stage='extract_ok',
            )

            if merge_at_end:
                _extract_log_objects('join meshes', extracted, stage='pre_join')
                _extract_log(
                    f'join_candidates={len(extracted)} merge={merge_at_end}',
                    stage='pre_join',
                )
                merged = _safe_join_meshes(
                    context,
                    extracted,
                    scene=work_scene,
                    hierarchy_meshes=extracted,
                    attribute_schema=extract_attribute_schema,
                )
            else:
                extracted_output = extracted

        if merge_at_end:
            if merged is None:
                return None
            merged.name = result_name
            merged[_MERGED_LOWPOLY_KEY] = True
            _clear_prior_merged_lowpoly(output_coll)
            _move_objects_to_collection([merged], output_coll)
            return merged

        return _finalize_extracted_high_objects(extracted_output, output_coll)
    finally:
        kept_objects: set[bpy.types.Object] = set()
        if merge_at_end and merged is not None:
            kept_objects.add(merged)
        elif not merge_at_end:
            kept_objects.update(extracted_output)

        for obj in list(work_scene.objects):
            if not object_helpers.is_object_alive(obj):
                continue
            oid = id(obj)
            if oid in pre_pipeline_object_ids and oid not in work_initial_ids:
                continue
            if obj in kept_objects:
                continue
            bpy.data.objects.remove(obj, do_unlink=True)
        if work_scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(work_scene)
        window = getattr(context, 'window', None)
        if window is not None and window.scene != original_scene:
            window.scene = original_scene


def generate_merged_lowpoly_for_roots(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
    output_coll: bpy.types.Collection,
    *,
    result_name: str,
    work_scene_name: str | None = None,
) -> bpy.types.Object | None:
    """Build one merged lowpoly mesh from forest roots using duplicate-only pipeline."""
    result = bake_extract_geometry_for_roots(
        context,
        roots,
        output_coll,
        merge_at_end=True,
        result_name=result_name,
        work_scene_name=work_scene_name,
    )
    if isinstance(result, bpy.types.Object):
        return result
    return None


def generate_extracted_highpoly_for_roots(
    context: bpy.types.Context,
    roots: list[bpy.types.Object],
    output_coll: bpy.types.Collection,
    *,
    work_scene_name: str | None = None,
) -> list[bpy.types.Object]:
    """Build unmerged extracted high meshes from forest roots (duplicate-only pipeline)."""
    result = bake_extract_geometry_for_roots(
        context,
        roots,
        output_coll,
        merge_at_end=False,
        work_scene_name=work_scene_name,
    )
    if isinstance(result, list):
        return result
    return []

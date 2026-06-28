"""Bake project export orchestration — generation pipeline then scoped FBX write."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import bpy
from mathutils import Matrix

from .static_utilities.bake_export_helpers import (
    cleanup_bake_export_temp_objects,
    create_export_empty,
    create_isolated_export_scene,
    duplicate_mesh_for_export,
    empty_is_descendant_of_any,
    ensure_export_directory,
    export_fbx_selection,
    export_scene_name,
    find_deepest_collection_for_object,
    mirror_child_collections_as_export_empties,
    remove_export_scene,
)
from .static_utilities.bake_view_layer_helpers import (
    ensure_objects_in_active_view_layer,
    temporary_bake_view_layer_access,
)
from .static_utilities.bake_debug_log_helpers import log_step, timed_step
from ..shared_utilities.lks_constants import BAKE_EXPORT_MODE_DEFAULT
from .helpers_bake_cleanup import (
    bake_group_collection_name,
    bake_project_root_collection_name,
    delete_bake_pipeline_artifacts_for_group,
    delete_bake_pipeline_artifacts_for_project,
    get_bake_group_collection,
    get_bake_group_role_collection,
    get_high_collections,
    get_low_collections,
    get_project_root_collection,
    iter_bake_project_collections,
    iter_bake_project_objects,
)
from .helpers_bake_prep import (
    bake_group_high_has_flatten_geometry,
    bake_group_low_has_flatten_geometry,
    generate_extracted_highpoly_for_bake_group,
    generate_merged_lowpoly_for_bake_group,
    get_bake_group_high_meshes,
)
from .lks_bake_props import LKS_PG_BakeGroup, LKS_PG_BakeProject

_MERGED_LOW_KEY = 'lks_merged_lowpoly'
_EXTRACTED_HIGH_KEY = 'lks_extracted_highpoly'
_SKIP_EXPORT_MIRROR_COLLECTIONS = frozenset({'_BAKE_PREP'})
_EXTRACTED_HIGH_STEM_RE = re.compile(r'_extracted_high(?:\.\d+)?$')


@dataclass
class BakeGroupExportMeshes:
    """Processed export meshes for one bake group."""

    group: LKS_PG_BakeGroup
    low_mesh: bpy.types.Object | None = None
    high_meshes: list[bpy.types.Object] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        """Has content.

        Returns:
            ``bool`` result.
        """
        return self.low_mesh is not None or bool(self.high_meshes)


def _iter_collection_objects_recursive(
    coll: bpy.types.Collection,
) -> list[bpy.types.Object]:
    seen: set[str] = set()
    objects: list[bpy.types.Object] = []

    def walk(collection: bpy.types.Collection) -> None:
        for obj in collection.objects:
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
            for child in obj.children:
                if child.name in seen:
                    continue
                seen.add(child.name)
                objects.append(child)
        for child_coll in collection.children:
            walk(child_coll)

    walk(coll)
    return objects


def iter_bake_group_export_low_mesh(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bpy.types.Object | None:
    """Merged lowpoly artifact tagged ``lks_merged_lowpoly``."""
    for coll in get_low_collections(project, group):
        for obj in _iter_collection_objects_recursive(coll):
            if obj.type == 'MESH' and obj.get(_MERGED_LOW_KEY):
                return obj
    return None


def iter_bake_group_export_high_meshes(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Extracted high meshes tagged ``lks_extracted_highpoly``."""
    meshes: list[bpy.types.Object] = []
    seen: set[str] = set()
    for coll in get_high_collections(project, group):
        for obj in _iter_collection_objects_recursive(coll):
            if obj.type != 'MESH' or not obj.get(_EXTRACTED_HIGH_KEY):
                continue
            if obj.name in seen:
                continue
            seen.add(obj.name)
            meshes.append(obj)
    return meshes


def _generate_bake_group_export_geometry_impl(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> BakeGroupExportMeshes | None:
    """Run merged-low / extracted-high for one group; return export meshes or None."""
    if bake_group_low_has_flatten_geometry(project, group):
        generate_merged_lowpoly_for_bake_group(context, project, group)
    if bake_group_high_has_flatten_geometry(project, group):
        generate_extracted_highpoly_for_bake_group(context, project, group)

    export_row = BakeGroupExportMeshes(
        group=group,
        low_mesh=iter_bake_group_export_low_mesh(project, group),
        high_meshes=iter_bake_group_export_high_meshes(project, group),
    )
    if not export_row.has_content:
        return None

    artifact_objects: list[bpy.types.Object] = []
    if export_row.low_mesh is not None:
        artifact_objects.append(export_row.low_mesh)
    artifact_objects.extend(export_row.high_meshes)
    ensure_objects_in_active_view_layer(context, context.scene, artifact_objects)
    return export_row


def generate_bake_group_export_geometry(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> BakeGroupExportMeshes | None:
    """Run merged-low / extracted-high for one group; return export meshes or None."""
    collections = iter_bake_project_collections(project)
    project_objects = iter_bake_project_objects(project)
    with temporary_bake_view_layer_access(context, collections, project_objects):
        return _generate_bake_group_export_geometry_impl(context, project, group)


def generate_bake_project_export_geometry(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
) -> list[BakeGroupExportMeshes]:
    """Run merged-low and extracted-high pipelines; return per-group export meshes."""
    collections = iter_bake_project_collections(project)
    project_objects = iter_bake_project_objects(project)
    with temporary_bake_view_layer_access(context, collections, project_objects):
        results: list[BakeGroupExportMeshes] = []
        for group in project.bake_groups:
            export_row = _generate_bake_group_export_geometry_impl(
                context, project, group,
            )
            if export_row is not None:
                results.append(export_row)
        return results


def bake_export_project_empty_name(project: LKS_PG_BakeProject) -> str:
    """Mirror bake project root collection name (e.g. ``BakeProject_BakeProject``)."""
    root = get_project_root_collection(project)
    if root is not None:
        return root.name
    return bake_project_root_collection_name(project.name)


def bake_export_group_empty_name(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> str:
    """Mirror bake group folder collection name (e.g. ``BakeGroup_BakeGroup``)."""
    folder = get_bake_group_collection(project, group)
    if folder is not None:
        return folder.name
    return bake_group_collection_name(group.name)


def bake_export_role_empty_names(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> tuple[str, str]:
    """Mirror high/low role collection names (e.g. ``BakeGroup_high``)."""
    high_coll = group.high_collection or get_bake_group_role_collection(
        project, group, 'HIGH',
    )
    low_coll = group.low_collection or get_bake_group_role_collection(
        project, group, 'LOW',
    )
    high_name = high_coll.name if high_coll is not None else f'{group.name}_high'
    low_name = low_coll.name if low_coll is not None else f'{group.name}_low'
    return high_name, low_name


def _matrix_is_world_identity(matrix: bpy.types.Matrix) -> bool:
    return matrix == Matrix.Identity(4)


def _role_collection(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    role_key: str,
) -> bpy.types.Collection | None:
    if role_key == 'HIGH':
        coll = group.high_collection
    else:
        coll = group.low_collection
    if coll is not None:
        return coll
    return get_bake_group_role_collection(project, group, role_key)


def _mirror_role_collection_empties(
    role_coll: bpy.types.Collection,
    role_empty: bpy.types.Object,
    scene_coll: bpy.types.Collection,
) -> tuple[dict[int, bpy.types.Object], list[bpy.types.Object]]:
    """Nested collection empties under ``role_empty``; returns map + new empties."""
    coll_map = mirror_child_collections_as_export_empties(
        role_coll,
        role_empty,
        scene_coll,
        skip_collection_names=_SKIP_EXPORT_MIRROR_COLLECTIONS,
    )
    nested_empties = [
        obj for coll_id, obj in coll_map.items()
        if coll_id != id(role_coll)
    ]
    return coll_map, nested_empties


def _parent_empty_for_source_object(
    coll_map: dict[int, bpy.types.Object],
    role_coll: bpy.types.Collection,
    role_empty: bpy.types.Object,
    source_obj: bpy.types.Object | None,
) -> bpy.types.Object:
    if source_obj is None:
        return role_empty
    target_coll = find_deepest_collection_for_object(
        role_coll,
        source_obj,
        skip_collection_names=_SKIP_EXPORT_MIRROR_COLLECTIONS,
    )
    return coll_map.get(id(target_coll), role_empty)


def _high_mesh_source_root(
    high_mesh: bpy.types.Object,
    roots: list[bpy.types.Object],
) -> bpy.types.Object | None:
    for root in roots:
        stem = re.sub(r'_extracted(?:\.\d+)?$', '', root.name)
        expected = f'{stem}_extracted_high'
        if high_mesh.name == expected or high_mesh.name == root.name:
            return root
    stem = _EXTRACTED_HIGH_STEM_RE.sub('', high_mesh.name)
    for root in roots:
        if root.name == stem:
            return root
    return None


def _collect_nested_export_empties(role_empty: bpy.types.Object) -> list[bpy.types.Object]:
    nested: list[bpy.types.Object] = []

    def walk(empty: bpy.types.Object) -> None:
        for child in empty.children:
            if child.type != 'EMPTY':
                continue
            nested.append(child)
            walk(child)

    walk(role_empty)
    return nested


def collect_bake_export_hierarchy_failures(
    export_objects: list[bpy.types.Object],
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    *,
    role: str | None = None,
) -> list[str]:
    """Validate export empties mirror bake collection names and sit at world origin."""
    failures: list[str] = []
    empties = [obj for obj in export_objects if obj.type == 'EMPTY']
    if not empties:
        failures.append('export hierarchy has no empties')
        return failures

    expected_project = bake_export_project_empty_name(project)
    expected_group = bake_export_group_empty_name(project, group)
    expected_high, expected_low = bake_export_role_empty_names(project, group)

    roots = [obj for obj in empties if obj.parent is None]
    if len(roots) != 1:
        failures.append(f'expected 1 root empty, found {len(roots)}')
        return failures

    root = roots[0]
    if root.name != expected_project:
        failures.append(
            f'root empty {root.name!r} != collection {expected_project!r}',
        )
    if not _matrix_is_world_identity(root.matrix_world):
        failures.append(f'root empty {root.name!r} is not at world origin')

    group_empties = [
        obj for obj in empties
        if obj.parent == root and obj.name == expected_group
    ]
    if not group_empties:
        failures.append(
            f'group empty {expected_group!r} missing under root',
        )
        return failures
    if len(group_empties) != 1:
        failures.append(
            f'expected 1 group empty named {expected_group!r} under root, '
            f'found {len(group_empties)}',
        )
        return failures

    group_empty = group_empties[0]
    if not _matrix_is_world_identity(group_empty.matrix_world):
        failures.append(f'group empty {group_empty.name!r} is not at world origin')

    role_empties = [obj for obj in empties if obj.parent == group_empty]
    role_names = {obj.name for obj in role_empties}
    expected_roles: set[str] = set()
    if role in (None, 'HIGH'):
        expected_roles.add(expected_high)
    if role in (None, 'LOW'):
        expected_roles.add(expected_low)

    if role_names != expected_roles:
        failures.append(
            f'role empties {sorted(role_names)!r} != expected {sorted(expected_roles)!r}',
        )

    for role_empty in role_empties:
        if not _matrix_is_world_identity(role_empty.matrix_world):
            failures.append(
                f'role empty {role_empty.name!r} is not at world origin',
            )
        for nested_empty in _collect_nested_export_empties(role_empty):
            if not _matrix_is_world_identity(nested_empty.matrix_world):
                failures.append(
                    f'nested empty {nested_empty.name!r} is not at world origin',
                )

    for obj in export_objects:
        if obj.type != 'MESH':
            continue
        if not empty_is_descendant_of_any(obj, [group_empty]):
            continue
        parent = obj.parent
        if parent is None or parent.type != 'EMPTY':
            failures.append(f'mesh {obj.name!r} is not parented under an empty')
            continue
        if not empty_is_descendant_of_any(parent, role_empties):
            failures.append(
                f'mesh {obj.name!r} is not parented under a role empty branch',
            )

    return failures


def _log_export_hierarchy(
    export_objects: list[bpy.types.Object],
    *,
    label: str,
) -> None:
    """Print export empty tree for headless test diagnostics."""
    empties = [obj for obj in export_objects if obj.type == 'EMPTY']

    def walk(empty: bpy.types.Object, indent: int) -> None:
        prefix = '  ' * indent
        print(f'{prefix}{empty.name}')
        child_empties = sorted(
            (child for child in empty.children if child.type == 'EMPTY'),
            key=lambda obj: obj.name,
        )
        for child_empty in child_empties:
            walk(child_empty, indent + 1)
        for child in sorted(empty.children, key=lambda obj: obj.name):
            if child.type == 'MESH':
                print(f'{prefix}  └── {child.name}')

    roots = sorted(
        (obj for obj in empties if obj.parent is None),
        key=lambda obj: obj.name,
    )
    print(f'EXPORT HIERARCHY {label}:')
    for root in roots:
        walk(root, 0)


def _export_fbx_in_scene(
    context: bpy.types.Context,
    export_scene: bpy.types.Scene,
    filepath: Path,
    export_objects: list[bpy.types.Object],
    *,
    hierarchy_label: str | None = None,
) -> None:
    """Write FBX from an isolated export scene, then remove tagged temp objects."""
    if hierarchy_label is not None:
        _log_export_hierarchy(export_objects, label=hierarchy_label)
    view_layer = export_scene.view_layers[0]
    with context.temp_override(scene=export_scene, view_layer=view_layer):
        export_fbx_selection(
            context,
            filepath,
            export_objects,
            include_empties=True,
            export_all_scene_objects=True,
        )
    cleanup_bake_export_temp_objects(export_objects)


def _append_group_meshes_to_hierarchy(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    row: BakeGroupExportMeshes,
    scene_coll: bpy.types.Collection,
    *,
    group_empty: bpy.types.Object,
    role: str | None = None,
) -> list[bpy.types.Object]:
    """Role empties, optional nested collection mirrors, mesh dupes under role branches."""
    export_objects: list[bpy.types.Object] = []
    group = row.group
    high_name, low_name = bake_export_role_empty_names(project, group)

    if role in (None, 'HIGH'):
        high_coll = _role_collection(project, group, 'HIGH')
        high_empty = create_export_empty(high_name, scene_coll, parent=group_empty)
        export_objects.append(high_empty)
        coll_map: dict[int, bpy.types.Object] = {id(high_empty): high_empty}
        if high_coll is not None:
            coll_map, nested_empties = _mirror_role_collection_empties(
                high_coll,
                high_empty,
                scene_coll,
            )
            export_objects.extend(nested_empties)
        high_roots = get_bake_group_high_meshes(project, group) if high_coll else []
        for high_mesh in row.high_meshes:
            source_root = _high_mesh_source_root(high_mesh, high_roots)
            if source_root is None and len(high_roots) == 1:
                source_root = high_roots[0]
            mesh_parent = (
                _parent_empty_for_source_object(
                    coll_map,
                    high_coll,
                    high_empty,
                    source_root,
                )
                if high_coll is not None
                else high_empty
            )
            dupe = duplicate_mesh_for_export(
                context,
                high_mesh,
                scene_coll,
                parent=mesh_parent,
                name=high_mesh.name,
            )
            export_objects.append(dupe)

    if role in (None, 'LOW'):
        low_coll = _role_collection(project, group, 'LOW')
        low_empty = create_export_empty(low_name, scene_coll, parent=group_empty)
        export_objects.append(low_empty)
        if low_coll is not None:
            _, nested_empties = _mirror_role_collection_empties(
                low_coll,
                low_empty,
                scene_coll,
            )
            export_objects.extend(nested_empties)
        if row.low_mesh is not None:
            dupe = duplicate_mesh_for_export(
                context,
                row.low_mesh,
                scene_coll,
                parent=low_empty,
                name=row.low_mesh.name,
            )
            export_objects.append(dupe)

    return export_objects


def _build_group_export_branch(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    row: BakeGroupExportMeshes,
    scene_coll: bpy.types.Collection,
    *,
    parent_empty: bpy.types.Object,
    role: str | None = None,
) -> list[bpy.types.Object]:
    """Project child: group empty plus optional high/low role branch."""
    group = row.group
    group_empty = create_export_empty(
        bake_export_group_empty_name(project, group),
        scene_coll,
        parent=parent_empty,
    )
    export_objects = [group_empty]
    export_objects.extend(
        _append_group_meshes_to_hierarchy(
            context,
            project,
            row,
            scene_coll,
            group_empty=group_empty,
            role=role,
        ),
    )
    return export_objects


def _build_export_hierarchy(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group_exports: list[BakeGroupExportMeshes],
    export_scene: bpy.types.Scene,
    *,
    role: str | None = None,
) -> list[bpy.types.Object]:
    """Mirror bake project collections as parented empties with export mesh duplicates."""
    export_objects: list[bpy.types.Object] = []
    scene_coll = export_scene.collection

    root_empty = create_export_empty(
        bake_export_project_empty_name(project),
        scene_coll,
    )
    export_objects.append(root_empty)

    for row in group_exports:
        export_objects.extend(
            _build_group_export_branch(
                context,
                project,
                row,
                scene_coll,
                parent_empty=root_empty,
                role=role,
            ),
        )

    return export_objects


def _export_group_one_fbx(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    row: BakeGroupExportMeshes,
    output_dir: Path,
) -> Path:
    """Single bake group as one FBX with project/group/high/low empties."""
    group = row.group
    scene_name = export_scene_name(group.name)
    export_scene = create_isolated_export_scene(scene_name)
    original_scene = context.window.scene if context.window else context.scene

    try:
        export_objects = _build_export_hierarchy(
            context, project, [row], export_scene,
        )
        hierarchy_failures = collect_bake_export_hierarchy_failures(
            export_objects, project, row.group,
        )
        if hierarchy_failures:
            raise RuntimeError(
                'Export hierarchy mismatch: ' + '; '.join(hierarchy_failures),
            )
        filepath = output_dir / f'{group.name}.fbx'
        _export_fbx_in_scene(
            context, export_scene, filepath, export_objects,
            hierarchy_label=group.name,
        )
        return filepath
    finally:
        if context.window is not None and original_scene is not None:
            context.window.scene = original_scene
        remove_export_scene(export_scene)


def _export_one_fbx(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group_exports: list[BakeGroupExportMeshes],
    output_dir: Path,
) -> Path:
    scene_name = export_scene_name(project.name)
    export_scene = create_isolated_export_scene(scene_name)
    original_scene = context.window.scene if context.window else context.scene

    try:
        export_objects = _build_export_hierarchy(
            context, project, group_exports, export_scene,
        )
        for row in group_exports:
            hierarchy_failures = collect_bake_export_hierarchy_failures(
                export_objects, project, row.group,
            )
            if hierarchy_failures:
                raise RuntimeError(
                    'Export hierarchy mismatch for '
                    f'{row.group.name}: ' + '; '.join(hierarchy_failures),
                )
        filepath = output_dir / f'{project.name}.fbx'
        _export_fbx_in_scene(
            context, export_scene, filepath, export_objects,
            hierarchy_label=project.name,
        )
        return filepath
    finally:
        if context.window is not None and original_scene is not None:
            context.window.scene = original_scene
        remove_export_scene(export_scene)


def _export_highs_and_lows(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group_exports: list[BakeGroupExportMeshes],
    output_dir: Path,
) -> list[Path]:
    exported: list[Path] = []
    original_scene = context.window.scene if context.window else context.scene

    for row in group_exports:
        group_name = row.group.name
        if row.high_meshes:
            scene_name = export_scene_name(f'{group_name}_high')
            export_scene = create_isolated_export_scene(scene_name)
            try:
                export_objects = _build_export_hierarchy(
                    context, project, [row], export_scene, role='HIGH',
                )
                hierarchy_failures = collect_bake_export_hierarchy_failures(
                    export_objects, project, row.group, role='HIGH',
                )
                if hierarchy_failures:
                    raise RuntimeError(
                        'Export hierarchy mismatch for '
                        f'{group_name}_high: ' + '; '.join(hierarchy_failures),
                    )
                filepath = output_dir / f'{group_name}_high.fbx'
                _export_fbx_in_scene(
                    context, export_scene, filepath, export_objects,
                    hierarchy_label=f'{group_name}_high',
                )
                exported.append(filepath)
            finally:
                remove_export_scene(export_scene)

        if row.low_mesh is not None:
            scene_name = export_scene_name(f'{group_name}_low')
            export_scene = create_isolated_export_scene(scene_name)
            try:
                export_objects = _build_export_hierarchy(
                    context, project, [row], export_scene, role='LOW',
                )
                hierarchy_failures = collect_bake_export_hierarchy_failures(
                    export_objects, project, row.group, role='LOW',
                )
                if hierarchy_failures:
                    raise RuntimeError(
                        'Export hierarchy mismatch for '
                        f'{group_name}_low: ' + '; '.join(hierarchy_failures),
                    )
                filepath = output_dir / f'{group_name}_low.fbx'
                _export_fbx_in_scene(
                    context, export_scene, filepath, export_objects,
                    hierarchy_label=f'{group_name}_low',
                )
                exported.append(filepath)
            finally:
                remove_export_scene(export_scene)

    if context.window is not None and original_scene is not None:
        context.window.scene = original_scene
    return exported


def export_bake_project(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    *,
    export_mode: str = BAKE_EXPORT_MODE_DEFAULT,
    output_dir: str | None = None,
) -> list[Path]:
    """
    Generate processed bake meshes, then export FBX per ``export_mode``.

    Returns written file paths. Raises ``RuntimeError`` when nothing is exported.
    """
    if len(project.bake_groups) == 0:
        raise RuntimeError('Bake project has no bake groups')

    target_dir = output_dir if output_dir else project.output_dir
    if not target_dir:
        raise RuntimeError('Bake project output directory is not set')

    with timed_step('export bake project', project=project):
        abs_output = ensure_export_directory(target_dir)
        with timed_step('generate export geometry', project=project):
            group_exports = generate_bake_project_export_geometry(context, project)
        if not group_exports:
            raise RuntimeError(
                'No export geometry produced — assign high/low roles with flattenable meshes',
            )
        log_step(
            f'{len(group_exports)} group(s) with export geometry',
            project=project,
        )

        with timed_step(f'write FBX ({export_mode})', project=project):
            if export_mode == 'HIGHS_AND_LOWS':
                paths = _export_highs_and_lows(context, project, group_exports, abs_output)
            else:
                paths = [_export_one_fbx(context, project, group_exports, abs_output)]

        if not paths:
            raise RuntimeError('Export produced no FBX files')

        for path in paths:
            log_step(f'wrote {path}', project=project)

        with timed_step('cleanup pipeline artifacts', project=project):
            removed = delete_bake_pipeline_artifacts_for_project(project)
            log_step(f'removed {removed} artifact(s)', project=project)

        log_step(f'success — {len(paths)} file(s) exported', project=project)
        return paths


def export_bake_group(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    *,
    export_mode: str = BAKE_EXPORT_MODE_DEFAULT,
    output_dir: str | None = None,
) -> list[Path]:
    """
    Generate processed meshes for one bake group, then export FBX per ``export_mode``.

    Returns written file paths. Raises ``RuntimeError`` when nothing is exported.
    """
    target_dir = output_dir if output_dir else project.output_dir
    if not target_dir:
        raise RuntimeError('Bake project output directory is not set')

    with timed_step(
        f'export bake group {group.name}',
        project=project,
        group_name=group.name,
    ):
        abs_output = ensure_export_directory(target_dir)
        with timed_step('generate export geometry', project=project, group_name=group.name):
            row = generate_bake_group_export_geometry(context, project, group)
        if row is None:
            raise RuntimeError(
                'No export geometry produced — assign high/low roles with flattenable meshes',
            )

        with timed_step(f'write FBX ({export_mode})', project=project, group_name=group.name):
            if export_mode == 'HIGHS_AND_LOWS':
                paths = _export_highs_and_lows(context, project, [row], abs_output)
            else:
                paths = [_export_group_one_fbx(context, project, row, abs_output)]

        if not paths:
            raise RuntimeError('Export produced no FBX files')

        for path in paths:
            log_step(f'wrote {path}', project=project, group_name=group.name)

        with timed_step('cleanup pipeline artifacts', project=project, group_name=group.name):
            removed = delete_bake_pipeline_artifacts_for_group(project, group)
            log_step(f'removed {removed} artifact(s)', project=project, group_name=group.name)

        log_step(
            f'success — {len(paths)} file(s) exported',
            project=project,
            group_name=group.name,
        )
        return paths


def bake_group_has_exportable_geometry(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bool:
    """True when the bake group has flattenable high or low geometry."""
    return (
        bake_group_low_has_flatten_geometry(project, group)
        or bake_group_high_has_flatten_geometry(project, group)
    )


def bake_project_has_exportable_groups(project: LKS_PG_BakeProject) -> bool:
    """True when any bake group has flattenable high or low geometry."""
    return any(
        bake_group_has_exportable_geometry(project, group)
        for group in project.bake_groups
    )

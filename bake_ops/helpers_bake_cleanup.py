"""Collection and RNA cleanup helpers for bake project / group removal."""

from __future__ import annotations

import re

import bpy

from ..shared_utilities.lks_constants import (
    BAKE_PREP_COLLECTION_STEM,
    is_bake_prep_collection_name,
)
from .static_utilities.bake_map_catalog import (
    needs_bake_map_catalog_seed,
    seed_bake_project_map_entries,
    seed_bake_project_map_entries_if_needed,
)

_pending_bake_map_catalog_seeds: set[tuple[str, str]] = set()
from .lks_bake_props import LKS_PG_BakeGroup, LKS_PG_BakeProject, clamp_active_bake_group_index

_BAKE_PROJECT_COLLECTION_SUFFIX = '_BakeProject'
_BAKE_GROUP_COLLECTION_SUFFIX = '_BakeGroup'

BAKE_ELIGIBLE_OBJECT_TYPES = frozenset({'MESH', 'EMPTY', 'GREASEPENCIL', 'CURVES'})

BAKE_GROUP_UI_LIST_CAPACITY = 128

_BAKE_OBJ_PROP_NAMES: tuple[str, ...] = (
    'lks_bake_role',
    'lks_bake_group_name',
    'lks_bake_clone',
    'lks_bake_source_name',
    'lks_bake_project_name',
)


def sanitize_bake_stem(name: str) -> str:
    """Safe stem for collection / group names (invalid chars → underscore)."""
    stem = re.sub(r'[^\w\-]+', '_', name.strip())
    return stem or 'bake_group'


def _project_collection_stem(project_name: str) -> str:
    """Collection stem from RNA name; sanitize only when Blender-name-unsafe."""
    stem = project_name.strip()
    if not stem:
        return 'BakeProject'
    if re.search(r'[^\w\-. ]', stem):
        sanitized = sanitize_bake_stem(stem)
        return 'BakeProject' if sanitized == 'bake_group' else sanitized
    return stem


def bake_project_root_collection_name(project_name: str) -> str:
    """Root collection name for a bake project RNA name."""
    return f'{_project_collection_stem(project_name)}{_BAKE_PROJECT_COLLECTION_SUFFIX}'


def bake_group_collection_name(group_name: str) -> str:
    """Bake group root collection name for a bake group RNA stem."""
    return f'{group_name}{_BAKE_GROUP_COLLECTION_SUFFIX}'


def _bake_group_name_from_collection(collection_name: str) -> str | None:
    """RNA stem from a bake group root collection name, if suffixed."""
    if collection_name.endswith(_BAKE_GROUP_COLLECTION_SUFFIX):
        return collection_name[: -len(_BAKE_GROUP_COLLECTION_SUFFIX)]
    return None


def default_bake_project_output_dir(project_name: str) -> str:
    """Auto default output_dir when a project is created or renamed."""
    return f'//{project_name}_bake/'


def unique_bake_project_name(scene: bpy.types.Scene, base: str = 'BakeProject') -> str:
    """Unique bake project name.

    Args:
        scene: ``bpy.types.Scene`` value.
        base: ``str`` value.

    Returns:
        ``str`` result.
    """
    existing = {project.name for project in scene.lks_bake_projects}
    if base not in existing:
        return base
    counter = 1
    while f'{base}_{counter}' in existing:
        counter += 1
    return f'{base}_{counter}'


def schedule_bake_map_catalog_seed_if_needed(
    scene: bpy.types.Scene,
    project: LKS_PG_BakeProject,
) -> None:
    """Queue deferred map catalog seed (safe to call from UI draw contexts)."""
    if not needs_bake_map_catalog_seed(project):
        return
    key = (scene.name, project.name)
    if key in _pending_bake_map_catalog_seeds:
        return
    _pending_bake_map_catalog_seeds.add(key)
    scene_name = scene.name
    project_name = project.name

    def _deferred() -> float | None:
        _pending_bake_map_catalog_seeds.discard(key)
        scene_ref = bpy.data.scenes.get(scene_name)
        if scene_ref is None:
            return None
        for proj in scene_ref.lks_bake_projects:
            if proj.name == project_name:
                seed_bake_project_map_entries_if_needed(proj)
                break
        return None

    bpy.app.timers.register(_deferred, first_interval=0.0)


def create_bake_project(scene: bpy.types.Scene, name: str) -> LKS_PG_BakeProject:
    """Add bake project RNA row, root collection, default output_dir; set active."""
    root_name = bake_project_root_collection_name(name)
    root_collection = bpy.data.collections.new(root_name)
    scene.collection.children.link(root_collection)

    project = scene.lks_bake_projects.add()
    project.root_collection = root_collection
    project.name = name
    project.output_dir = default_bake_project_output_dir(name)

    seed_bake_project_map_entries(project)

    scene.lks_active_bake_project_index = len(scene.lks_bake_projects) - 1
    return project


def resolve_bake_project_stem_from_selection(
    context: bpy.types.Context,
    eligible: list[bpy.types.Object],
) -> str:
    """Stem for a new project from selection (active eligible, else first eligible)."""
    active = context.active_object
    if active is not None and active in eligible:
        return sanitize_bake_stem(active.name)
    return sanitize_bake_stem(eligible[0].name)


def _project_name_from_root_collection(root: bpy.types.Collection) -> str | None:
    if root.name.endswith(_BAKE_PROJECT_COLLECTION_SUFFIX):
        return root.name[: -len(_BAKE_PROJECT_COLLECTION_SUFFIX)]
    return None


def _collection_name_available(
    name: str,
    *,
    exclude: bpy.types.Collection | None = None,
) -> bool:
    coll = bpy.data.collections.get(name)
    return coll is None or coll == exclude


def _unique_root_collection_name(
    project_name: str,
    *,
    exclude: bpy.types.Collection | None = None,
) -> str:
    base = bake_project_root_collection_name(project_name)
    if _collection_name_available(base, exclude=exclude):
        return base
    counter = 1
    while True:
        candidate = f'{base}_{counter:02d}'
        if _collection_name_available(candidate, exclude=exclude):
            return candidate
        counter += 1


def rename_bake_project(
    project: LKS_PG_BakeProject,
    scene: bpy.types.Scene,
) -> None:
    """Sync root collection and default output_dir after RNA ``name`` changes."""
    new_name = project.name
    if not new_name:
        return

    root = project.root_collection
    old_name = _project_name_from_root_collection(root) if root is not None else None
    if old_name == new_name:
        return

    if root is not None:
        target_name = _unique_root_collection_name(new_name, exclude=root)
        if root.name != target_name:
            root.name = target_name

    if old_name is not None:
        old_default_output = default_bake_project_output_dir(old_name)
        if project.output_dir == old_default_output:
            project.output_dir = default_bake_project_output_dir(new_name)

    for obj in iter_bake_project_objects(project):
        if hasattr(obj, 'lks_bake_project_name') and getattr(obj, 'lks_bake_project_name') == old_name:
            obj.lks_bake_project_name = new_name


def get_project_root_collection(
    project: LKS_PG_BakeProject,
) -> bpy.types.Collection | None:
    """Return the bake project root collection ({Name}_BakeProject)."""
    return project.root_collection


def get_unassigned_parent(
    project: LKS_PG_BakeProject,
) -> bpy.types.Collection | None:
    """Parent for objects in the project but not assigned to any bake group."""
    return get_project_root_collection(project)


def eligible_bake_selected_objects(
    context: bpy.types.Context,
) -> list[bpy.types.Object]:
    """Selected objects eligible for in-place bake project / group staging."""
    return [
        obj for obj in context.selected_objects
        if obj.type in BAKE_ELIGIBLE_OBJECT_TYPES
    ]


def move_objects_to_collection(
    objects: list[bpy.types.Object],
    target_collection: bpy.types.Collection,
) -> int:
    """Unlink from every collection, then link only to target_collection."""
    moved = 0
    for obj in objects:
        if obj.name not in bpy.data.objects:
            continue
        if (
            len(obj.users_collection) == 1
            and obj.users_collection[0] == target_collection
        ):
            continue
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        if obj.name not in target_collection.objects:
            target_collection.objects.link(obj)
        moved += 1
    return moved


def move_objects_to_project_root(
    project: LKS_PG_BakeProject,
    objects: list[bpy.types.Object],
) -> int:
    """Move objects exclusively to the project root collection."""
    parent = get_unassigned_parent(project)
    if parent is None:
        return 0
    return move_objects_to_collection(objects, parent)


def ensure_child_collection(
    parent: bpy.types.Collection,
    name: str,
) -> bpy.types.Collection:
    """Return named child collection under parent, creating and linking if missing."""
    child = parent.children.get(name)
    if child is None:
        child = bpy.data.collections.new(name)
        parent.children.link(child)
    return child


def unique_bake_group_name(
    project: LKS_PG_BakeProject,
    base: str = 'BakeGroup',
) -> str:
    """Unique bake group stem within a project RNA list."""
    existing = {group.name for group in project.bake_groups}
    if base not in existing:
        return base
    counter = 1
    while f'{base}_{counter:02d}' in existing:
        counter += 1
    return f'{base}_{counter:02d}'


def _stamp_bake_object_metadata(
    obj: bpy.types.Object,
    *,
    project_name: str,
    group_name: str,
    role: str = 'UNASSIGNED',
) -> None:
    if hasattr(obj, 'lks_bake_project_name'):
        obj.lks_bake_project_name = project_name
    if hasattr(obj, 'lks_bake_group_name'):
        obj.lks_bake_group_name = group_name
    if hasattr(obj, 'lks_bake_role'):
        obj.lks_bake_role = role


def _unique_group_collection_name(
    project: LKS_PG_BakeProject,
    base: str,
    *,
    exclude: bpy.types.Collection | None = None,
) -> str:
    root = get_project_root_collection(project)
    if root is None:
        return base
    if root.children.get(base) is None or root.children.get(base) == exclude:
        if _collection_name_available(base, exclude=exclude):
            return base
    counter = 1
    while True:
        candidate = f'{base}_{counter:02d}'
        child = root.children.get(candidate)
        if child is None or child == exclude:
            if _collection_name_available(candidate, exclude=exclude):
                return candidate
        counter += 1


def _role_collection_names(group_name: str) -> tuple[str, str]:
    return f'{group_name}_high', f'{group_name}_low'


def get_bake_group_role_collection(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    role: str,
) -> bpy.types.Collection | None:
    """Return `{name}_high` or `{name}_low` child collection."""
    folder = get_bake_group_collection(project, group)
    if folder is None:
        return None
    child_name = _role_collection_names(group.name)[0 if role == 'HIGH' else 1]
    return folder.children.get(child_name)


def get_high_collections(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Collection]:
    """Primary high collection plus any `{name}_high*` child collections."""
    folder = get_bake_group_collection(project, group)
    collections: list[bpy.types.Collection] = []
    seen: set[str] = set()

    primary = group.high_collection or get_bake_group_role_collection(project, group, 'HIGH')
    if primary is not None:
        collections.append(primary)
        seen.add(primary.name)

    if folder is not None:
        for child in folder.children:
            if '_high' not in child.name or child.name in seen:
                continue
            collections.append(child)
            seen.add(child.name)
    return collections


def get_low_collections(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Collection]:
    """Primary low collection plus any nested `{name}_low*` under the bake group folder."""
    folder = get_bake_group_collection(project, group)
    collections: list[bpy.types.Collection] = []
    seen: set[str] = set()

    def add_low(coll: bpy.types.Collection | None) -> None:
        if coll is None or coll.name in seen:
            return
        collections.append(coll)
        seen.add(coll.name)

    add_low(group.low_collection or get_bake_group_role_collection(project, group, 'LOW'))

    def walk_low_descendants(coll: bpy.types.Collection) -> None:
        for child in coll.children:
            if '_low' in child.name:
                add_low(child)
            walk_low_descendants(child)

    if folder is not None:
        walk_low_descendants(folder)
    return collections


_BAKE_PREP_COLLECTION_NAME = BAKE_PREP_COLLECTION_STEM
_BAKE_LOW_PIPELINE_ARTIFACT_KEYS = ('lks_merged_lowpoly', 'lks_deep_apply_preview')
_BAKE_HIGH_PIPELINE_ARTIFACT_KEYS = ('lks_extracted_highpoly',)
_BAKE_GENERATED_GEOMETRY_KEYS = ('lks_merged_lowpoly', 'lks_extracted_highpoly')


def is_bake_low_pipeline_artifact(obj: bpy.types.Object) -> bool:
    """True for merged-low / deep-apply preview meshes that must not feed back into prep."""
    return any(obj.get(key) for key in _BAKE_LOW_PIPELINE_ARTIFACT_KEYS)


def is_bake_high_pipeline_artifact(obj: bpy.types.Object) -> bool:
    """True for extracted-high meshes that must not feed back into high prep."""
    return any(obj.get(key) for key in _BAKE_HIGH_PIPELINE_ARTIFACT_KEYS)


def is_bake_generated_geometry_artifact(obj: bpy.types.Object) -> bool:
    """True for merged-low / extracted-high meshes produced by bake or export pipelines."""
    return any(obj.get(key) for key in _BAKE_GENERATED_GEOMETRY_KEYS)


def iter_bake_group_generated_geometry_artifacts(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Tagged merged-low / extracted-high objects in the bake group collection tree."""
    return [
        obj for obj in iter_bake_group_objects(project, group)
        if is_bake_generated_geometry_artifact(obj)
    ]


def count_bake_project_generated_geometry_artifacts(
    project: LKS_PG_BakeProject,
) -> int:
    """Count merged-low / extracted-high pipeline meshes across all bake groups."""
    return sum(
        len(iter_bake_group_generated_geometry_artifacts(project, group))
        for group in project.bake_groups
    )


def delete_bake_pipeline_artifacts_for_group(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> int:
    """Remove tagged merged-low / extracted-high meshes; preserve sources and staging."""
    artifacts = iter_bake_group_generated_geometry_artifacts(project, group)
    if not artifacts:
        return 0

    removed = 0
    for obj in artifacts:
        if obj.name not in bpy.data.objects:
            continue
        if obj == group.high_root:
            group.high_root = None
        if obj == group.low_root:
            group.low_root = None
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1

    _sync_role_assigned_flags(project, group)
    return removed


def get_bake_project_prep_collection(
    project: LKS_PG_BakeProject,
) -> bpy.types.Collection | None:
    """``{Project}_BakeProject/_BAKE_PREP`` when present (project-level bake temp)."""
    root = get_project_root_collection(project)
    if root is None:
        return None
    for child in root.children:
        if is_bake_prep_collection_name(child.name):
            return child
    return None


def ensure_bake_project_prep_collection(
    project: LKS_PG_BakeProject,
) -> bpy.types.Collection | None:
    """Return or create ``_BAKE_PREP`` under the project root collection."""
    root = get_project_root_collection(project)
    if root is None:
        return None
    existing = get_bake_project_prep_collection(project)
    if existing is not None:
        return existing
    return ensure_child_collection(root, _BAKE_PREP_COLLECTION_NAME)


def delete_bake_project_prep_artifacts(
    project: LKS_PG_BakeProject,
) -> int:
    """Remove project-level merged-low / extracted-high meshes in ``_BAKE_PREP``."""
    prep = get_bake_project_prep_collection(project)
    if prep is None:
        return 0

    removed = 0
    for obj in list(prep.objects):
        if obj.name not in bpy.data.objects:
            continue
        if not is_bake_generated_geometry_artifact(obj):
            continue
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
    return removed


def delete_bake_pipeline_artifacts_for_project(
    project: LKS_PG_BakeProject,
) -> int:
    """Remove generated bake geometry artifacts for project prep and every group."""
    removed = delete_bake_project_prep_artifacts(project)
    for group in list(project.bake_groups):
        removed += delete_bake_pipeline_artifacts_for_group(project, group)
    return removed


def _iter_objects_in_role_collections(
    collections: list[bpy.types.Collection],
    *,
    exclude_bake_prep: bool = True,
    is_pipeline_artifact=is_bake_low_pipeline_artifact,
) -> list[bpy.types.Object]:
    """Unique objects in role collections, nested subcollections, and parent chains."""
    seen: set[str] = set()
    objects: list[bpy.types.Object] = []

    def walk_collection(coll: bpy.types.Collection) -> None:
        if exclude_bake_prep and is_bake_prep_collection_name(coll.name):
            return
        for obj in coll.objects:
            if obj.name in seen or is_pipeline_artifact(obj):
                continue
            seen.add(obj.name)
            objects.append(obj)
        for child_coll in coll.children:
            walk_collection(child_coll)

    for coll in collections:
        walk_collection(coll)

    stack = list(objects)
    while stack:
        obj = stack.pop()
        for child in obj.children:
            if child.name in seen or is_pipeline_artifact(child):
                continue
            seen.add(child.name)
            objects.append(child)
            stack.append(child)

    return objects


def iter_bake_group_high_objects(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Objects in all high-role collections for this bake group."""
    return _iter_objects_in_role_collections(
        get_high_collections(project, group),
        is_pipeline_artifact=is_bake_high_pipeline_artifact,
    )


def iter_bake_group_low_objects(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Objects in all low-role collections for this bake group."""
    return _iter_objects_in_role_collections(get_low_collections(project, group))


def create_bake_group(
    project: LKS_PG_BakeProject,
    name: str,
    scene: bpy.types.Scene,
) -> LKS_PG_BakeGroup:
    """Append bake group RNA row and `{name}_BakeGroup/` + role subcollections under project root."""
    root = get_project_root_collection(project)
    if root is None:
        raise ValueError('Bake project has no root collection')

    group_folder = ensure_child_collection(root, bake_group_collection_name(name))
    high_name, low_name = _role_collection_names(name)
    high_coll = ensure_child_collection(group_folder, high_name)
    low_coll = ensure_child_collection(group_folder, low_name)

    bake_group = project.bake_groups.add()
    bake_group.name = name
    bake_group.sources_collection = group_folder
    bake_group.high_collection = high_coll
    bake_group.low_collection = low_coll
    bake_group.high_assigned = False
    bake_group.low_assigned = False

    project.active_bake_group_index = len(project.bake_groups) - 1
    ensure_bake_group_ui_slots(bake_group)
    return bake_group


def rename_bake_group(
    group: LKS_PG_BakeGroup,
    scene: bpy.types.Scene,
) -> None:
    """Sync collection tree and role roots after RNA ``name`` changes."""
    new_name = group.name
    if not new_name:
        return

    folder = group.sources_collection
    if folder is None:
        return

    old_name = _bake_group_name_from_collection(folder.name) or folder.name
    if old_name == new_name:
        return

    project: LKS_PG_BakeProject | None = None
    for scene_project in scene.lks_bake_projects:
        for bake_group in scene_project.bake_groups:
            if bake_group == group:
                project = scene_project
                break
        if project is not None:
            break
    if project is None:
        return

    target_folder_name = _unique_group_collection_name(
        project,
        bake_group_collection_name(new_name),
        exclude=folder,
    )
    if folder.name != target_folder_name:
        folder.name = target_folder_name

    old_high, old_low = _role_collection_names(old_name)
    new_high, new_low = _role_collection_names(new_name)
    high_coll = folder.children.get(old_high) or folder.children.get(new_high)
    low_coll = folder.children.get(old_low) or folder.children.get(new_low)
    if high_coll is not None and high_coll.name != new_high:
        high_coll.name = new_high
    if low_coll is not None and low_coll.name != new_low:
        low_coll.name = new_low

    if high_coll is not None:
        group.high_collection = high_coll
    if low_coll is not None:
        group.low_collection = low_coll

    for obj in iter_bake_group_objects(project, group):
        if hasattr(obj, 'lks_bake_group_name') and getattr(obj, 'lks_bake_group_name') == old_name:
            obj.lks_bake_group_name = new_name


def assign_objects_to_bake_group(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    objects: list[bpy.types.Object],
) -> int:
    """Move eligible objects exclusively to `{name}_BakeGroup/` staging folder."""
    return move_objects_to_bake_group_staging(project, group, objects)


def unassign_objects_from_bake_group(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    objects: list[bpy.types.Object],
    scene: bpy.types.Scene,
) -> int:
    """Unlink objects from the bake group collection tree; move to scene collection only."""
    if not objects:
        return 0

    group_colls = set(iter_bake_group_collections(project, group))
    bake_roots = _bake_organizer_roots(group)
    removed = 0

    for obj in objects:
        if not any(coll in group_colls for coll in obj.users_collection):
            continue
        removed += 1
        if obj == group.high_root:
            group.high_root = None
        if obj == group.low_root:
            group.low_root = None
        if obj.parent in bake_roots:
            obj.parent = None
        clear_bake_object_metadata(obj)
        move_objects_to_collection([obj], scene.collection)
        _try_remove_orphan_organizer(obj, bake_roots)

    _sync_role_assigned_flags(project, group)
    return removed


def selected_objects_in_bake_group(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Selected objects linked anywhere in the active bake group tree."""
    group_names = {obj.name for obj in iter_bake_group_objects(project, group)}
    return [obj for obj in context.selected_objects if obj.name in group_names]


def assignable_bake_selected_objects(
    context: bpy.types.Context,
) -> list[bpy.types.Object]:
    """Selected objects eligible to move into a bake group staging folder."""
    return eligible_bake_selected_objects(context)


def _has_object_ancestor(
    obj: bpy.types.Object,
    ancestor: bpy.types.Object,
) -> bool:
    current = obj.parent
    while current is not None:
        if current == ancestor:
            return True
        current = current.parent
    return False


def _object_in_collection_tree(
    obj: bpy.types.Object,
    coll: bpy.types.Collection | None,
) -> bool:
    if coll is None:
        return False
    if obj.name in coll.objects:
        return True
    current = obj.parent
    while current is not None:
        if current.name in coll.objects:
            return True
        current = current.parent
    return False


def _sync_role_assigned_flags(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> None:
    group.high_assigned = any(
        collection_has_objects(coll) for coll in get_high_collections(project, group)
    )
    group.low_assigned = any(
        collection_has_objects(coll) for coll in get_low_collections(project, group)
    )


def find_bake_group_project(
    scene: bpy.types.Scene,
    group: LKS_PG_BakeGroup,
) -> LKS_PG_BakeProject | None:
    """Return the bake project that owns ``group``, if any."""
    for project in scene.lks_bake_projects:
        for bake_group in project.bake_groups:
            if bake_group == group:
                return project
    return None


def get_bake_group_objects_list(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[tuple[bpy.types.Object, str]]:
    """Live (object, role_label) rows for bake group contents UIList."""
    return [
        (obj, resolve_object_bake_role_label(project, group, obj))
        for obj in iter_bake_group_objects(project, group)
    ]


def ensure_bake_group_ui_slots(group: LKS_PG_BakeGroup) -> None:
    """Pre-allocate fixed UIList placeholder slots (operators / register only)."""
    slots = group.ui_list_slots
    for _ in range(BAKE_GROUP_UI_LIST_CAPACITY - len(slots)):
        slots.add()


def migrate_bake_group_ui_slots_all_scenes() -> None:
    """Ensure existing bake groups have UIList slots (deferred post-register only)."""
    scenes = getattr(bpy.data, 'scenes', None)
    if scenes is None:
        return
    for scene in scenes:
        for project in scene.lks_bake_projects:
            for group in project.bake_groups:
                ensure_bake_group_ui_slots(group)


def resolve_object_bake_role_label(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    obj: bpy.types.Object,
) -> str:
    """Role badge for contents list: staging | high | low | unassigned."""
    folder = get_bake_group_collection(project, group)
    if folder is None:
        return 'unassigned'

    for high_coll in get_high_collections(project, group):
        if _object_in_collection_tree(obj, high_coll):
            return 'high'
    for low_coll in get_low_collections(project, group):
        if _object_in_collection_tree(obj, low_coll):
            return 'low'
    if group.high_root is not None:
        if obj == group.high_root or _has_object_ancestor(obj, group.high_root):
            return 'high'
    if group.low_root is not None:
        if obj == group.low_root or _has_object_ancestor(obj, group.low_root):
            return 'low'
    if obj.name in folder.objects:
        return 'staging'
    return 'unassigned'


def move_objects_to_bake_group_staging(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    objects: list[bpy.types.Object],
) -> int:
    """Move objects exclusively to `{name}_BakeGroup/`; stamp staging metadata."""
    folder = get_bake_group_collection(project, group) or group.sources_collection
    if folder is None:
        return 0
    moved = move_objects_to_collection(objects, folder)
    for obj in objects:
        _stamp_bake_object_metadata(
            obj,
            project_name=project.name,
            group_name=group.name,
            role='UNASSIGNED',
        )
    return moved


def _role_container_name(group_name: str, role: str) -> str:
    return f'{group_name}_high' if role == 'HIGH' else f'{group_name}_low'


def _objects_in_group_staging(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Objects linked directly to `{name}_BakeGroup/` (not role subcollections)."""
    folder = get_bake_group_collection(project, group)
    if folder is None:
        return []
    return list(folder.objects)


def selected_objects_in_group_staging(
    context: bpy.types.Context,
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Selected objects currently staged in the active group's root folder."""
    staging = {obj.name for obj in _objects_in_group_staging(project, group)}
    return [obj for obj in context.selected_objects if obj.name in staging]


def assign_bake_role(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    objects: list[bpy.types.Object],
    role: str,
) -> bpy.types.Collection | None:
    """Move selection exclusively into `{name}_BakeGroup/{name}_high|low/`; objects keep their names."""
    if not objects:
        return None

    group_name = group.name
    role_name = _role_container_name(group_name, role)
    folder = get_bake_group_collection(project, group)
    if folder is None:
        return None

    coll_attr = 'high_collection' if role == 'HIGH' else 'low_collection'
    role_coll = getattr(group, coll_attr) or get_bake_group_role_collection(project, group, role)
    if role_coll is None:
        role_coll = ensure_child_collection(folder, role_name)
        setattr(group, coll_attr, role_coll)

    move_objects_to_collection(objects, role_coll)
    for obj in objects:
        _stamp_bake_object_metadata(
            obj,
            project_name=project.name,
            group_name=group_name,
            role=role,
        )

    _sync_role_assigned_flags(project, group)
    return role_coll


def resolve_role_from_selection(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    selected: list[bpy.types.Object],
) -> str | None:
    """Return 'HIGH' or 'LOW' when selection resolves to a role collection."""
    for obj in selected:
        for high_coll in get_high_collections(project, group):
            if _object_in_collection_tree(obj, high_coll):
                return 'HIGH'
        for low_coll in get_low_collections(project, group):
            if _object_in_collection_tree(obj, low_coll):
                return 'LOW'
        if group.high_root == obj:
            return 'HIGH'
        if group.low_root == obj:
            return 'LOW'
        if group.high_root is not None and obj.parent == group.high_root:
            return 'HIGH'
        if group.low_root is not None and obj.parent == group.low_root:
            return 'LOW'
    return None


def clear_bake_role(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    role: str,
    scene: bpy.types.Scene,
) -> None:
    """Move role contents back to `{name}_BakeGroup/` staging; objects keep their names."""
    coll_attr = 'high_collection' if role == 'HIGH' else 'low_collection'
    role_coll = getattr(group, coll_attr) or get_bake_group_role_collection(project, group, role)
    if role_coll is None:
        return

    folder = get_bake_group_collection(project, group)
    to_restage = list(role_coll.objects)
    for obj in to_restage:
        if folder is not None:
            move_objects_to_collection([obj], folder)
        _stamp_bake_object_metadata(
            obj,
            project_name=project.name,
            group_name=group.name,
            role='UNASSIGNED',
        )

    _sync_role_assigned_flags(project, group)


def get_bake_group_collection(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bpy.types.Collection | None:
    """Return the bake group folder ({name}_BakeGroup) directly under the project root."""
    root = project.root_collection
    if root is None:
        return group.sources_collection
    coll = root.children.get(bake_group_collection_name(group.name))
    if coll is not None:
        return coll
    return group.sources_collection


def _group_collections(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Collection]:
    collections: list[bpy.types.Collection] = []
    folder = get_bake_group_collection(project, group)
    if folder is not None:
        collections.append(folder)
        stem = group.name
        for child_name in (f'{stem}_high', f'{stem}_low'):
            child = folder.children.get(child_name)
            if child is not None:
                collections.append(child)
    elif group.sources_collection is not None:
        collections.append(group.sources_collection)
    return collections


def clear_bake_object_metadata(obj: bpy.types.Object) -> None:
    """Revert stamped lks_bake_* object metadata when registered."""
    for prop_name in _BAKE_OBJ_PROP_NAMES:
        if not hasattr(obj, prop_name):
            continue
        prop = obj.bl_rna.properties.get(prop_name)
        if prop is None:
            continue
        if prop.type == 'BOOLEAN':
            setattr(obj, prop_name, False)
        else:
            setattr(obj, prop_name, prop.default)


def _bake_organizer_roots(group: LKS_PG_BakeGroup) -> set[bpy.types.Object]:
    roots: set[bpy.types.Object] = set()
    for pointer in (group.high_root, group.low_root):
        if pointer is not None:
            roots.add(pointer)
    return roots


def ensure_object_in_scene_collection(
    obj: bpy.types.Object,
    scene: bpy.types.Scene,
) -> None:
    """Move object exclusively to the scene master collection."""
    if obj.name not in bpy.data.objects:
        return
    move_objects_to_collection([obj], scene.collection)


def _try_remove_orphan_organizer(
    obj: bpy.types.Object,
    bake_roots: set[bpy.types.Object],
) -> None:
    if obj.name not in bpy.data.objects:
        return
    if obj.users_collection:
        return
    if obj.type != 'EMPTY':
        return
    if obj not in bake_roots:
        return
    bpy.data.objects.remove(obj, do_unlink=True)


def unlink_objects_from_collection(
    coll: bpy.types.Collection | None,
    *,
    scene: bpy.types.Scene,
    bake_roots: set[bpy.types.Object] | None = None,
) -> None:
    """Unlink all objects from a collection; reparent orphans to scene root."""
    if coll is None:
        return
    roots = bake_roots or set()
    for obj in list(coll.objects):
        coll.objects.unlink(obj)
        clear_bake_object_metadata(obj)
        ensure_object_in_scene_collection(obj, scene)
        _try_remove_orphan_organizer(obj, roots)


def dissolve_collection_tree(
    coll: bpy.types.Collection | None,
    scene: bpy.types.Scene,
) -> None:
    """Unlink objects and remove empty collections bottom-up."""
    if coll is None:
        return
    for child in list(coll.children):
        dissolve_collection_tree(child, scene)
    unlink_objects_from_collection(coll, scene=scene)
    for parent in list(bpy.data.collections):
        if coll.name in parent.children:
            parent.children.unlink(coll)
    if coll.users == 0:
        bpy.data.collections.remove(coll)


def collection_has_objects(coll: bpy.types.Collection | None) -> bool:
    """Collection has objects.

    Args:
        coll: ``bpy.types.Collection | None`` value.

    Returns:
        ``bool`` result.
    """
    if coll is None:
        return False
    if len(coll.objects) > 0:
        return True
    return any(collection_has_objects(child) for child in coll.children)


def bake_group_has_geometry(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bool:
    """True when staging or role containers hold objects."""
    for coll in _group_collections(project, group):
        if collection_has_objects(coll):
            return True
    return False


def bake_project_has_geometry(project: LKS_PG_BakeProject) -> bool:
    """Bake project has geometry.

    Args:
        project: Bake export project RNA/settings object.

    Returns:
        ``bool`` result.
    """
    return any(bake_group_has_geometry(project, group) for group in project.bake_groups)


def iter_bake_group_collections(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Collection]:
    """Collections in a bake group's subtree (group folder, high, low)."""
    folder = get_bake_group_collection(project, group)
    if folder is None:
        return [coll for coll in _group_collections(project, group) if coll is not None]
    collections: list[bpy.types.Collection] = [folder]
    stack = list(folder.children)
    while stack:
        coll = stack.pop()
        collections.append(coll)
        stack.extend(coll.children)
    return collections


def iter_bake_group_objects(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> list[bpy.types.Object]:
    """Objects linked in the bake group collection tree (includes parented descendants)."""
    seen: set[str] = set()
    objects: list[bpy.types.Object] = []
    for coll in iter_bake_group_collections(project, group):
        stack = list(coll.objects)
        while stack:
            obj = stack.pop()
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
            stack.extend(obj.children)
    return objects


def bake_group_any_visible(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
) -> bool:
    """True when at least one group object is visible in the viewport."""
    objects = iter_bake_group_objects(project, group)
    if not objects:
        return True
    return any(not obj.hide_viewport for obj in objects)


def iter_bake_project_collections(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Collection]:
    """All collections under the project root (root + unassigned + group subtree)."""
    root = project.root_collection
    if root is None:
        return []
    collections: list[bpy.types.Collection] = []
    stack = [root]
    while stack:
        coll = stack.pop()
        collections.append(coll)
        stack.extend(coll.children)
    return collections


def iter_bake_project_objects(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    """Objects under root_collection (collections + parented descendants)."""
    from .static_utilities.bake_view_layer_helpers import iter_objects_in_collection_tree

    return iter_objects_in_collection_tree(project.root_collection)


def bake_project_any_visible(project: LKS_PG_BakeProject) -> bool:
    """True when at least one project object is visible in the viewport."""
    objects = iter_bake_project_objects(project)
    if not objects:
        return True
    return any(not obj.hide_viewport for obj in objects)


def iter_bake_project_high_objects(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    """High-role objects across every bake group in the project."""
    seen: set[str] = set()
    objects: list[bpy.types.Object] = []
    for group in project.bake_groups:
        for obj in iter_bake_group_high_objects(project, group):
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
    return objects


def iter_bake_project_low_objects(
    project: LKS_PG_BakeProject,
) -> list[bpy.types.Object]:
    """Low-role objects across every bake group in the project."""
    seen: set[str] = set()
    objects: list[bpy.types.Object] = []
    for group in project.bake_groups:
        for obj in iter_bake_group_low_objects(project, group):
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
    return objects


def _iter_bake_role_objects(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup | None,
    *,
    role: str,
) -> list[bpy.types.Object]:
    if role == 'high':
        if group is None:
            return iter_bake_project_high_objects(project)
        return iter_bake_group_high_objects(project, group)
    if group is None:
        return iter_bake_project_low_objects(project)
    return iter_bake_group_low_objects(project, group)


def bake_role_objects_any_visible(objects: list[bpy.types.Object]) -> bool:
    """True when at least one object is visible in the viewport (empty → visible)."""
    if not objects:
        return True
    return any(not obj.hide_viewport for obj in objects)


def bake_project_role_any_visible(
    project: LKS_PG_BakeProject,
    *,
    role: str,
) -> bool:
    """True when at least one project-wide high/low object is viewport-visible."""
    return bake_role_objects_any_visible(
        _iter_bake_role_objects(project, None, role=role),
    )


def bake_group_role_any_visible(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    *,
    role: str,
) -> bool:
    """True when at least one group high/low object is viewport-visible."""
    return bake_role_objects_any_visible(
        _iter_bake_role_objects(project, group, role=role),
    )


def toggle_bake_role_objects_visibility(
    objects: list[bpy.types.Object],
) -> tuple[int, bool]:
    """Toggle viewport visibility for role objects. Returns (count, hide_set)."""
    hide = bake_role_objects_any_visible(objects)
    for obj in objects:
        obj.hide_viewport = hide
    return len(objects), hide


def toggle_bake_project_role_visibility(
    project: LKS_PG_BakeProject,
    *,
    role: str,
) -> tuple[int, bool]:
    """Toggle viewport visibility for all high/low objects in the project."""
    objects = _iter_bake_role_objects(project, None, role=role)
    return toggle_bake_role_objects_visibility(objects)


def toggle_bake_group_role_visibility(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    *,
    role: str,
) -> tuple[int, bool]:
    """Toggle viewport visibility for one bake group's high/low objects."""
    objects = _iter_bake_role_objects(project, group, role=role)
    return toggle_bake_role_objects_visibility(objects)


def cleanup_bake_group_collections(
    project: LKS_PG_BakeProject,
    group: LKS_PG_BakeGroup,
    scene: bpy.types.Scene,
) -> None:
    """Unlink objects and dissolve the group's collection folder tree."""
    bake_roots = _bake_organizer_roots(group)
    for coll in _group_collections(project, group):
        unlink_objects_from_collection(coll, scene=scene, bake_roots=bake_roots)

    group.high_root = None
    group.low_root = None
    group.high_collection = None
    group.low_collection = None
    group.sources_collection = None

    folder = get_bake_group_collection(project, group)
    if folder is not None:
        dissolve_collection_tree(folder, scene)


def cleanup_bake_group(
    project: LKS_PG_BakeProject,
    group_index: int,
    scene: bpy.types.Scene,
) -> None:
    """Full group teardown: collections, pointers, RNA row, active index clamp."""
    if not (0 <= group_index < len(project.bake_groups)):
        return
    group = project.bake_groups[group_index]
    cleanup_bake_group_collections(project, group, scene)
    project.bake_groups.remove(group_index)
    clamp_active_bake_group_index(project)


def cleanup_bake_project(
    project: LKS_PG_BakeProject,
    scene: bpy.types.Scene,
) -> None:
    """Dissolve group trees and root collection; clear root pointer before remove."""
    while project.bake_groups:
        cleanup_bake_group(project, 0, scene)

    root = project.root_collection
    project.root_collection = None
    if root is not None:
        dissolve_collection_tree(root, scene)

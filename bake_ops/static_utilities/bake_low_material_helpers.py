"""Baker-managed single low material per bake project (uniquify + slot override)."""

from __future__ import annotations

import bpy

from lks_baker.shared_utilities import object_helpers
from lks_baker.shared_utilities.collection_instance_helpers import get_instanced_collection, is_colinst_object
from lks_baker.shared_utilities.grouppro_helpers import is_grouppro_placeholder_object
from lks_baker.shared_utilities.lks_constants import (
    BAKE_IMAGE_FILE_TYPE_DEFAULT,
    BAKE_IMAGE_FILE_TYPE_EXTENSIONS,
    BAKE_LOW_MATERIAL_DEFAULT_PREFIX,
    BAKE_LOW_MATERIAL_SUFFIX,
)


def bake_low_material_prefix(
    project,
    scene: bpy.types.Scene | None = None,
) -> str:
    """Project material prefix; empty project value falls back to scene then ``MI_``."""
    raw = (getattr(project, 'lks_material_prefix', None) or '').strip()
    if raw:
        return raw
    if scene is not None:
        scene_raw = (
            getattr(scene, 'lks_asset_prefix_mat', BAKE_LOW_MATERIAL_DEFAULT_PREFIX)
            or BAKE_LOW_MATERIAL_DEFAULT_PREFIX
        ).strip()
        if scene_raw:
            return scene_raw
    return BAKE_LOW_MATERIAL_DEFAULT_PREFIX


def bake_low_material_suffix(project) -> str:
    """Project material suffix for bake low materials."""
    return (
        getattr(project, 'lks_material_suffix', BAKE_LOW_MATERIAL_SUFFIX)
        or BAKE_LOW_MATERIAL_SUFFIX
    )


def bake_image_file_extension(project) -> str:
    """Lowercase file extension for the project's baked texture images."""
    image_file_type = getattr(
        project,
        'lks_image_file_type',
        BAKE_IMAGE_FILE_TYPE_DEFAULT,
    )
    return BAKE_IMAGE_FILE_TYPE_EXTENSIONS.get(image_file_type, 'png')


def bake_project_low_material_name(
    project_name: str,
    *,
    prefix: str = BAKE_LOW_MATERIAL_DEFAULT_PREFIX,
    suffix: str = BAKE_LOW_MATERIAL_SUFFIX,
) -> str:
    """``{prefix}{project_export_stem}{suffix}`` — one texture set per bake project."""
    stem = project_name.strip() or 'BakeProject'
    return f'{prefix}{stem}{suffix}'


def ensure_bake_project_low_material(
    project,
    scene: bpy.types.Scene | None = None,
) -> bpy.types.Material:
    """Return existing or newly created baker-managed low material for a project."""
    mat_name = bake_project_low_material_name(
        project.name,
        prefix=bake_low_material_prefix(project, scene),
        suffix=bake_low_material_suffix(project),
    )
    material = bpy.data.materials.get(mat_name)
    if material is not None:
        return material

    material = bpy.data.materials.new(name=mat_name)
    material.use_nodes = True
    principled = material.node_tree.nodes.get('Principled BSDF')
    if principled is not None:
        principled.inputs['Roughness'].default_value = 0.5
    return material


def _iter_collection_objects_recursive(
    coll: bpy.types.Collection,
) -> list[bpy.types.Object]:
    """All objects in ``coll`` including nested child collections."""
    objects: list[bpy.types.Object] = []
    seen: set[str] = set()

    def walk(collection: bpy.types.Collection) -> None:
        for obj in collection.objects:
            if obj.name in seen:
                continue
            seen.add(obj.name)
            objects.append(obj)
        for child_coll in collection.children:
            walk(child_coll)

    walk(coll)
    return objects


def _collection_forest_roots(coll: bpy.types.Collection) -> list[bpy.types.Object]:
    members = _iter_collection_objects_recursive(coll)
    names = {obj.name for obj in members}
    return [
        obj for obj in members
        if obj.parent is None or obj.parent.name not in names
    ]


def _append_expanded_meshes_from_object(
    obj: bpy.types.Object,
    seen: set[str],
    meshes: list[bpy.types.Object],
) -> None:
    if not object_helpers.is_object_alive(obj) or obj.name in seen:
        return
    seen.add(obj.name)

    if (
        obj.type == 'MESH'
        and obj.data is not None
        and not is_grouppro_placeholder_object(obj)
    ):
        meshes.append(obj)

    if is_colinst_object(obj):
        inst_coll = get_instanced_collection(obj)
        if inst_coll is not None:
            for root in _collection_forest_roots(inst_coll):
                _append_expanded_meshes_from_object(root, seen, meshes)

    for child in obj.children:
        _append_expanded_meshes_from_object(child, seen, meshes)


def collect_hierarchy_meshes_expanded(
    roots: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    """Meshes under roots, expanding collection instances and Group Pro groups."""
    seen: set[str] = set()
    meshes: list[bpy.types.Object] = []
    for root in object_helpers.filter_valid_objects(roots):
        _append_expanded_meshes_from_object(root, seen, meshes)
    return meshes


def apply_single_material_to_mesh(
    obj: bpy.types.Object,
    material: bpy.types.Material,
) -> bool:
    """Uniquify mesh data and assign ``material`` as the only slot."""
    if obj.type != 'MESH' or obj.data is None:
        return False
    object_helpers.ensure_single_user_mesh_data(obj)
    mesh = obj.data
    mesh.materials.clear()
    mesh.materials.append(material)
    return True


def apply_single_material_to_mesh_hierarchy(
    roots: list[bpy.types.Object],
    material: bpy.types.Material,
) -> int:
    """Uniquify and single-slot override on every expanded mesh under ``roots``."""
    count = 0
    for obj in collect_hierarchy_meshes_expanded(roots):
        if apply_single_material_to_mesh(obj, material):
            count += 1
    return count


def uniquify_and_apply_bake_low_material(
    project,
    roots: list[bpy.types.Object],
    scene: bpy.types.Scene | None = None,
) -> int:
    """Ensure project low material exists, uniquify meshes in scope, apply material."""
    if not roots:
        return 0
    material = ensure_bake_project_low_material(project, scene)
    return apply_single_material_to_mesh_hierarchy(roots, material)

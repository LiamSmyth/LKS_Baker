import bpy
from mathutils import Matrix
from typing import Dict, List, Optional

from . import object_helpers
from .geonodes_modifier_helpers import get_nodes_modifier_input, set_nodes_modifier_input
from .transform_apply_helpers import smart_transform_mesh_data
from .lks_constants import GPRO_COLL_SOCKET, GPRO_INSTANCE_MOD

GPRO_ADDON_MODULE = "GroupPro"
GPRO_PLACEHOLDER_MESH_NAMES = frozenset({"GP_EMPTY_MESH", "gp_bbox_mesh"})


def is_grouppro_mesh_group(obj: bpy.types.Object) -> bool:
    if obj is None or obj.type != "MESH":
        return False
    group_mod = obj.modifiers.get(GPRO_INSTANCE_MOD)
    if not group_mod or group_mod.type != "NODES":
        return False
    return bool(get_nodes_modifier_input(group_mod, GPRO_COLL_SOCKET))


def is_legacy_grouppro_collection_instance(obj: bpy.types.Object) -> bool:
    return (
        obj is not None
        and obj.type == "EMPTY"
        and obj.instance_type == "COLLECTION"
        and obj.instance_collection is not None
    )


def is_exportable_grouppro_group(obj: bpy.types.Object) -> bool:
    return is_grouppro_mesh_group(obj) or is_legacy_grouppro_collection_instance(obj)


def get_exportable_grouppro_groups(
    objects: List[bpy.types.Object],
) -> List[bpy.types.Object]:
    return [obj for obj in objects if is_exportable_grouppro_group(obj)]


def is_grouppro_placeholder_mesh(mesh: bpy.types.Mesh) -> bool:
    if mesh is None:
        return False
    if mesh.name in GPRO_PLACEHOLDER_MESH_NAMES:
        return True
    if mesh.name.startswith("GP_EMPTY_MESH") or mesh.name.startswith("gp_bbox"):
        return True
    return False


def is_grouppro_placeholder_object(obj: bpy.types.Object) -> bool:
    if obj is None:
        return False
    if is_grouppro_mesh_group(obj):
        return True
    if obj.type != "MESH" or obj.data is None:
        return False
    if is_grouppro_placeholder_mesh(obj.data):
        return True
    if obj.name.startswith("gp_bbox_object"):
        return True
    return False


def get_grouppro_collection(group_obj: bpy.types.Object) -> Optional[bpy.types.Collection]:
    group_mod = group_obj.modifiers.get(GPRO_INSTANCE_MOD)
    if not group_mod:
        return None
    return get_nodes_modifier_input(group_mod, GPRO_COLL_SOCKET)


def _duplicate_group_collection_member(child: bpy.types.Object) -> Optional[bpy.types.Object]:
    if is_grouppro_placeholder_object(child) and not is_grouppro_mesh_group(child):
        return None

    if is_grouppro_mesh_group(child):
        return child.copy()

    if child.type == "EMPTY" and child.instance_collection:
        return child.copy()

    if child.type != "MESH" or child.data is None:
        return None

    new_child = child.copy()
    new_child.data = child.data.copy()
    return new_child


def _apply_all_modifiers_on_object(obj: bpy.types.Object) -> None:
    if obj.type != "MESH" or not obj.modifiers:
        return

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    if obj.data and obj.data.users > 1:
        obj.data = obj.data.copy()

    for mod in list(obj.modifiers):
        if mod.name == GPRO_INSTANCE_MOD:
            continue
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except RuntimeError as exc:
            print(f"Could not apply modifier '{mod.name}' on '{obj.name}': {exc}")


def _hide_gp_mesh_source(obj: bpy.types.Object) -> bool:
    if obj.hide_viewport and obj.hide_render:
        return False
    obj.hide_viewport = True
    obj.hide_render = True
    return True


def _multi_instance_source_roots(sources: set[bpy.types.Object]) -> set[str]:
    """Basenames for depsgraph-multiplied sources (e.g. ``pop_object`` from ``pop_object.001``)."""
    roots: set[str] = set()
    for obj in sources:
        if "." in obj.name:
            base, suffix = obj.name.rsplit(".", 1)
            if suffix.isdigit():
                roots.add(base)
                continue
        roots.add(obj.name)
    return roots


def _is_orphan_multi_instance_copy(name: str, root: str) -> bool:
    if name == root:
        return True
    if not name.startswith(f"{root}."):
        return False
    suffix = name[len(root) + 1 :]
    return suffix.isdigit()


def _build_gp_outliner_empty_tree(
    group_obj: bpy.types.Object,
    root_empty: bpy.types.Object,
) -> tuple[dict[int, bpy.types.Object], dict[int, bpy.types.Object]]:
    """
    Mirror GP collection structure with identity empties for outliner grouping.

    Mesh duplicates still bake transforms relative to ``root_empty``; folder empties
    carry no transform (matrix_basis identity).
    """
    coll_to_empty: dict[int, bpy.types.Object] = {}
    source_to_empty: dict[int, bpy.types.Object] = {}
    gp_root = get_grouppro_collection(group_obj)
    if gp_root is None:
        return coll_to_empty, source_to_empty

    def ensure_coll_empty(
        coll: bpy.types.Collection,
        parent_empty: bpy.types.Object,
    ) -> bpy.types.Object:
        coll_id = id(coll)
        existing = coll_to_empty.get(coll_id)
        if existing is not None:
            return existing
        node = bpy.data.objects.new(coll.name, None)
        bpy.context.scene.collection.objects.link(node)
        node.parent = parent_empty
        node.matrix_world = parent_empty.matrix_world.copy()
        coll_to_empty[coll_id] = node
        return node

    def walk(coll: bpy.types.Collection, parent_empty: bpy.types.Object) -> None:
        coll_empty = ensure_coll_empty(coll, parent_empty)
        for obj in coll.objects:
            if is_grouppro_mesh_group(obj):
                gp_folder = bpy.data.objects.new(f"{obj.name}_gp", None)
                bpy.context.scene.collection.objects.link(gp_folder)
                gp_folder.parent = coll_empty
                gp_folder.matrix_world = coll_empty.matrix_world.copy()
                nested = get_grouppro_collection(obj)
                if nested is not None:
                    walk(nested, gp_folder)
                continue
            if obj.type != "MESH" or is_grouppro_placeholder_object(obj):
                continue
            source_to_empty[id(obj)] = coll_empty
        for child_coll in coll.children:
            walk(child_coll, coll_empty)

    walk(gp_root, root_empty)
    return coll_to_empty, source_to_empty


def _outliner_parent_for_gp_source(
    original: bpy.types.Object,
    *,
    source_to_empty: dict[int, bpy.types.Object],
    coll_to_empty: dict[int, bpy.types.Object],
    root_empty: bpy.types.Object,
) -> bpy.types.Object:
    parent = source_to_empty.get(id(original))
    if parent is not None:
        return parent
    for coll in original.users_collection:
        parent = coll_to_empty.get(id(coll))
        if parent is not None:
            return parent
    return root_empty


def _suppress_gp_source_meshes(
    group_obj: bpy.types.Object,
    *,
    keep_names: set[str],
    realized_sources: set[bpy.types.Object] | None = None,
) -> int:
    """Hide GP collection source meshes replaced by depsgraph realize."""
    root_coll = get_grouppro_collection(group_obj)
    if root_coll is None:
        return 0

    sources = realized_sources or set()
    instance_roots = _multi_instance_source_roots(sources)
    visited_coll_ids: set[int] = set()
    hidden = 0
    stack = [root_coll]
    while stack:
        coll = stack.pop()
        coll_id = id(coll)
        if coll_id in visited_coll_ids:
            continue
        visited_coll_ids.add(coll_id)
        stack.extend(coll.children)
        for obj in coll.objects:
            if is_grouppro_mesh_group(obj):
                nested = get_grouppro_collection(obj)
                if nested is not None:
                    stack.append(nested)

    # Scope: GP tree collections plus any collection holding a realized source.
    scoped: set[bpy.types.Object] = set(sources)
    for coll in bpy.data.collections:
        if id(coll) not in visited_coll_ids:
            continue
        scoped.update(coll.all_objects)
    for src in sources:
        for coll in src.users_collection:
            scoped.update(coll.all_objects)

    for obj in scoped:
        if obj.name in keep_names or is_grouppro_placeholder_object(obj):
            continue
        if obj.type != "MESH":
            continue
        family_orphan = any(
            _is_orphan_multi_instance_copy(obj.name, root) for root in instance_roots
        )
        if obj in sources or family_orphan:
            if _hide_gp_mesh_source(obj):
                hidden += 1
    return hidden


def decompose_single_grouppro_group_to_children_parented_under_empty(
    group_obj: bpy.types.Object,
    *,
    uniquify: bool = True,
) -> Optional[bpy.types.Object]:
    """
    Expand a Group Pro 3.x mesh group into mesh duplicates placed from depsgraph
    instance world matrices (viewport WYSIWYG).
    """
    coll = get_grouppro_collection(group_obj)
    if coll is None:
        print(f"Object '{group_obj.name}' is not a Group Pro mesh group")
        return None

    if uniquify:
        make_grouppro_groups_unique_manual([group_obj])
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    empty_matrix = group_obj.matrix_world.copy()
    pending: list[tuple[str, bpy.types.Mesh, Matrix, bpy.types.Object]] = []

    for inst in depsgraph.object_instances:
        if inst.parent is None or inst.parent.original != group_obj:
            continue
        eval_obj = inst.object
        original = eval_obj.original
        if eval_obj.type != "MESH" or original is None or original.data is None:
            continue
        if is_grouppro_mesh_group(original):
            continue
        if is_grouppro_placeholder_object(original):
            continue
        try:
            eval_mesh = eval_obj.to_mesh()
            if eval_mesh is None or not eval_mesh.vertices:
                continue
            if len(eval_mesh.vertices) != len(original.data.vertices):
                continue
            mesh = bpy.data.meshes.new_from_object(eval_obj)
            pending.append((
                original.name,
                mesh,
                inst.matrix_world.copy(),
                original,
            ))
        except RuntimeError:
            continue
        finally:
            eval_obj.to_mesh_clear()

    empty = bpy.data.objects.new(group_obj.name + "_decomposed", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.matrix_world = empty_matrix

    result_names: set[str] = set()
    realized_sources: set[bpy.types.Object] = set()
    for name, mesh, instance_matrix, original in pending:
        relative = empty.matrix_world.inverted() @ instance_matrix
        smart_transform_mesh_data(mesh, relative)
        dupe = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(dupe)
        dupe.parent = empty
        dupe.matrix_basis = Matrix.Identity(4)
        result_names.add(dupe.name)
        realized_sources.add(original)

    _suppress_gp_source_meshes(
        group_obj,
        keep_names=result_names,
        realized_sources=realized_sources,
    )
    return empty


def decompose_grouppro_group_recursively(
    group_obj: bpy.types.Object,
    parent: Optional[bpy.types.Object] = None,
    *,
    uniquify: bool = True,
) -> bpy.types.Object:
    """
    Recursively decompose Group Pro mesh groups and legacy collection instances into
    a hierarchy of empties and meshes, applying modifiers on leaf meshes as we go.
    """
    if is_grouppro_mesh_group(group_obj):
        new_empty = decompose_single_grouppro_group_to_children_parented_under_empty(
            group_obj,
            uniquify=uniquify,
        )
        if new_empty is None:
            return group_obj
        if parent:
            world = new_empty.matrix_world.copy()
            new_empty.parent = parent
            new_empty.matrix_world = world
    elif group_obj.instance_collection:
        new_empty = object_helpers.decompose_single_instance_collection_to_children_parented_under_empty(
            group_obj
        )
        if parent:
            world = new_empty.matrix_world.copy()
            new_empty.parent = parent
            new_empty.matrix_world = world
    else:
        return group_obj

    for child in list(new_empty.children):
        if is_grouppro_mesh_group(child) or child.instance_collection:
            decompose_grouppro_group_recursively(child, new_empty, uniquify=False)
            bpy.data.objects.remove(child, do_unlink=True)

    if new_empty.parent is None:
        bpy.data.objects.remove(group_obj)
        bpy.ops.object.select_all(action="DESELECT")
        new_empty.select_set(True)
        bpy.context.view_layer.objects.active = new_empty

    return new_empty


def _extract_gp_leaf_meshes_via_collection_members(
    group_obj: bpy.types.Object,
) -> List[bpy.types.Object]:
    """Fallback when depsgraph instancing is empty — expand GP collection members directly."""
    from .colinst_extract_helpers import dissolve_subtree

    context = bpy.context
    dissolve_subtree(context, group_obj)
    context.view_layer.update()

    mesh_objects = [
        mesh
        for mesh in object_helpers.collect_all_meshes_in_hierarchy(group_obj)
        if mesh.type == 'MESH' and not is_grouppro_placeholder_object(mesh)
    ]
    for mesh in mesh_objects:
        if not mesh.modifiers:
            continue
        if is_grouppro_mesh_group(mesh):
            continue
        _apply_all_modifiers_on_object(mesh)

    results: list[bpy.types.Object] = []
    for mesh in mesh_objects:
        if mesh.parent is not None:
            object_helpers.cook_parented_mesh_to_world(mesh)
        results.append(mesh)

    if group_obj.name in bpy.data.objects:
        object_helpers.remove_object(group_obj)
    return results


def extract_evaluated_leaf_meshes_from_gp_root(
    group_obj: bpy.types.Object,
) -> List[bpy.types.Object]:
    """Realize evaluated GP leaf meshes with world positions baked (WYSIWYG)."""
    make_grouppro_groups_unique_manual([group_obj])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    results: list[bpy.types.Object] = []
    for inst in depsgraph.object_instances:
        if inst.parent is None or inst.parent.original != group_obj:
            continue
        eval_obj = inst.object
        original = eval_obj.original
        if eval_obj.type != 'MESH' or original is None:
            continue
        try:
            eval_mesh = eval_obj.to_mesh()
            if eval_mesh is None or not eval_mesh.vertices:
                continue
            if original.data is None or len(eval_mesh.vertices) != len(original.data.vertices):
                continue
            mesh = bpy.data.meshes.new_from_object(eval_obj)
        except RuntimeError:
            continue
        finally:
            eval_obj.to_mesh_clear()
        if not mesh.vertices:
            bpy.data.meshes.remove(mesh)
            continue
        smart_transform_mesh_data(mesh, eval_obj.matrix_world.copy())
        leaf = bpy.data.objects.new(original.name, mesh)
        leaf.matrix_world = Matrix.Identity(4)
        bpy.context.scene.collection.objects.link(leaf)
        results.append(leaf)

    if not results:
        return _extract_gp_leaf_meshes_via_collection_members(group_obj)

    if group_obj.name in bpy.data.objects:
        bpy.data.objects.remove(group_obj, do_unlink=True)
    return results


def destructively_dissolve_grouppro_mesh_group_and_retrieve_meshes(
    group_obj: bpy.types.Object,
) -> List[bpy.types.Object]:
    """
    Dissolve a Group Pro 3.x mesh group using leaf-to-root transform cooking instead of
    depsgraph instancing, which is unreliable with nested non-uniform scales.

    Forest-root GP groups use depsgraph leaf extraction for viewport WYSIWYG fidelity.
    """
    if group_obj.parent is None:
        return extract_evaluated_leaf_meshes_from_gp_root(group_obj)
    root_empty = decompose_grouppro_group_recursively(group_obj)
    mesh_objects = object_helpers.collect_all_meshes_in_hierarchy(root_empty)
    for mesh in mesh_objects:
        if not mesh.modifiers:
            continue
        if is_grouppro_mesh_group(mesh):
            continue
        _apply_all_modifiers_on_object(mesh)
    return object_helpers.destructively_retrieve_meshes_from_hierarchy(root_empty)


def _grouppro_collection_reference_count(coll: bpy.types.Collection) -> int:
    count = 0
    for obj in bpy.data.objects:
        if not is_grouppro_mesh_group(obj):
            continue
        if get_grouppro_collection(obj) == coll:
            count += 1
    return count


def _duplicate_gp_collection_member(member: bpy.types.Object) -> Optional[bpy.types.Object]:
    if is_grouppro_mesh_group(member):
        dupe = member.copy()
        src_coll = get_grouppro_collection(member)
        if src_coll is not None:
            new_coll = deep_copy_grouppro_collection(src_coll)
            group_mod = dupe.modifiers.get(GPRO_INSTANCE_MOD)
            if group_mod is not None:
                set_nodes_modifier_input(group_mod, GPRO_COLL_SOCKET, new_coll)
        return dupe
    if member.type == "MESH" and member.data is not None:
        dupe = member.copy()
        dupe.data = member.data.copy()
        return dupe
    if member.type == "EMPTY" and member.instance_collection is not None:
        return member.copy()
    if member.data is not None:
        return member.copy()
    return None


def deep_copy_grouppro_collection(
    coll: bpy.types.Collection,
    *,
    name_suffix: str = "_unique",
) -> bpy.types.Collection:
    """Deep-copy a GP source collection including nested GP groups."""
    new_coll = bpy.data.collections.new(f'{coll.name}{name_suffix}')
    obj_map: Dict[bpy.types.Object, bpy.types.Object] = {}

    for member in coll.objects:
        dupe = _duplicate_gp_collection_member(member)
        if dupe is None:
            continue
        new_coll.objects.link(dupe)
        obj_map[member] = dupe

    for member in coll.objects:
        if member not in obj_map:
            continue
        dupe = obj_map[member]
        if member.parent and member.parent in obj_map:
            dupe.parent = obj_map[member.parent]
        else:
            dupe.parent = None
        dupe.matrix_basis = member.matrix_basis.copy()

    return new_coll


def make_grouppro_group_collection_unique(group_obj: bpy.types.Object) -> bool:
    """Assign a private deep copy of the GP collection on ``group_obj``."""
    coll = get_grouppro_collection(group_obj)
    if coll is None:
        return False
    new_coll = deep_copy_grouppro_collection(coll)
    group_mod = group_obj.modifiers.get(GPRO_INSTANCE_MOD)
    if group_mod is None:
        return False
    set_nodes_modifier_input(group_mod, GPRO_COLL_SOCKET, new_coll)
    return True


def _collect_gp_groups_from_roots(
    roots: List[bpy.types.Object],
) -> list[bpy.types.Object]:
    """All GP mesh groups reachable through GP collection trees under roots."""
    seen: set[str] = set()
    pending = list(roots)
    groups: list[bpy.types.Object] = []
    while pending:
        obj = pending.pop()
        if obj.name in seen:
            continue
        seen.add(obj.name)
        if not is_grouppro_mesh_group(obj):
            continue
        groups.append(obj)
        coll = get_grouppro_collection(obj)
        if coll is None:
            continue
        for member in coll.all_objects:
            if member.name not in seen and is_grouppro_mesh_group(member):
                pending.append(member)
    return groups


def make_grouppro_groups_unique_manual(
    roots: List[bpy.types.Object],
) -> int:
    """Unique shared GP collections under ``roots`` without the Group Pro addon."""
    gp_groups = _collect_gp_groups_from_roots(roots)
    uniquified = 0
    while True:
        candidates = [
            group_obj for group_obj in gp_groups
            if group_obj.name in bpy.data.objects
            and is_grouppro_mesh_group(group_obj)
            and _grouppro_collection_reference_count(
                get_grouppro_collection(group_obj),
            ) > 1
        ]
        if not candidates:
            break
        progressed = False
        for group_obj in candidates:
            if make_grouppro_group_collection_unique(group_obj):
                uniquified += 1
                progressed = True
                gp_groups = _collect_gp_groups_from_roots(roots)
        if not progressed:
            break
    return uniquified

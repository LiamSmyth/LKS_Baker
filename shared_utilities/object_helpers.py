import bpy
from typing import List
from mathutils import Matrix, Vector
import math

from .deep_apply_debug import enabled as _deep_apply_debug_enabled
from .deep_apply_debug import log as _deep_apply_log
from .transform_apply_helpers import smart_bake_matrix_local_into_mesh_data
from .transform_apply_helpers import smart_transform_mesh_data


def context_selected_objects(context: bpy.types.Context) -> list[bpy.types.Object]:
    """Selected objects — works in UI and headless (view_layer fallback)."""
    selected = getattr(context, 'selected_objects', None)
    if selected is not None:
        return list(selected)
    view_layer = context.view_layer
    return [obj for obj in view_layer.objects if obj.select_get()]


def remove_object(obj: bpy.types.Object):
    """
    Fully remove an object and its mesh data from the scene.

    Parameters:
    - obj (bpy.types.Object): The object to remove.
    """

    # Remove the object from the scene
    bpy.context.collection.objects.unlink(obj)

    if obj.type == "EMPTY":
        bpy.data.objects.remove(obj)
        del obj
        return

    # Remove the mesh data from the scene
    if obj.data.users == 0:
        bpy.data.meshes.remove(obj.data)
        del obj.data

    if obj.users == 0:
        bpy.data.objects.remove(obj)
        del obj

    bpy.ops.outliner.orphans_purge(do_recursive=True)


def create_clone_with_applied_xforms(obj: bpy.types.Object) -> bpy.types.Object:
    """
    Creates a clone of the given object with all transformations applied. 
    It also ensures that the clone's mesh data is single-user, even if the original object's mesh was multi-user.

    Parameters:
    - obj (bpy.types.Object): The object to clone.

    Returns:
    - bpy.types.Object: The cloned object with transformations applied.
    """

    # Create a clone of the object
    clone_object = obj.copy()
    # Ensure the clone has its own unique mesh data (single-user)
    clone_object.data = obj.data.copy()

    # Link the clone object to the current collection
    bpy.context.collection.objects.link(clone_object)

    # Make sure we're only operating on the clone
    bpy.ops.object.select_all(action='DESELECT')
    clone_object.select_set(True)
    bpy.context.view_layer.objects.active = clone_object

    # Apply the transformations to the clone
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    return clone_object


def ensure_single_user_mesh_data(obj: bpy.types.Object) -> bool:
    """Copy mesh data when shared; True when a new data block was assigned."""
    if obj.type != 'MESH' or obj.data is None:
        return False
    if obj.data.users <= 1:
        return False
    obj.data = obj.data.copy()
    return True


def uniquify_mesh_data_for_inplace_edit(obj: bpy.types.Object) -> bool:
    """Assign a private mesh copy before in-place geometry edits."""
    if obj.type != 'MESH' or obj.data is None:
        return False
    obj.data = obj.data.copy()
    return True


def _ensure_single_user_mesh_data(obj: bpy.types.Object) -> None:
    ensure_single_user_mesh_data(obj)


def bake_matrix_local_into_mesh_data(obj: bpy.types.Object) -> None:
    """Bake ``matrix_local`` into mesh via 4x4 multiply (avoids Euler/scale shear loss)."""
    if obj.type != 'MESH' or obj.data is None:
        return
    _ensure_single_user_mesh_data(obj)
    smart_bake_matrix_local_into_mesh_data(obj)


def _log_unparent_matrix_state(obj: bpy.types.Object, label: str) -> None:
    if not _deep_apply_debug_enabled():
        return
    parent_name = obj.parent.name if obj.parent else None
    _deep_apply_log(
        f'unparent {label}: {obj.name!r} parent={parent_name!r} '
        f'matrix_world={[[round(obj.matrix_world[r][c], 4) for c in range(4)] for r in range(4)]}',
        stage='unparent',
    )


def decompose_single_instance_collection_to_children_parented_under_empty(
    obj: bpy.types.Object,
) -> bpy.types.Object | None:
    """
    Expand a collection instance into real objects parented under a new empty at the
    instance world transform. Preserves in-collection parenting via matrix_basis.
    """
    if not obj.instance_collection:
        print("Object is not a collection instance")
        return None

    coll = obj.instance_collection
    empty = bpy.data.objects.new(obj.name + "_decomposed", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.matrix_world = obj.matrix_world.copy()

    members = list(coll.objects)
    obj_map: dict[bpy.types.Object, bpy.types.Object] = {}
    for member in members:
        if member.type == "MESH" and member.data is not None:
            duplicate = member.copy()
            duplicate.data = member.data.copy()
        elif member.instance_collection is not None:
            duplicate = member.copy()
        elif member.data is not None:
            duplicate = member.copy()
        else:
            print(f"Skipping instance member '{member.name}' — no mesh or nested instance")
            continue

        bpy.context.scene.collection.objects.link(duplicate)
        obj_map[member] = duplicate

    member_set = set(members)
    for member in members:
        if member not in obj_map:
            continue
        duplicate = obj_map[member]
        if member.parent and member.parent in obj_map:
            duplicate.parent = obj_map[member.parent]
        else:
            duplicate.parent = empty
        duplicate.matrix_basis = member.matrix_basis.copy()

    return empty


def decompose_instance_collection_recursively(obj: bpy.types.Object, parent: bpy.types.Object = None) -> bpy.types.Object:
    """
    In this recursive function we pass in a base object for the function to decompose. If the object is a collection
    instance, we decompose it into its children and parent them under a new empty. We then pass each child into 
    this function, and the function will decompose the child if it is a collection instance. This function will
    continue to recurse until it reaches a child that is not a collection instance, at which point it will return.


    """
    # If obj has an instance collection,
    if obj.instance_collection:
        new_empty = decompose_single_instance_collection_to_children_parented_under_empty(
            obj,
        )
        if new_empty is None:
            return obj
        if parent:
            new_empty.parent = parent
    else:
        return obj

    for child in new_empty.children:
        # If the child is an instance collection, decompose the child and remove the original collection instance
        if child.instance_collection:
            decompose_instance_collection_recursively(child, new_empty)
            bpy.data.objects.remove(child)

        # If it is not an instance collection, it is a mesh or some other object. Apply all modifiers
        else:
            if child.modifiers:
                for mod in child.modifiers:
                    print("Found modifier: " + mod.name +
                          " on object :" + child.name + ", applying...")
                    bpy.ops.object.modifier_apply(modifier=mod.name)

    # Remove the original collection instance if the empty is at the root of the hierarchy
    if new_empty.parent == None:
        bpy.data.objects.remove(obj)
        bpy.ops.object.select_all(action='DESELECT')
        new_empty.select_set(True)
        bpy.context.view_layer.objects.active = new_empty
    return new_empty


def collect_all_meshes_in_hierarchy(root_obj: bpy.types.Object) -> List[bpy.types.Object]:
    """
        This method collects all meshes in the hierarchy of the given root object, including the root object itself.

        Args:
        root_obj (bpy.types.Object): The root object to collect meshes from

        Returns:
        List[bpy.types.Object]: A list of all meshes in the hierarchy of the root object
    """
    meshes = []
    if root_obj.type == 'MESH':
        meshes.append(root_obj)

    for child in root_obj.children:
        meshes.extend(collect_all_meshes_in_hierarchy(child))

    return meshes


def apply_transform_on_mesh_and_step_up_hierarchy(obj: bpy.types.Object):
    """
        This method makes an object unique, applies the transform on the given object 
        and steps up the hierarchy of the object until it reaches the root object.
        This uses object ops, which means your selection will change.

        Args:
        obj (bpy.types.Object): The object to apply the transform on and step up the hierarchy of
    """
    if obj.type != 'MESH':
        print("Object is not a mesh")
        return

    # Make mesh data unique when shared (object user count is unrelated).
    _ensure_single_user_mesh_data(obj)

    # Deselct everything and select the object
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)

    # Set the mesh as the active object, so context is correct for applying modifiers.
    # Apply any modifiers on the object, but ensure the context is set to the object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')

    orig_parent = obj.parent
    _log_unparent_matrix_state(obj, 'before_bake')

    bake_matrix_local_into_mesh_data(obj)
    _log_unparent_matrix_state(obj, 'after_bake')

    if not orig_parent:
        return

    parent_world = orig_parent.matrix_world.copy()
    grandparent = orig_parent.parent
    if grandparent is not None:
        step_matrix = grandparent.matrix_world.inverted() @ parent_world
    else:
        step_matrix = parent_world
    smart_transform_mesh_data(obj.data, step_matrix)

    obj.parent = grandparent
    if grandparent is not None:
        obj.matrix_world = grandparent.matrix_world.copy()
    else:
        obj.matrix_world = Matrix.Identity(4)
    _log_unparent_matrix_state(obj, 'after_step_up')


def cook_parented_mesh_to_world(obj: bpy.types.Object) -> None:
    """Bake parent transforms into mesh data until ``obj`` has no parent."""
    if obj.type != 'MESH':
        return
    while obj.name in bpy.data.objects and obj.parent is not None:
        apply_transform_on_mesh_and_step_up_hierarchy(obj)
    if obj.name not in bpy.data.objects or obj.type != 'MESH':
        return
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bake_matrix_local_into_mesh_data(obj)


def destructively_retrieve_meshes_from_hierarchy(root_obj: bpy.types.Object) -> List[bpy.types.Object]:
    """
    This method will take a hierarchy of meshes and empties (only) and unparent each mesh in the hierarchy,
    cooking the transforms into the mesh data. when each mesh has no more parents, the original hierarchy
    will be removed. The primary use case for this method is for circumstances in which "make instances real"
    causes meshes to move and rotate due to badly composed transforms.

    Args:
        root_obj (bpy.types.Object): The root object of the hierarchy to destructively dissolve

    Returns:
        List[bpy.types.Object]: A list of the meshes that were retrieved from the hierarchy

    """
    mesh_objects = collect_all_meshes_in_hierarchy(root_obj)

    def _hierarchy_depth(obj: bpy.types.Object) -> int:
        depth = 0
        parent = obj.parent
        while parent is not None:
            depth += 1
            parent = parent.parent
        return depth

    # Deepest meshes first: apply modifiers + transforms on leaves before parents
    # so parent transform_apply does not move still-parented descendants.
    mesh_objects.sort(key=_hierarchy_depth, reverse=True)

    for mesh in mesh_objects:
        while mesh.parent:
            apply_transform_on_mesh_and_step_up_hierarchy(mesh)

    # Bake any remaining object transform (parent chain tail) into mesh data.
    for mesh in mesh_objects:
        if mesh.name not in bpy.data.objects or mesh.type != 'MESH':
            continue
        bpy.ops.object.select_all(action='DESELECT')
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        bake_matrix_local_into_mesh_data(mesh)

    # Remove original root object and its children
    # select the root object and its children
    root_obj.select_set(True)
    bpy.ops.object.select_grouped(type='CHILDREN_RECURSIVE')
    bpy.ops.object.delete()

    for mesh in mesh_objects:
        mesh.select_set(True)

    bpy.context.view_layer.objects.active = mesh_objects[0]

    # unlink root object
    bpy.data.objects.remove(root_obj)

    return mesh_objects


def destructively_dissolve_instance_collection_and_retrieve_meshes(root_collection_instance: bpy.types.Object) -> List[bpy.types.Object]:
    """
    This method will retrieve all meshes from a hierarchy of collection instances and return them in a list, 
    after dissolving the hierarchy. This method is destructive and will remove the original hierarchy, as well
    as cooking the transforms into the mesh data.
    """
    root_empty = decompose_instance_collection_recursively(
        root_collection_instance)

    mesh_objects = destructively_retrieve_meshes_from_hierarchy(root_empty)

    return mesh_objects


def make_collection_instance_hierarchy_unique_recursively(instance_collection_object: bpy.types.Object, in_collection: bpy.types.Collection, recursion_depth=0):
    """
    This method will take a collection instance and make it unique, as well as all of its children. This method
    is recursive and will recurse through the entire hierarchy of the collection instance.

    Args:
        instance (bpy.types.Object): The collection instance to make unique
    """
    object: bpy.types.Object = instance_collection_object
    debug = True
    recursion_string = "~" * recursion_depth + " "

    if debug:
        print("\n\n" + recursion_string +
              "Attempting to make object unique: " + object.name)

    if not object.instance_collection and not object.data:
        if debug:
            print(recursion_string +
                  "Object has no data or instance collection, skipping...")
        return

    # Object is a mesh
    if not object.instance_collection:
        if debug:
            print(recursion_string +
                  "Object was not a collection instance, making object data unique...")
        dupe: bpy.types.Object = (object)

        in_collection.objects.link(dupe)
        in_collection.collection.objects.unlink(object)

        if object.data:
            return

    if debug:
        print(recursion_string + "Object was an instance collection...")
    # Here we know it's an instance collection object
    dupe = object.copy()
    dupe.instance_collection = object.instance_collection.copy()

    in_collection.objects.link(dupe)
    in_collection.objects.unlink(object)

    collection: bpy.types.Collection = dupe.instance_collection
    collection_objs = collection.objects[:]
    if debug:
        print(recursion_string + "collection found: " + collection.name)
    for child in collection_objs:
        if debug:
            print(recursion_string + "Found child object: " + child.name)
        dupe_child = child.copy()

        collection.objects.link(dupe_child)
        collection.objects.unlink(child)

        if child.data:
            if debug:
                print(recursion_string +
                      "Child object has data, making data unique... ")
            dupe_child.data = child.data.copy()

        if dupe_child.instance_collection:
            if debug:
                print(recursion_string +
                      "Child object is an instance collection, recursing... ")
            dupe_child.instance_collection = child.instance_collection.copy()
            make_collection_instance_hierarchy_unique_recursively(
                dupe_child, collection, recursion_depth + 1)


def is_object_alive(obj: bpy.types.Object | None) -> bool:
    """True when *obj* still exists in ``bpy.data.objects``."""
    if obj is None:
        return False
    try:
        name = obj.name
    except ReferenceError:
        return False
    return name in bpy.data.objects and bpy.data.objects.get(name) is not None


def filter_valid_objects(objects: List[bpy.types.Object]) -> List[bpy.types.Object]:
    """
    Returns live ``bpy.data.objects`` entries for objects still in the file.

    :param object_list: List of Blender objects.
    :return: List of valid Blender objects.
    """
    live: List[bpy.types.Object] = []
    for obj in objects:
        if not is_object_alive(obj):
            continue
        resolved = bpy.data.objects.get(obj.name)
        if resolved is not None:
            live.append(resolved)
    return live


def filter_mesh_objects(objects: List[bpy.types.Object]) -> List[bpy.types.Object]:
    """
    Returns a list of mesh objects from the given object_list.

    :param object_list: List of Blender objects.
    :return: List of mesh Blender objects.
    """
    mesh_objects: List[bpy.types.Object] = []
    for obj in objects:
        if obj.type == 'MESH':
            mesh_objects.append(obj)
    return mesh_objects


def collect_hierarchy_forest_roots(
    objects: List[bpy.types.Object],
) -> List[bpy.types.Object]:
    """Top-level roots within an object set (parent absent or outside the set)."""
    live = filter_valid_objects(objects)
    names = {obj.name for obj in live}
    roots: List[bpy.types.Object] = []
    for obj in live:
        parent = obj.parent
        if parent is None or not is_object_alive(parent) or parent.name not in names:
            roots.append(obj)
    return roots


def collect_objects_in_subtrees(
    roots: List[bpy.types.Object],
) -> List[bpy.types.Object]:
    """Each root plus all ``Object.children`` descendants, deduplicated."""
    seen: set[str] = set()
    subtree: List[bpy.types.Object] = []
    stack = list(filter_valid_objects(roots))
    while stack:
        obj = stack.pop()
        if not is_object_alive(obj):
            continue
        if obj.name in seen:
            continue
        seen.add(obj.name)
        subtree.append(obj)
        stack.extend(obj.children)
    return subtree


def expand_objects_with_parent_chain(
    objects: List[bpy.types.Object],
) -> List[bpy.types.Object]:
    """Include ancestors so duplicated subsets keep intact transform chains."""
    seen: set[str] = set()
    expanded: List[bpy.types.Object] = []

    def add(obj: bpy.types.Object) -> None:
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        expanded.append(obj)

    for obj in objects:
        chain: List[bpy.types.Object] = []
        current: bpy.types.Object | None = obj
        while current is not None:
            chain.append(current)
            current = current.parent
        for ancestor in reversed(chain):
            add(ancestor)

    return expanded


def duplicate_via_depsgraph(
    obj: bpy.types.Object,
    *,
    context: bpy.types.Context | None = None,
) -> bpy.types.Object:
    """Duplicate object with modifiers applied via the dependency graph."""
    ctx = context or bpy.context
    depsgraph = ctx.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)

    new_mesh = bpy.data.meshes.new_from_object(eval_obj)
    new_obj = bpy.data.objects.new(obj.name, new_mesh)
    new_obj.matrix_world = obj.matrix_world.copy()

    return new_obj

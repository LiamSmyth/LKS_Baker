"""Subtree-scoped uniquify and modifier-apply phases for deep geometry ops."""



from __future__ import annotations



from dataclasses import dataclass



import bpy

from mathutils import Vector



from . import mesh_helpers, object_helpers

from .collection_instance_helpers import (
    bake_colinst_objects_in_subtrees,
    bake_colinst_to_hierarchy,
    find_colinst_roots_in_selection,
    is_colinst_object,
    is_collection_instance,
)
from .grouppro_helpers import is_grouppro_mesh_group

from .geonodes_instance_helpers import (

    dissolve_geonodes_collection_instances_in_objects,

)

from .deep_apply_debug import log_pass as _deep_pass_log

from .grouppro_helpers import is_grouppro_placeholder_object

from .hierarchy_flatten_helpers import flatten_hierarchy_to_world_meshes

from .lks_constants import (
    GPRO_INSTANCE_MOD,
    TRIANGULATE_NGON_METHOD_DEFAULT,
    TRIANGULATE_QUAD_METHOD_DEFAULT,
)





@dataclass(frozen=True)

class DeepPhaseResult:

    """Counts from a single deep-geometry phase pass."""



    mesh_count: int = 0

    uniquified_count: int = 0

    modifiers_applied_count: int = 0

    modifiers_deleted_count: int = 0

    triangulated_count: int = 0

    triangulate_skipped_count: int = 0

    baked_collection_instances: int = 0

    baked_geonodes_collection_instances: int = 0

    removed_non_geometry: int = 0

    uv_unstacked_mesh_count: int = 0

    mirror_modifiers_offset_count: int = 0

    baked_root_empties: tuple[bpy.types.Object, ...] = ()





_NON_GEOMETRY_TYPES = frozenset({'EMPTY', 'CAMERA', 'LIGHT', 'LIGHT_PROBE', 'SPEAKER'})





def get_selection_subtree_roots(

    context: bpy.types.Context,

) -> list[bpy.types.Object]:

    """Forest roots from the current selection."""

    selected = object_helpers.context_selected_objects(context)

    if not selected:

        return []

    return object_helpers.collect_hierarchy_forest_roots(selected)





def collect_subtree_meshes(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

) -> list[bpy.types.Object]:

    """Mesh objects under roots (selection subtree), deduplicated."""

    _ = context

    seen: set[str] = set()

    meshes: list[bpy.types.Object] = []

    for obj in object_helpers.collect_objects_in_subtrees(roots):

        if obj.type != 'MESH' or obj.data is None:

            continue

        if is_grouppro_placeholder_object(obj):

            continue

        if obj.name in seen:

            continue

        seen.add(obj.name)

        meshes.append(obj)

    return meshes





def selection_has_subtree_meshes(context: bpy.types.Context) -> bool:

    """True when selection includes at least one mesh in its subtree."""

    roots = get_selection_subtree_roots(context)

    if not roots:

        return False

    return bool(collect_subtree_meshes(context, roots))





def selection_has_subtree_meshes_with_mirror(context: bpy.types.Context) -> bool:

    """True when selection subtree includes a mesh with a Mirror modifier."""

    roots = get_selection_subtree_roots(context)

    if not roots:

        return False

    from .mesh_uv_helpers import collect_subtree_meshes_with_mirror

    return bool(collect_subtree_meshes_with_mirror(context, roots))





def move_objects_to_scene_collection(

    objects: list[bpy.types.Object],

    scene: bpy.types.Scene,

) -> None:

    """Link objects only to the scene root collection."""

    target = scene.collection

    for obj in object_helpers.filter_valid_objects(objects):

        for coll in list(obj.users_collection):

            coll.objects.unlink(obj)

        if obj.name not in target.objects:

            target.objects.link(obj)





def _mesh_hierarchy_depth(obj: bpy.types.Object) -> int:

    depth = 0

    parent = obj.parent

    while parent is not None:

        depth += 1

        parent = parent.parent

    return depth





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

    return max(

        (after_vertex - before_vertex).length

        for after_vertex, before_vertex in zip(after, before)

    )





def log_phase_vertex_deltas(

    phase: str,

    before_verts: dict[str, list[Vector]],

    meshes: list[bpy.types.Object],

) -> None:

    """Log per-object max vertex delta after a phase when debug is enabled."""

    if not before_verts:

        _deep_pass_log(phase, f'{len(meshes)} mesh(es), no before snapshot')

        return

    deltas: list[str] = []

    for mesh in meshes:

        before = before_verts.get(mesh.name)

        if before is None:

            continue

        delta = _max_vertex_delta(before, _mesh_world_vertices(mesh))

        if delta is not None:

            deltas.append(f'{mesh.name}={delta:.2e}')

    _deep_pass_log(

        phase,

        f'{len(meshes)} mesh(es) parentless={sum(1 for m in meshes if m.parent is None)} '

        f'deltas=[{", ".join(deltas) or "n/a"}]',

        objects=meshes,

    )





def bake_collection_instances_for_roots(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

) -> DeepPhaseResult:

    """Dissolve every collection / GP instance under ``roots`` in place."""

    bake_result = bake_colinst_objects_in_subtrees(context, roots)

    return DeepPhaseResult(
        baked_collection_instances=bake_result.baked_count,
        baked_root_empties=tuple(bake_result.root_empties),
    )





def bake_geonodes_collection_instances_for_roots(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

) -> DeepPhaseResult:

    """Expand geo-nodes collection instance modifiers under ``roots``."""

    subtree = object_helpers.collect_objects_in_subtrees(roots)

    baked = dissolve_geonodes_collection_instances_in_objects(context, list(subtree))

    context.view_layer.update()

    return DeepPhaseResult(baked_geonodes_collection_instances=baked)





def deep_uv_unstack(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

) -> DeepPhaseResult:

    """Set whole-number Mirror ``offset_u`` on every subtree mesh with mirror modifiers."""

    from .mesh_uv_helpers import (

        apply_mirror_uv_unstack_offset,

        collect_subtree_meshes_with_mirror,

    )

    meshes = collect_subtree_meshes_with_mirror(context, roots)

    mesh_count = 0

    mod_count = 0

    for obj in meshes:

        updated = apply_mirror_uv_unstack_offset(obj)

        if updated:

            mesh_count += 1

            mod_count += updated

    _deep_pass_log(

        'uv_unstack',

        f'meshes={len(meshes)} unstacked={mesh_count} mirror_mods={mod_count}',

    )

    return DeepPhaseResult(

        mesh_count=len(meshes),

        uv_unstacked_mesh_count=mesh_count,

        mirror_modifiers_offset_count=mod_count,

    )





def deep_uniquify_geometry(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

) -> DeepPhaseResult:

    """De-instance mesh data for every mesh under roots."""

    meshes = collect_subtree_meshes(context, roots)

    uniquified = 0

    for obj in meshes:

        if object_helpers.ensure_single_user_mesh_data(obj):

            uniquified += 1

    return DeepPhaseResult(mesh_count=len(meshes), uniquified_count=uniquified)





def deep_apply_modifiers(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

    *,

    defer_triangulate: bool = False,

) -> DeepPhaseResult:

    """Apply visible modifiers on subtree meshes; delete viewport-hidden ones."""

    meshes = collect_subtree_meshes(context, roots)

    meshes.sort(key=_mesh_hierarchy_depth, reverse=True)

    applied = 0

    deleted = 0

    for obj in meshes:

        if not obj.modifiers:

            continue

        if defer_triangulate:

            deleted += mesh_helpers.remove_modifiers_of_types(obj, {'TRIANGULATE'})

        obj_applied = 0

        obj_deleted = 0

        for mod in list(obj.modifiers):

            if mod.name == GPRO_INSTANCE_MOD:

                continue

            if not mod.show_viewport:

                obj.modifiers.remove(mod)

                obj_deleted += 1

                continue

            try:

                with context.temp_override(

                    object=obj,

                    active_object=obj,

                    selected_objects=[obj],

                    view_layer=context.view_layer,

                ):

                    bpy.ops.object.modifier_apply(modifier=mod.name)

                obj_applied += 1

            except RuntimeError as exc:

                print(

                    f"Could not apply modifier '{mod.name}' on '{obj.name}': {exc}",

                )

        applied += obj_applied

        deleted += obj_deleted

    return DeepPhaseResult(

        mesh_count=len(meshes),

        modifiers_applied_count=applied,

        modifiers_deleted_count=deleted,

    )





def _mesh_has_non_triangle_faces(mesh: bpy.types.Mesh) -> bool:

    for poly in mesh.polygons:

        if len(poly.vertices) > 3:

            return True

    return False





def deep_triangulate_meshes(

    context: bpy.types.Context,

    meshes: list[bpy.types.Object],

    *,

    quad_method: str = TRIANGULATE_QUAD_METHOD_DEFAULT,

    ngon_method: str = TRIANGULATE_NGON_METHOD_DEFAULT,

    keep_custom_normals: bool = True,

) -> DeepPhaseResult:

    """Add and apply a triangulate modifier on meshes that still have quads/ngons."""

    triangulated = 0

    skipped = 0

    for obj in meshes:

        if obj.type != 'MESH' or obj.data is None:

            continue

        if not _mesh_has_non_triangle_faces(obj.data):

            skipped += 1

            continue

        if mesh_helpers.apply_triangulate_modifier(
            context,
            obj,
            keep_custom_normals=keep_custom_normals,
            quad_method=quad_method,
            ngon_method=ngon_method,
        ):

            triangulated += 1

    _deep_pass_log(

        'triangulate',

        f'mesh_count={len(meshes)} triangulated={triangulated} skipped={skipped}',

    )

    return DeepPhaseResult(

        mesh_count=len(meshes),

        triangulated_count=triangulated,

        triangulate_skipped_count=skipped,

    )





def deep_triangulate_geometry(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

    *,

    quad_method: str = TRIANGULATE_QUAD_METHOD_DEFAULT,

    ngon_method: str = TRIANGULATE_NGON_METHOD_DEFAULT,

    keep_custom_normals: bool = True,

) -> DeepPhaseResult:

    """Triangulate every mesh under roots with preserved custom normals."""

    meshes = collect_subtree_meshes(context, roots)

    return deep_triangulate_meshes(
        context,
        meshes,
        quad_method=quad_method,
        ngon_method=ngon_method,
        keep_custom_normals=keep_custom_normals,
    )





def deep_flatten_hierarchy(

    context: bpy.types.Context,

    scene: bpy.types.Scene,

    roots: list[bpy.types.Object],

    *,

    object_filter: set[str] | None = None,

) -> list[bpy.types.Object]:

    """Deparent meshes, dissolve instances, and bake transforms (no modifier apply)."""

    _ = roots

    return flatten_hierarchy_to_world_meshes(

        context,

        scene,

        object_filter=object_filter,

        apply_modifiers=False,

    )





def cleanup_non_geometry_for_roots(

    context: bpy.types.Context,

    roots: list[bpy.types.Object],

) -> DeepPhaseResult:

    """Remove empties, cameras, and lights under roots (meshes preserved)."""

    _ = context

    removed = 0

    live_roots = object_helpers.filter_valid_objects(roots)

    for obj in object_helpers.collect_objects_in_subtrees(live_roots):

        if obj.type not in _NON_GEOMETRY_TYPES:

            continue

        if is_collection_instance(obj):

            continue

        object_helpers.remove_object(obj)

        removed += 1

    return DeepPhaseResult(removed_non_geometry=removed)


"""Extract mesh data from Blender (FBX/OBJ import, no custom parser)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from .mesh_data import MeshData
from .runtime_log import log, timed_step


@dataclass
class MeshPair:
    """Low/high ``MeshData`` pair for atlas bakes.

    Attributes:
        low: ``MeshData`` value.
        high: ``MeshData`` value.
        low_name: ``str`` value.
        high_name: ``str`` value.
    """
    low: MeshData
    high: MeshData
    low_name: str
    high_name: str


def _active_view_layer(scene) -> object:
    view_layers = scene.view_layers
    if not view_layers:
        raise RuntimeError("scene has no view layers")
    try:
        index = int(view_layers.active_index)
        if index < 0 or index >= len(view_layers):
            index = 0
        return view_layers[index]
    except AttributeError:
        active = getattr(view_layers, "active", None)
        if active is not None:
            return active
        return view_layers[0]


def _import_context_override() -> dict | None:
    import bpy

    from .blender_session import _primary_scene

    scene = _primary_scene()
    view_layer = _active_view_layer(scene)
    wm = bpy.context.window_manager
    if wm is None:
        if view_layer is None:
            return None
        return {
            "scene": scene,
            "view_layer": view_layer,
        }
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((item for item in area.regions if item.type == "WINDOW"), None)
            if region is None:
                continue
            return {
                "window": window,
                "screen": screen,
                "area": area,
                "region": region,
                "scene": scene,
                "view_layer": view_layer or bpy.context.view_layer,
            }
    if view_layer is None:
        return None
    return {
        "scene": scene,
        "view_layer": view_layer,
    }


def load_mesh_from_obj_path(mesh_path: str | Path) -> MeshData:
    """Load triangulated OBJ exported by the bake engine test fixtures."""
    mesh_path = Path(mesh_path)
    if not mesh_path.exists():
        raise FileNotFoundError(mesh_path)

    vertices: list[list[float]] = []
    uvs: list[list[float]] = []
    normals: list[list[float]] = []
    faces: list[list[int]] = []
    face_uvs: list[list[float]] = []

    with timed_step(f"parse OBJ {mesh_path.name}"):
        for raw_line in mesh_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            tag, *parts = line.split()
            if tag == "v" and len(parts) >= 3:
                vertices.append([float(parts[0]), float(parts[1]), float(parts[2])])
            elif tag == "vt" and len(parts) >= 2:
                uvs.append([float(parts[0]), float(parts[1])])
            elif tag == "vn" and len(parts) >= 3:
                normals.append([float(parts[0]), float(parts[1]), float(parts[2])])
            elif tag == "f" and len(parts) >= 3:
                corner_indices: list[int] = []
                corner_uvs: list[list[float]] = []
                for corner in parts[:3]:
                    tokens = corner.split("/")
                    vert_index = int(tokens[0]) - 1
                    uv_index = int(tokens[1]) - 1 if len(tokens) > 1 and tokens[1] else vert_index
                    corner_indices.append(vert_index)
                    corner_uvs.append(uvs[uv_index])
                faces.append(corner_indices)
                face_uvs.append(corner_uvs)

    if not vertices or not faces:
        raise RuntimeError(f"no mesh geometry in {mesh_path}")

    return MeshData(
        vertices=np.asarray(vertices, dtype=np.float64),
        faces=np.asarray(faces, dtype=np.int32),
        normals=np.asarray(normals, dtype=np.float64),
        face_uvs=np.asarray(face_uvs, dtype=np.float64),
    )


def _import_mesh_file(mesh_path: Path) -> object:
    import bpy

    log(f"import mesh file: {mesh_path.name}")
    suffix = mesh_path.suffix.lower()
    if suffix == ".fbx":
        override = _import_context_override()
        with timed_step(f"bpy.ops.import_scene.fbx({mesh_path.name})"):
            if override is not None:
                with bpy.context.temp_override(**override):
                    bpy.ops.import_scene.fbx(filepath=str(mesh_path))
            else:
                bpy.ops.import_scene.fbx(filepath=str(mesh_path))
    elif suffix == ".obj":
        override = _import_context_override()
        with timed_step(f"bpy.ops.wm.obj_import({mesh_path.name})"):
            if override is not None:
                with bpy.context.temp_override(**override):
                    bpy.ops.wm.obj_import(filepath=str(mesh_path))
            else:
                bpy.ops.wm.obj_import(filepath=str(mesh_path))
    else:
        raise ValueError(f"unsupported mesh format: {suffix}")

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"no mesh objects imported from {mesh_path}")
    obj = max(meshes, key=lambda item: len(item.data.vertices))
    log(f"selected mesh object {obj.name!r}: {len(obj.data.vertices)} verts")
    return obj


def _transform_vertices(vertices: np.ndarray, matrix) -> np.ndarray:
    count = len(vertices)
    ones = np.ones((count, 1), dtype=np.float64)
    mat = np.array(matrix, dtype=np.float64)
    return (np.hstack([vertices, ones]) @ mat.T)[:, :3]


def _transform_normals(normals: np.ndarray, matrix) -> np.ndarray:
    mat3 = np.array(matrix.to_3x3(), dtype=np.float64)
    transformed = normals @ mat3.T
    lengths = np.linalg.norm(transformed, axis=1, keepdims=True)
    lengths = np.maximum(lengths, 1e-8)
    return transformed / lengths


def meshdata_from_object(
    obj,
    *,
    label: str = "",
    space: Literal["object", "world"] = "world",
) -> MeshData:
    """Triangulated UV corners with vertices/normals in object or world space."""
    tag = f" ({label})" if label else ""
    mesh = obj.data
    uv_layer = _active_uv_layer(mesh)

    with timed_step(f"calc_loop_triangles{tag}"):
        mesh.calc_loop_triangles()

    matrix = obj.matrix_world
    vert_count = len(mesh.vertices)
    tri_count = len(mesh.loop_triangles)
    log(f"extract{tag}: {vert_count} verts, {tri_count} tris, space={space}")

    with timed_step(f"foreach_get vertices/normals{tag}"):
        coords = np.empty(vert_count * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", coords)
        local_vertices = coords.reshape(-1, 3)
        if space == "world":
            vertices = _transform_vertices(local_vertices, matrix)
        else:
            vertices = local_vertices

        normal_flat = np.empty(vert_count * 3, dtype=np.float64)
        mesh.vertices.foreach_get("normal", normal_flat)
        local_normals = normal_flat.reshape(-1, 3)
        if space == "world":
            normals = _transform_normals(local_normals, matrix)
        else:
            lengths = np.linalg.norm(local_normals, axis=1, keepdims=True)
            normals = local_normals / np.maximum(lengths, 1e-8)

    with timed_step(f"foreach_get faces/uvs{tag}"):
        faces_flat = np.empty(tri_count * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", faces_flat)
        faces = faces_flat.reshape(tri_count, 3)

        loop_indices = np.empty(tri_count * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("loops", loop_indices)
        loop_indices = loop_indices.reshape(tri_count, 3)

        uv_flat = np.empty(len(mesh.loops) * 2, dtype=np.float64)
        uv_layer.data.foreach_get("uv", uv_flat)
        uv_by_loop = uv_flat.reshape(-1, 2)
        face_uvs = uv_by_loop[loop_indices]

    return MeshData(
        vertices=vertices,
        faces=faces,
        normals=normals,
        face_uvs=face_uvs,
    )


def _active_uv_layer(mesh) -> object:
    """Return the active UV layer across Blender RNA variants."""
    if not mesh.uv_layers:
        raise ValueError("mesh has no UV map")
    uv_layers = mesh.uv_layers
    try:
        index = int(uv_layers.active_index)
        if index < 0 or index >= len(uv_layers):
            index = 0
            uv_layers.active_index = 0
        return uv_layers[index]
    except AttributeError:
        active = getattr(uv_layers, "active", None)
        if active is not None:
            return active
        return uv_layers[0]


def _active_uv_layer_name(mesh) -> str:
    return _active_uv_layer(mesh).name


def load_mesh_from_blender(mesh_path: str | Path) -> MeshData:
    """Load mesh from blender.

    Args:
        mesh_path: ``str | Path`` value.

    Returns:
        ``MeshData`` result.
    """
    mesh_path = Path(mesh_path)
    if not mesh_path.exists():
        raise FileNotFoundError(mesh_path)
    if mesh_path.suffix.lower() == ".obj":
        return load_mesh_from_obj_path(mesh_path)

    import bpy

    from .blender_session import bootstrap_bake_engine_blender_session, clear_bake_test_scene

    bootstrap_bake_engine_blender_session()
    clear_bake_test_scene()
    obj = _import_mesh_file(mesh_path)
    return meshdata_from_object(obj, label=mesh_path.name)


def load_mesh_pair_from_blender(low_path: str | Path, high_path: str | Path) -> MeshPair:
    """Import low + high into one scene so world transforms stay aligned."""
    low_path = Path(low_path)
    high_path = Path(high_path)
    if not low_path.exists():
        raise FileNotFoundError(low_path)
    if not high_path.exists():
        raise FileNotFoundError(high_path)

    if low_path.suffix.lower() == ".obj" and high_path.suffix.lower() == ".obj":
        with timed_step(f"parse OBJ pair ({low_path.name}, {high_path.name})"):
            low_data = load_mesh_from_obj_path(low_path)
            high_data = load_mesh_from_obj_path(high_path)
        return MeshPair(
            low=low_data,
            high=high_data,
            low_name=low_path.stem,
            high_name=high_path.stem,
        )

    import bpy

    from .blender_session import bootstrap_bake_engine_blender_session, clear_bake_test_scene

    bootstrap_bake_engine_blender_session()
    clear_bake_test_scene()

    low_obj = _import_mesh_file(low_path)
    with timed_step(f"meshdata_from_object low ({low_path.name})"):
        low_data = meshdata_from_object(low_obj, label=f"low/{low_path.name}")

    high_obj = _import_mesh_file(high_path)
    with timed_step(f"meshdata_from_object high ({high_path.name})"):
        high_data = meshdata_from_object(high_obj, label=f"high/{high_path.name}")

    return MeshPair(
        low=low_data,
        high=high_data,
        low_name=low_obj.name,
        high_name=high_obj.name,
    )


def build_bvh(mesh: MeshData):
    """Triangle BVH for ray tests (Blender mathutils; works in --background)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    with timed_step(f"BVHTree.FromPolygons ({len(mesh.faces)} tris)"):
        verts = [Vector(v.tolist()) for v in mesh.vertices]
        polys = [tuple(int(i) for i in face) for face in mesh.faces]
        return BVHTree.FromPolygons(verts, polys)


def _object_export_override(obj) -> dict:
    import bpy

    view_layer = bpy.context.view_layer
    for item in view_layer.objects:
        item.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    base = {
        "active_object": obj,
        "object": obj,
        "selected_objects": [obj],
        "editable_objects": [obj],
        "view_layer": view_layer,
    }
    view3d = _import_context_override()
    if view3d is not None:
        base.update(view3d)
    return base


def triangulate_mesh_preserve_shading(obj) -> None:
    """Convert quads/ngons to tris without recalculating smooth/sharp shading."""
    import bpy

    mesh = obj.data
    if all(len(poly.vertices) == 3 for poly in mesh.polygons):
        mesh.calc_loop_triangles()
        return

    base = _object_export_override(obj)
    edit_kwargs = {**base, "edit_object": obj}
    with bpy.context.temp_override(**edit_kwargs):
        bpy.ops.object.mode_set(mode="EDIT")
    with bpy.context.temp_override(**edit_kwargs):
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
    with bpy.context.temp_override(**base):
        bpy.ops.object.mode_set(mode="OBJECT")
    mesh.calc_loop_triangles()


def export_triangulated_fbx(obj, filepath: str | Path, *, label: str = "") -> None:
    """Export one mesh as triangulated FBX with loop tangents (use_tspace)."""
    import bpy

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tag = f" ({label})" if label else ""

    mesh = obj.data
    uv_layer = _active_uv_layer(mesh)

    with timed_step(f"triangulate{tag}"):
        triangulate_mesh_preserve_shading(obj)

    with timed_step(f"calc_tangents{tag}"):
        mesh.calc_tangents(uvmap=uv_layer.name)

    fbx_kwargs = {
        "filepath": str(filepath),
        "check_existing": False,
        "use_selection": True,
        "use_active_collection": False,
        "global_scale": 1.0,
        "apply_unit_scale": True,
        "apply_scale_options": "FBX_SCALE_NONE",
        "use_space_transform": True,
        "bake_space_transform": False,
        "object_types": {"MESH"},
        "use_mesh_modifiers": False,
        "use_mesh_modifiers_render": False,
        "mesh_smooth_type": "FACE",
        "use_subsurf": False,
        "use_mesh_edges": False,
        "use_tspace": True,
        "path_mode": "AUTO",
        "axis_forward": "-Z",
        "axis_up": "Y",
    }

    base = _object_export_override(obj)
    with timed_step(f"export FBX {filepath.name}"):
        with bpy.context.temp_override(**base):
            bpy.ops.export_scene.fbx(**fbx_kwargs)

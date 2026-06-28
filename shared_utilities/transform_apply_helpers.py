"""Smart mesh transform apply — correct normals when determinant is negative."""

from __future__ import annotations

import bpy
from mathutils import Matrix


def matrix_has_negative_scale(matrix: Matrix) -> bool:
    """True when the 3x3 linear part reverses orientation (mirror / negative scale)."""
    return matrix.to_3x3().determinant() < 0.0


def flip_mesh_normals(mesh: bpy.types.Mesh) -> None:
    """Reverse face winding and negate custom split normals when present."""
    for poly in mesh.polygons:
        poly.flip()
    if mesh.has_custom_normals:
        # Blender 4.1+: calc_normals_split removed; corner_normals is the cache.
        mesh.normals_split_custom_set(
            tuple(
                tuple(-cn.vector)
                for cn in mesh.corner_normals
            ),
        )
    mesh.update()


def smart_transform_mesh_data(mesh: bpy.types.Mesh, matrix: Matrix) -> None:
    """``mesh.transform`` plus normal correction for orientation-reversing matrices."""
    mesh.transform(matrix)
    if matrix_has_negative_scale(matrix):
        flip_mesh_normals(mesh)


def smart_bake_matrix_local_into_mesh_data(obj: bpy.types.Object) -> None:
    """Bake ``matrix_local`` into mesh data; fix inverted normals on negative scale."""
    if obj.type != 'MESH' or obj.data is None:
        return
    local = obj.matrix_local.copy()
    smart_transform_mesh_data(obj.data, local)
    parent = obj.parent
    if parent is not None:
        obj.matrix_world = parent.matrix_world.copy()
    else:
        obj.matrix_world = Matrix.Identity(4)

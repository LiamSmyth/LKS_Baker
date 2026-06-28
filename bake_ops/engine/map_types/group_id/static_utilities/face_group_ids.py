"""Read per-face integer group ids from mesh data or Blender objects."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData

# Mirror root ``lks_constants`` — avoid ``static_utilities/__init__.py`` (imports bpy).
ATTR_SCULPT_FACE_SET = ".sculpt_face_set"
GROUP_ID_POLYGROUP_ATTR_CANDIDATES: tuple[str, ...] = ("polygroup", "pg", "PolyGroup")


def resolve_group_id_attribute_name(
    *,
    preset: str,
    custom_name: str,
) -> str:
    """Map UI preset + custom RNA to the face attribute name to read."""
    preset_key = str(preset).upper()
    if preset_key == "FACE_SET":
        return ATTR_SCULPT_FACE_SET
    if preset_key == "POLYGROUP":
        return GROUP_ID_POLYGROUP_ATTR_CANDIDATES[0]
    custom = str(custom_name).strip()
    if not custom:
        raise ValueError("group_id CUSTOM preset requires a non-empty attribute name")
    return custom


def _first_existing_face_int_attribute(mesh, candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        attr = mesh.attributes.get(name)
        if attr is None:
            continue
        if attr.domain != "FACE" or attr.data_type != "INT":
            continue
        return name
    return None


def _resolve_face_int_attribute(mesh, attribute_name: str) -> tuple[str, object] | None:
    """Return resolved attribute name and RNA block, or None when not readable."""
    attr = mesh.attributes.get(attribute_name)
    if attr is None:
        if attribute_name == GROUP_ID_POLYGROUP_ATTR_CANDIDATES[0]:
            fallback = _first_existing_face_int_attribute(
                mesh,
                (*GROUP_ID_POLYGROUP_ATTR_CANDIDATES, ATTR_SCULPT_FACE_SET),
            )
            if fallback is None:
                return None
            attribute_name = fallback
            attr = mesh.attributes[attribute_name]
        else:
            return None

    if attr.domain != "FACE" or attr.data_type != "INT":
        return None
    return attribute_name, attr


def face_int_attribute_skip_reason(mesh, attribute_name: str, *, mesh_label: str) -> str | None:
    """Return human-readable skip reason when *attribute_name* is missing or invalid."""
    if _resolve_face_int_attribute(mesh, attribute_name) is not None:
        return None
    if attribute_name == GROUP_ID_POLYGROUP_ATTR_CANDIDATES[0]:
        return (
            f"{mesh_label} has no polygroup-like face INT attribute "
            f"(tried {GROUP_ID_POLYGROUP_ATTR_CANDIDATES + (ATTR_SCULPT_FACE_SET,)!r})"
        )
    return f"{mesh_label} missing face INT attribute {attribute_name!r}"


def get_group_id_derive_skip_reason(obj, *, map_entry=None) -> str | None:
    """Return skip reason when group_id cannot be derived from *obj*; None when OK."""
    if obj.type != "MESH" or obj.data is None:
        return f"'{obj.name}' is not a mesh object"

    from lks_baker.bake_ops.engine.map_types.group_id.group_id_raster_cfg import (
        GroupIdRasterConfig,
        config_from_entry,
    )

    try:
        config = config_from_entry(map_entry) if map_entry is not None else GroupIdRasterConfig()
    except ValueError as exc:
        return str(exc)

    return face_int_attribute_skip_reason(
        obj.data,
        config.attribute_name,
        mesh_label=obj.name,
    )


def read_triangulated_face_int_ids_from_object(obj, attribute_name: str) -> np.ndarray:
    """Return one int group id per loop triangle on *obj*."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    tri_count = len(mesh.loop_triangles)
    if tri_count == 0:
        return np.zeros(0, dtype=np.int32)

    skip_reason = face_int_attribute_skip_reason(mesh, attribute_name, mesh_label=obj.name)
    if skip_reason is not None:
        raise ValueError(skip_reason)

    resolved_name, attr = _resolve_face_int_attribute(mesh, attribute_name)
    if resolved_name is None or attr is None:
        raise ValueError(
            face_int_attribute_skip_reason(mesh, attribute_name, mesh_label=obj.name)
            or f"{obj.name} missing face INT attribute {attribute_name!r}",
        )
    attribute_name = resolved_name

    poly_count = len(mesh.polygons)
    poly_values = np.empty(poly_count, dtype=np.int32)
    attr.data.foreach_get("value", poly_values)

    poly_indices = np.empty(tri_count, dtype=np.int32)
    mesh.loop_triangles.foreach_get("polygon_index", poly_indices)
    return poly_values[poly_indices].astype(np.int32, copy=False)


def mesh_with_face_int_ids(
    mesh: MeshData,
    face_int_ids: np.ndarray,
) -> MeshData:
    """Return *mesh* copy carrying per-triangle ``face_int_ids``."""
    ids = np.asarray(face_int_ids, dtype=np.int32)
    if len(ids) != len(mesh.faces):
        raise ValueError(
            f"face_int_ids length {len(ids)} != triangle count {len(mesh.faces)}",
        )
    return MeshData(
        vertices=mesh.vertices,
        faces=mesh.faces,
        normals=mesh.normals,
        face_uvs=mesh.face_uvs,
        face_int_ids=ids,
    )


def synthetic_face_int_ids(mesh: MeshData) -> np.ndarray:
    """Deterministic per-triangle ids for fixtures without authored attributes."""
    return (np.arange(len(mesh.faces), dtype=np.int32) + 1)


def resolve_mesh_face_int_ids(mesh: MeshData) -> np.ndarray:
    """Use authored ids when present; otherwise synthesize for tests."""
    if mesh.face_int_ids is not None:
        ids = np.asarray(mesh.face_int_ids, dtype=np.int32)
        if len(ids) != len(mesh.faces):
            raise ValueError(
                f"mesh.face_int_ids length {len(ids)} != triangle count {len(mesh.faces)}",
            )
        return ids
    return synthetic_face_int_ids(mesh)

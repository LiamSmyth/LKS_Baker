"""Per-slot emit RGB extracted from Principled materials for engine H→L raster."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MeshMaterialEmitData:
    """Emit-encoded RGB per material slot and per-face slot indices."""

    slot_emit_rgb: np.ndarray
    face_slot_index: np.ndarray


def mesh_face_material_indices(mesh) -> np.ndarray:
    """Return per-triangle material slot indices aligned with ``mesh.loop_triangles``."""
    tri_count = len(mesh.loop_triangles)
    mat_flat = np.empty(tri_count, dtype=np.int32)
    mesh.loop_triangles.foreach_get("material_index", mat_flat)
    return mat_flat


def mesh_material_emit_data_from_object(obj, profile: str) -> MeshMaterialEmitData:
    """Collect emit RGB per slot from one mesh object's material slots."""
    from lks_baker.bake_ops.static_utilities.bake_shader_profiles import (
        emit_rgb_from_principled_material,
    )

    mesh = obj.data
    slot_colors: list[tuple[float, float, float]] = []
    for slot in obj.material_slots:
        source = slot.material
        if source is None:
            slot_colors.append((0.5, 0.5, 0.5))
        else:
            rgba = emit_rgb_from_principled_material(source, profile=profile)
            slot_colors.append((float(rgba[0]), float(rgba[1]), float(rgba[2])))
    if not slot_colors:
        slot_colors.append((0.5, 0.5, 0.5))

    face_slot_index = mesh_face_material_indices(mesh)
    return MeshMaterialEmitData(
        slot_emit_rgb=np.asarray(slot_colors, dtype=np.float32),
        face_slot_index=face_slot_index,
    )

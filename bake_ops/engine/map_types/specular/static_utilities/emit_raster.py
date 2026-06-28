"""H→L specular emit raster — raycast from low UV surface to high mesh materials."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.static_utilities.low_surface_atlas import (
    rasterize_low_surface,
)
from lks_baker.bake_ops.engine.static_utilities.mesh_data import MeshData
from lks_baker.bake_ops.engine.static_utilities.mesh_material_emit import (
    MeshMaterialEmitData,
)


def emit_raster_specular(
    low: MeshData,
    high: MeshData,
    material_data: MeshMaterialEmitData,
    image_size: int,
    *,
    cage_extrusion: float = 0.01,
    max_ray_distance: float = 0.0,
    ray_bias: float = 1e-4,
) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize specular emit from high materials onto low UV atlas.

    Inputs: world-space low mesh, world-space high mesh, per-slot emit RGB.
    Output: RGBA float32 H×W×4 (grayscale specular in RGB) and valid mask.
    """
    from mathutils import Vector

    from lks_baker.bake_ops.engine.static_utilities.blender_mesh import build_bvh

    position, normal, valid = rasterize_low_surface(low, image_size)
    bvh = build_bvh(high)
    rgba = np.zeros((image_size, image_size, 4), dtype=np.float32)
    max_dist = float(max_ray_distance) if max_ray_distance > 0.0 else 1e6
    origin_offset = float(ray_bias) + float(cage_extrusion)

    ys, xs = np.nonzero(valid)
    for y, x in zip(ys, xs, strict=False):
        n = normal[y, x]
        origin = position[y, x] + n * origin_offset
        hit_location, _hit_normal, face_index, _distance = bvh.ray_cast(
            Vector(origin.tolist()),
            Vector(n.tolist()),
            max_dist,
        )
        if hit_location is None or face_index is None:
            continue
        if face_index < 0 or face_index >= len(material_data.face_slot_index):
            continue
        slot_idx = int(material_data.face_slot_index[face_index])
        if slot_idx < 0 or slot_idx >= len(material_data.slot_emit_rgb):
            continue
        rgb = material_data.slot_emit_rgb[slot_idx]
        rgba[y, x, 0] = rgb[0]
        rgba[y, x, 1] = rgb[1]
        rgba[y, x, 2] = rgb[2]
        rgba[y, x, 3] = 1.0

    return rgba, valid

"""Tangent-space bent normal from object-space atlas bent-normal core."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.map_types.bent_normal_object.static_utilities.bent_normal_object import (
    _safe_normalize,
    bent_normal_object,
    pack_bent_normal_rgb,
    surface_tangent_frames,
)
from lks_baker.bake_ops.engine.settings.bent_normal_settings import (
    HemisphereTraceSettings,
    hemisphere_trace_to_object_settings,
)


def _object_to_tangent(
    vector: np.ndarray,
    tangent: np.ndarray,
    bitangent: np.ndarray,
    normal: np.ndarray,
) -> np.ndarray:
    return np.stack(
        (
            np.sum(vector * tangent, axis=-1),
            np.sum(vector * bitangent, axis=-1),
            np.sum(vector * normal, axis=-1),
        ),
        axis=-1,
    ).astype(np.float32)


def atlas_hemisphere_bent_normal(
    position: np.ndarray,
    object_normal: np.ndarray,
    island_id: np.ndarray,
    valid: np.ndarray,
    settings: HemisphereTraceSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute tangent-space bent normals via object-space atlas integration.

    Inputs: internal object-space ``position`` / ``normal_object`` atlases (OpenGL PNG row order).
    Output: tangent-space bent normal RGB (``rgb = n * 0.5 + 0.5``).
    """
    obj_settings = hemisphere_trace_to_object_settings(settings)
    bent_object, _object_rgba = bent_normal_object(
        position,
        object_normal,
        island_id,
        valid,
        obj_settings,
    )
    tangent, bitangent, normal = surface_tangent_frames(object_normal, position, island_id)
    bent_tangent = _object_to_tangent(bent_object, tangent, bitangent, normal)
    bent_tangent = _safe_normalize(bent_tangent)
    bent_tangent[~valid] = 0.0
    rgba = pack_bent_normal_rgb(bent_tangent, valid)
    return rgba, bent_tangent

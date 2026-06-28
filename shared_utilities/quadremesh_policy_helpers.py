"""Policy helpers for LKS Quad Remesh scope, symmetry, and count behavior."""

from __future__ import annotations

import bpy

SCOPE_MODE_AUTO = 'AUTO'
SCOPE_MODE_WHOLE_OBJECT = 'WHOLE_OBJECT'
SUPPORTED_SUBSET_SCOPES = frozenset({
    'SELECTED_FACES',
    'VISIBLE_SCULPT_FACES',
})

SCOPE_MODE_ITEMS = [
    ('AUTO', 'Auto', 'Use selected faces or visible sculpt faces when a subset is active, otherwise remesh the whole object'),
    ('WHOLE_OBJECT', 'Whole Object',
     'Always remesh the whole active mesh object even if a subset is active'),
]


def is_subset_scope(scope: str) -> bool:
    """Return True when *scope* represents a subset remesh workflow."""
    return scope in SUPPORTED_SUBSET_SCOPES


def normalize_scope(scope: str) -> str:
    """Map unsupported or future scopes back to a safe executable scope."""
    if scope in SUPPORTED_SUBSET_SCOPES:
        return scope
    return SCOPE_MODE_WHOLE_OBJECT


def resolve_scope_mode(context: bpy.types.Context, scope_mode: str) -> str:
    """Resolve UI scope mode into an actual remesh scope."""
    if scope_mode == SCOPE_MODE_WHOLE_OBJECT:
        return SCOPE_MODE_WHOLE_OBJECT

    from . import quadremesh_subset_helpers

    return normalize_scope(quadremesh_subset_helpers.detect_remesh_scope(context))


def format_scope_label(scope: str) -> str:
    """Return a human-readable label for a resolved remesh scope."""
    if scope == 'SELECTED_FACES':
        return 'Selected Faces'
    if scope == 'VISIBLE_SCULPT_FACES':
        return 'Visible Sculpt Faces'
    if scope == 'ACTIVE_FACE_SET':
        return 'Active Face Set'
    return 'Whole Object'


def compute_target_count(
    base_target_count: int,
    source_obj: bpy.types.Object | None,
    remesh_obj: bpy.types.Object | None,
    *,
    scale_to_subset: bool,
) -> int:
    """Compute the effective target count for a remesh job."""
    if not scale_to_subset or source_obj is None or remesh_obj is None:
        return max(1, int(base_target_count))

    source_face_count = len(
        source_obj.data.polygons) if source_obj.type == 'MESH' else 0
    remesh_face_count = len(
        remesh_obj.data.polygons) if remesh_obj.type == 'MESH' else 0
    if source_face_count <= 0 or remesh_face_count <= 0:
        return max(1, int(base_target_count))

    ratio = remesh_face_count / source_face_count
    scaled_target_count = round(base_target_count * ratio)
    return max(1, int(scaled_target_count))

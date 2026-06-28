"""World-space position map encoding helpers (no bpy import)."""

from __future__ import annotations

_BBOX_AXIS_EPSILON = 1e-6


def longest_world_bbox_extent(
    bbox_min: tuple[float, float, float],
    bbox_max: tuple[float, float, float],
) -> float:
    """Return the longest edge length of a world-space axis-aligned bounding box."""
    return max(bbox_max[axis] - bbox_min[axis] for axis in range(3))


def normalize_world_position_to_bbox(
    position: tuple[float, float, float],
    bbox_min: tuple[float, float, float],
    bbox_max: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Remap world position to 0–1 with uniform scale from the longest AABB edge."""
    longest = longest_world_bbox_extent(bbox_min, bbox_max)
    if longest <= _BBOX_AXIS_EPSILON:
        return 0.0, 0.0, 0.0
    return (
        (position[0] - bbox_min[0]) / longest,
        (position[1] - bbox_min[1]) / longest,
        (position[2] - bbox_min[2]) / longest,
    )

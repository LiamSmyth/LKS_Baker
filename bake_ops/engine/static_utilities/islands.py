"""Connected-component island IDs; island-aware convolution helpers."""
from __future__ import annotations

import numpy as np

# Seam-aware labeling must not explode into per-texel charts (blurs iterate labels).
_MAX_ISLANDS = 48


def label_islands(valid: np.ndarray) -> np.ndarray:
    """Connected-component island IDs; -1 = background."""
    if not np.any(valid):
        return np.full(valid.shape, -1, dtype=np.int32)
    try:
        from scipy import ndimage

        labeled, _ = ndimage.label(valid)
        out = labeled.astype(np.int32, copy=False) - 1
        out[~valid] = -1
        return out
    except ImportError:
        height, width = valid.shape
        block_h = np.zeros((height, width), dtype=bool)
        block_v = np.zeros((height, width), dtype=bool)
        return _label_with_blocked_edges(valid, block_h, block_v)


def island_label_count(island_id: np.ndarray) -> int:
    """Island label count.

    Args:
        island_id: H×W int32 UV island label per texel.

    Returns:
        ``int`` result.
    """
    labels = island_id[island_id >= 0]
    return int(len(np.unique(labels))) if labels.size else 0


def _coalesce_island_ids(island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Fall back to alpha CC labels when chart count is unreasonable."""
    if island_label_count(island_id) <= _MAX_ISLANDS:
        return island_id
    return label_islands(valid)


def _position_seam_blocks(
    valid: np.ndarray,
    position: np.ndarray,
    *,
    position_seam_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Block adjacency only at large position jumps (UV chart / mirror cuts)."""
    block_h = np.zeros(valid.shape, dtype=bool)
    block_v = np.zeros(valid.shape, dtype=bool)
    pos = position.astype(np.float32)
    if float(np.max(np.abs(pos))) <= 1e-4:
        return block_h, block_v

    dh = np.linalg.norm(pos[:, 1:, :] - pos[:, :-1, :], axis=-1)
    seam_h = valid[:, :-1] & valid[:, 1:] & (dh > position_seam_threshold)
    block_h[:, :-1] |= seam_h
    block_h[:, 1:] |= seam_h

    dv = np.linalg.norm(pos[1:, :, :] - pos[:-1, :, :], axis=-1)
    seam_v = valid[:-1, :] & valid[1:, :] & (dv > position_seam_threshold)
    block_v[:-1, :] |= seam_v
    block_v[1:, :] |= seam_v
    return block_h, block_v


def _label_with_blocked_edges(valid: np.ndarray, block_h: np.ndarray, block_v: np.ndarray) -> np.ndarray:
    """Connected components on ``valid`` without crossing blocked edges (union-find)."""
    height, width = valid.shape
    flat_count = height * width
    parent = np.arange(flat_count, dtype=np.int32)

    def find(index: int) -> int:
        root = index
        while parent[root] != root:
            root = int(parent[root])
        while parent[index] != index:
            nxt = int(parent[index])
            parent[index] = root
            index = nxt
        return root

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for y in range(height):
        row_offset = y * width
        for x in range(width):
            if not valid[y, x]:
                continue
            index = row_offset + x
            if x + 1 < width and valid[y, x + 1] and not block_h[y, x]:
                union(index, index + 1)
            if y + 1 < height and valid[y + 1, x] and not block_v[y, x]:
                union(index, index + width)

    labels = np.full(flat_count, -1, dtype=np.int32)
    next_id = 0
    for index in range(flat_count):
        if not valid.flat[index]:
            continue
        root = find(index)
        if labels[root] < 0:
            labels[root] = next_id
            next_id += 1
        labels[index] = labels[root]

    out = labels.reshape(height, width)
    out[~valid] = -1
    return out


def label_islands_seam_aware(
    valid: np.ndarray,
    position: np.ndarray | None = None,
    *,
    position_seam_threshold: float = 0.04,
) -> np.ndarray:
    """Split alpha CC only at large position discontinuities (mirror/chart seams)."""
    if not np.any(valid):
        return np.full(valid.shape, -1, dtype=np.int32)
    if position is None or position.shape[:2] != valid.shape[:2]:
        return label_islands(valid)

    block_h, block_v = _position_seam_blocks(
        valid,
        position,
        position_seam_threshold=position_seam_threshold,
    )
    return _label_with_blocked_edges(valid, block_h, block_v)


def resolve_island_ids(
    valid: np.ndarray,
    position: np.ndarray | None = None,
    object_normal: np.ndarray | None = None,
    tangent_normal: np.ndarray | None = None,
) -> np.ndarray:
    """Chart islands for seam-safe filters; never return per-texel fragmentation."""
    _ = object_normal
    _ = tangent_normal
    base = label_islands(valid)
    has_position = (
        position is not None
        and position.shape[:2] == valid.shape[:2]
        and float(np.max(np.abs(position))) > 1e-4
    )
    if not has_position:
        return base

    seam = label_islands_seam_aware(valid, position, position_seam_threshold=0.04)
    if island_label_count(seam) > max(island_label_count(base) * 2, _MAX_ISLANDS):
        return base
    return seam


def _iter_island_labels(island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    labels = np.unique(island_id[island_id >= 0])
    if labels.size <= _MAX_ISLANDS:
        return labels
    coalesced = label_islands(valid)
    return np.unique(coalesced[coalesced >= 0])


def island_inpaint_gaps(
    field: np.ndarray,
    island_id: np.ndarray,
    known: np.ndarray,
    *,
    max_passes: int = 64,
) -> np.ndarray:
    """Fill unknown texels within each UV island from same-island known neighbors."""
    out = field.astype(np.float32, copy=True)
    if field.ndim != 2:
        raise ValueError("island_inpaint_gaps expects H×W scalar field")

    active = (island_id >= 0) & (~known)
    if not np.any(active):
        return out

    filled = known.copy()
    for _ in range(max_passes):
        if not np.any(active):
            break
        accum = np.zeros_like(out, dtype=np.float32)
        counts = np.zeros(out.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = np.roll(np.roll(out, dy, axis=0), dx, axis=1)
            shift_filled = np.roll(np.roll(filled, dy, axis=0), dx, axis=1)
            shift_island = np.roll(np.roll(island_id, dy, axis=0), dx, axis=1)
            same_island = (shift_island == island_id) & (island_id >= 0)
            contrib = shift_filled & same_island
            accum += np.where(contrib, shifted, 0.0)
            counts += contrib.astype(np.float32)

        can_fill = active & (counts > 0.0)
        if not np.any(can_fill):
            break
        out[can_fill] = (accum[can_fill] / counts[can_fill])
        filled[can_fill] = True
        active[can_fill] = False
    return out


def _island_sobel_axis(field: np.ndarray, island_id: np.ndarray, valid: np.ndarray, axis: int) -> np.ndarray:
    from scipy import ndimage

    out = np.zeros(field.shape[:2], dtype=np.float32)
    kernel = np.array([-1.0, 0.0, 1.0], dtype=np.float32)
    work_id = _coalesce_island_ids(island_id, valid)

    for label in _iter_island_labels(work_id, valid):
        mask = work_id == label
        patch = np.where(mask, field, 0.0)
        deriv = ndimage.convolve1d(patch, kernel, axis=axis, mode="nearest") * 0.5
        out[mask] = deriv[mask]

    out[~valid] = 0.0
    return out


def island_sobel_dx(field: np.ndarray, island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Island sobel dx.

    Args:
        field: ``np.ndarray`` value.
        island_id: H×W int32 UV island label per texel.
        valid: H×W bool mask of texels with mesh coverage.

    Returns:
        ``np.ndarray`` result.
    """
    return _island_sobel_axis(field, island_id, valid, axis=1)


def island_sobel_dy(field: np.ndarray, island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Island sobel dy.

    Args:
        field: ``np.ndarray`` value.
        island_id: H×W int32 UV island label per texel.
        valid: H×W bool mask of texels with mesh coverage.

    Returns:
        ``np.ndarray`` result.
    """
    return _island_sobel_axis(field, island_id, valid, axis=0)


def island_sobel_divergence(field: np.ndarray, island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Island sobel divergence.

    Args:
        field: ``np.ndarray`` value.
        island_id: H×W int32 UV island label per texel.
        valid: H×W bool mask of texels with mesh coverage.

    Returns:
        ``np.ndarray`` result.
    """
    return island_sobel_dx(field, island_id, valid) + island_sobel_dy(field, island_id, valid)


def island_laplacian(field: np.ndarray, island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Island laplacian.

    Args:
        field: ``np.ndarray`` value.
        island_id: H×W int32 UV island label per texel.
        valid: H×W bool mask of texels with mesh coverage.

    Returns:
        ``np.ndarray`` result.
    """
    return island_sobel_divergence(
        island_sobel_dx(field, island_id, valid),
        island_id,
        valid,
    ) + island_sobel_divergence(
        island_sobel_dy(field, island_id, valid),
        island_id,
        valid,
    )


def tangent_normal_divergence(normal: np.ndarray, island_id: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Tangent normal divergence.

    Args:
        normal: ``np.ndarray`` value.
        island_id: H×W int32 UV island label per texel.
        valid: H×W bool mask of texels with mesh coverage.

    Returns:
        ``np.ndarray`` result.
    """
    dnx_dx = island_sobel_dx(normal[..., 0], island_id, valid)
    dny_dy = island_sobel_dy(normal[..., 1], island_id, valid)
    return dnx_dx + dny_dy

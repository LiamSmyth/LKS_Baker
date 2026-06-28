"""Symmetry helper utilities isolated from auto seam helpers.

Responsibilities:
 - Detect exact (or near-exact) mirror symmetry about primary axes (X/Y/Z) using bbox center.
 - Optional caching of symmetry mapping for repeated operator runs.
 - Provide functions to propagate seams from processed half to mirrored half.
 - Provide mask utility for half‑mesh restricted computation.
"""
from __future__ import annotations
import bmesh
from typing import Dict, Tuple, List, Set, Iterable

CACHE_KEY = "_lks_symmetry_cache"


def _build_cache_record(axis_index: int, center: float, vert_pairs: List[Tuple[int, int]], vert_count: int):
    return {
        "axis": axis_index,
        "center": center,
        "pairs": vert_pairs,  # list of (pos_idx, neg_idx)
        "vert_count": vert_count,
    }


def detect_mirror_symmetry(
    bm: bmesh.types.BMesh,
    tol: float = 1e-6,
    allow_cache: bool = True,
    obj=None,
    min_ratio: float = 1.0,
    debug: bool = False,
):
    """Detect dominant axial mirror symmetry.

    Returns (axis_index, center_coord, vert_map, meta)
    vert_map maps positive-side verts to their negative counterparts (excludes centerline verts).
    Simplified reimplementation after corruption – focuses on correctness & clarity.
    """
    bm.verts.ensure_lookup_table()
    if not bm.verts:
        return (None, None, {}, {"cached": False, "match_ratio": 0.0})

    # Basic bbox centers
    mins = [min(v.co[i] for v in bm.verts) for i in range(3)]
    maxs = [max(v.co[i] for v in bm.verts) for i in range(3)]
    centers = [(mins[i] + maxs[i]) * 0.5 for i in range(3)]

    # Helper to build mapping for an axis
    def build_map(ax: int):
        center = centers[ax]
        # Side classification uses a separate tiny epsilon; user tol only for matching
        span = maxs[ax] - mins[ax]
        classify_eps = min(max(1e-9, span * 1e-5), 1e-4)
        pos_verts: List[bmesh.types.BMVert] = []
        neg_verts: List[bmesh.types.BMVert] = []
        for v in bm.verts:
            d = v.co[ax] - center
            if d > classify_eps:
                pos_verts.append(v)
            elif d < -classify_eps:
                neg_verts.append(v)
        if not pos_verts or not neg_verts:
            # Degenerate along this axis
            return {}, {
                "matched_pairs": 0,
                "unmatched_pos": len(pos_verts),
                "unmatched_neg": len(neg_verts),
                "match_ratio": 0.0,
                "classify_eps": classify_eps,
            }, center
        # Matching strategy: multi-pass escalating tolerance until reasonable coverage achieved
        base_match_tol = max(tol, 1e-9)
        tol_passes = [base_match_tol,
                      base_match_tol * 2.0, base_match_tol * 4.0]
        best_local_map: Dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}
        best_stats = {}
        neg_pool_all = list(neg_verts)
        # Precompute mirrored target positions for positives (to avoid recomputing per pass)
        mirrored_targets = []
        for pv in pos_verts:
            mc = pv.co.copy()
            mc[ax] = center - (pv.co[ax] - center)
            mirrored_targets.append((pv, mc))

        for pass_i, match_tol in enumerate(tol_passes):
            used_neg: Set[bmesh.types.BMVert] = set()
            vert_map: Dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}
            unmatched_pos = 0
            # Simple O(n^2) search capped if vertex count modest; else build coarse bucket by rounding axis
            if len(pos_verts) * len(neg_verts) <= 400000:  # heuristic
                for pv, mc in mirrored_targets:
                    best_d = match_tol * 2.0
                    match = None
                    for nv in neg_pool_all:
                        if nv in used_neg:
                            continue
                        dlen = (nv.co - mc).length
                        if dlen <= best_d:
                            best_d = dlen
                            match = nv
                    if match:
                        vert_map[pv] = match
                        used_neg.add(match)
                    else:
                        unmatched_pos += 1
            else:
                # Bucket by rounded axis coord for scalability
                inv = 1.0 / match_tol
                buckets: Dict[int, List[bmesh.types.BMVert]] = {}
                for nv in neg_pool_all:
                    buckets.setdefault(
                        int(round(nv.co[ax] * inv)), []).append(nv)
                for pv, mc in mirrored_targets:
                    key = int(round(mc[ax] * inv))
                    cand_list = []
                    for dk in (key - 1, key, key + 1):
                        cand_list.extend(buckets.get(dk, ()))
                    best_d = match_tol * 2.0
                    match = None
                    for nv in cand_list:
                        if nv in used_neg:
                            continue
                        dlen = (nv.co - mc).length
                        if dlen <= best_d:
                            best_d = dlen
                            match = nv
                    if match:
                        vert_map[pv] = match
                        used_neg.add(match)
                    else:
                        unmatched_pos += 1
            matched = len(vert_map)
            unmatched_neg = len(neg_verts) - len(used_neg)
            total_pairs = matched + unmatched_pos + unmatched_neg
            ratio = matched / total_pairs if total_pairs else 0.0
            # Accept early if ratio perfect or meets min_ratio target
            if ratio >= min_ratio or ratio == 1.0:
                best_local_map = vert_map
                best_stats = {
                    "matched_pairs": matched,
                    "unmatched_pos": unmatched_pos,
                    "unmatched_neg": unmatched_neg,
                    "match_ratio": ratio,
                    "classify_eps": classify_eps,
                    "pass": pass_i,
                    "match_tol": match_tol,
                }
                break
            # Track best so far
            if ratio > best_stats.get("match_ratio", -1.0):
                best_local_map = vert_map
                best_stats = {
                    "matched_pairs": matched,
                    "unmatched_pos": unmatched_pos,
                    "unmatched_neg": unmatched_neg,
                    "match_ratio": ratio,
                    "classify_eps": classify_eps,
                    "pass": pass_i,
                    "match_tol": match_tol,
                }
        if not best_stats:
            best_stats = {"matched_pairs": 0, "unmatched_pos": len(pos_verts), "unmatched_neg": len(
                neg_verts), "match_ratio": 0.0, "classify_eps": classify_eps, "pass": -1, "match_tol": base_match_tol}
        return best_local_map, best_stats, center

    best_axis: int | None = None
    best_center: float | None = None
    best_map: Dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}
    best_meta: Dict[str, object] = {"match_ratio": 0.0}
    for ax in range(3):
        vmap, meta, center = build_map(ax)
        ratio = meta["match_ratio"]
        if ratio > best_meta.get("match_ratio", 0.0):
            best_axis, best_center, best_map, best_meta = ax, center, vmap, meta

    # Accept if meets strict min_ratio or relaxed fallback (>=98% & at least half the verts paired)
    if best_axis is None:
        return (None, None, {}, {"cached": False, "match_ratio": 0.0})
    strict_ok = best_meta["match_ratio"] >= min_ratio
    relaxed_ok = (not strict_ok) and best_meta["match_ratio"] >= 0.98 and best_meta.get(
        "matched_pairs", 0) >= 2
    if not (strict_ok or relaxed_ok):
        return (None, None, {}, {"cached": False, "match_ratio": best_meta["match_ratio"]})
    best_meta["axis"] = best_axis
    best_meta["cached"] = False
    best_meta["relaxed"] = bool(relaxed_ok and not strict_ok)
    return (best_axis, best_center, best_map, best_meta)


def build_positive_half_face_mask(bm: bmesh.types.BMesh, axis_index: int, center: float, tol: float) -> Set[int]:
    """Return face indices on authoritative ("positive") side for half-compute.

    IMPORTANT: Decoupled from user symmetry tolerance. We only want tolerance to affect
    detection robustness (pairing), not how much of the mesh we process. Previously we used
    (center - tol) which caused the region to expand as tolerance increased. Now we apply a
    tiny clamped epsilon based on mesh span so the processed half is stable.
    """
    bm.faces.ensure_lookup_table()
    if not bm.faces:
        return set()
    # Compute span along axis for scale-invariant epsilon
    axis_vals = [v.co[axis_index] for v in bm.verts]
    span = max(axis_vals) - min(axis_vals) if axis_vals else 0.0
    # small, bounded; independent of user tol
    eps = min(max(1e-9, span * 1e-5), 5e-4)
    cutoff = center - eps
    mask: Set[int] = set()
    for f in bm.faces:
        # Any vertex on or beyond the plane (within eps) counts
        if any(v.co[axis_index] >= cutoff for v in f.verts):
            mask.add(f.index)
    return mask


def iter_half_mesh_verts(bm: bmesh.types.BMesh, axis_index: int, center: float, tol: float) -> Iterable[bmesh.types.BMVert]:
    """Yield verts on positive side using stable epsilon (not user tol)."""
    if not bm.verts:
        return
    axis_vals = [v.co[axis_index] for v in bm.verts]
    span = max(axis_vals) - min(axis_vals) if axis_vals else 0.0
    eps = min(max(1e-9, span * 1e-5), 5e-4)
    cutoff = center - eps
    for v in bm.verts:
        if v.co[axis_index] >= cutoff:
            yield v


def half_edge_filter(edge: bmesh.types.BMEdge, axis_index: int, center: float, tol: float) -> bool:
    """Return True if edge should be considered during half-side computation (any vert in positive band)."""
    return any(v.co[axis_index] >= center - tol for v in edge.verts)


def invalidate_symmetry_cache(obj):
    # Object-attached symmetry cache was never written; kept as a stable hook.
    if obj is None:
        return


def propagate_mirrored_seams(bm: bmesh.types.BMesh, axis_index: int, center: float,
                             vert_map: Dict[bmesh.types.BMVert, bmesh.types.BMVert],
                             symmetry_tol: float = 1e-6,
                             prune_extra: bool = False):
    """Copy seam state from processed (positive) side edges to mirrored counterparts.

    Extended to also mirror seams for edges that include exactly one positive-side vertex (mapped)
    and one centerline vertex. Previously those edges were skipped because the centerline vertex
    is not present in vert_map (we intentionally omit centerline verts during detection). This
    caused half-compute diskify paths that start/end on the symmetry plane to *not* mirror fully.

    Args:
        bm: BMesh
        axis_index: symmetry axis (0=X,1=Y,2=Z)
        center: axis coordinate of symmetry plane
        vert_map: mapping positive->negative BMVert
        symmetry_tol: tolerance band for considering a vertex "on" the symmetry plane
        prune_extra: if True, remove seams on the mirrored (negative) side that do NOT have
            a corresponding seam on the positive side (or centerline). This enforces strict
            mirroring instead of additive-only propagation.
    """
    if axis_index is None or not vert_map:
        return

    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    axis_vals = [v.co[axis_index] for v in bm.verts]
    span = max(axis_vals) - min(axis_vals) if axis_vals else 0.0
    center_band = min(max(1e-9, span * 1e-5), 5e-4)

    def on_center(v: bmesh.types.BMVert) -> bool:
        return abs(v.co[axis_index] - center) <= center_band

    side_tol = min(symmetry_tol, span * 1e-4 if span >
                   0 else symmetry_tol, 1e-3)

    def is_pos(v: bmesh.types.BMVert) -> bool:
        return v.co[axis_index] > center + side_tol

    def is_neg(v: bmesh.types.BMVert) -> bool:
        return v.co[axis_index] < center - side_tol

    reverse_map = {nv: pv for pv, nv in vert_map.items()}
    edge_by_pair: Dict[tuple[int, int], bmesh.types.BMEdge] = {}
    for _e in bm.edges:
        edge_by_pair[tuple(
            sorted((_e.verts[0].index, _e.verts[1].index)))] = _e

    def map_vert(v: bmesh.types.BMVert, from_positive: bool):
        if on_center(v):
            return v
        return vert_map.get(v) if from_positive else reverse_map.get(v)

    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    axis_vals = [v.co[axis_index] for v in bm.verts]
    span = max(axis_vals) - min(axis_vals) if axis_vals else 0.0
    center_band = min(max(1e-9, span * 1e-5), 5e-4)

    def on_center(v: bmesh.types.BMVert) -> bool:
        return abs(v.co[axis_index] - center) <= center_band

    side_tol = min(symmetry_tol, span * 1e-4 if span >
                   0 else symmetry_tol, 1e-3)

    def is_pos(v: bmesh.types.BMVert) -> bool:
        return v.co[axis_index] > center + side_tol

    def is_neg(v: bmesh.types.BMVert) -> bool:
        return v.co[axis_index] < center - side_tol

    reverse_map = {nv: pv for pv, nv in vert_map.items()}
    edge_by_pair: Dict[tuple[int, int], bmesh.types.BMEdge] = {}
    for _e in bm.edges:
        edge_by_pair[tuple(
            sorted((_e.verts[0].index, _e.verts[1].index)))] = _e

    def map_vert(v: bmesh.types.BMVert, from_positive: bool):
        if on_center(v):
            return v
        return vert_map.get(v) if from_positive else reverse_map.get(v)
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    # Precompute lookup for edges by unordered vert index pair
    edge_by_pair: Dict[tuple, bmesh.types.BMEdge] = {}
    for e in bm.edges:
        vs = tuple(sorted((e.verts[0].index, e.verts[1].index)))
        edge_by_pair[vs] = e

    def on_center(v):
        return abs(v.co[axis_index] - center) <= symmetry_tol

    # Track mirrored edges we explicitly ensured are seams (so pruning can distinguish)
    mirrored_kept = set()
    for e in bm.edges:
        v1, v2 = e.verts
        # Only propagate from positive side (or centerline) edges
        if v1.co[axis_index] < center - symmetry_tol and v2.co[axis_index] < center - symmetry_tol:
            continue
        if not e.seam:
            continue
        # Case 1: both vertices mapped (pure positive edge)
        if v1 in vert_map and v2 in vert_map:
            mv1 = vert_map[v1]
            mv2 = vert_map[v2]
            me = edge_by_pair.get(tuple(sorted((mv1.index, mv2.index))))
            if me:
                if not me.seam:
                    me.seam = True
                mirrored_kept.add(me)
            continue
        # Case 2: one mapped + one centerline vertex -> mirror to (mapped_mirror, centerline)
        if v1 in vert_map and on_center(v2):
            mv1 = vert_map[v1]
            # centerline v2 mirrors to itself
            me = edge_by_pair.get(tuple(sorted((mv1.index, v2.index))))
            if me:
                if not me.seam:
                    me.seam = True
                mirrored_kept.add(me)
            continue
        if v2 in vert_map and on_center(v1):
            mv2 = vert_map[v2]
            me = edge_by_pair.get(tuple(sorted((mv2.index, v1.index))))
            if me:
                if not me.seam:
                    me.seam = True
                mirrored_kept.add(me)

    if prune_extra:
        # Build reverse map: negative -> positive
        reverse_map = {nv: pv for pv, nv in vert_map.items()}
        for e in bm.edges:
            if not e.seam:
                continue
            v1, v2 = e.verts
            # Only consider edges that lie wholly or partially on negative side; skip positive side ones
            if v1.co[axis_index] >= center - symmetry_tol or v2.co[axis_index] >= center - symmetry_tol:
                # Edge touches positive side or centerline; source edge, never pruned
                continue
            # Edge fully negative side; find positive counterpart
            pv1 = reverse_map.get(v1)
            pv2 = reverse_map.get(v2)
            if pv1 is None or pv2 is None:
                # Cannot map -> ambiguous; skip pruning to be conservative
                continue
            pos_edge = edge_by_pair.get(tuple(sorted((pv1.index, pv2.index))))
            if not pos_edge or not pos_edge.seam:
                # Negative seam has no matching positive seam; remove
                e.seam = False


def symmetry_axis_letter(axis_index: int | None) -> str:
    return {0: 'X', 1: 'Y', 2: 'Z'}.get(axis_index, '')


def mirror_sync_seams(
    bm: bmesh.types.BMesh,
    axis_index: int,
    center: float,
    vert_map: Dict[bmesh.types.BMVert, bmesh.types.BMVert],
    symmetry_tol: float = 1e-6,
    additive: bool = False,
    source_positive: bool = True,
):
    """Synchronize seam edges across symmetry plane.

    additive=True  -> union both sides' seam flags (never clears seams)
    additive=False -> authoritative copy from source side (clears mismatches on target)
    source_positive selects authoritative side when copy mode.
    """
    if axis_index is None or not vert_map:
        return

    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    # Scale-aware narrow center band independent of user tol
    axis_vals = [v.co[axis_index] for v in bm.verts]
    span = max(axis_vals) - min(axis_vals) if axis_vals else 0.0
    center_band = min(max(1e-9, span * 1e-5), 5e-4)
    side_tol = min(symmetry_tol, span * 1e-4 if span >
                   0 else symmetry_tol, 1e-3)

    def on_center(v: bmesh.types.BMVert) -> bool:
        return abs(v.co[axis_index] - center) <= center_band

    def is_pos(v: bmesh.types.BMVert) -> bool:
        return v.co[axis_index] > center + side_tol

    def is_neg(v: bmesh.types.BMVert) -> bool:
        return v.co[axis_index] < center - side_tol

    reverse_map = {nv: pv for pv, nv in vert_map.items()}
    edge_by_pair: Dict[tuple[int, int], bmesh.types.BMEdge] = {}
    for _e in bm.edges:
        edge_by_pair[tuple(
            sorted((_e.verts[0].index, _e.verts[1].index)))] = _e

    def map_vert(v: bmesh.types.BMVert, from_positive: bool):
        if on_center(v):
            return v
        return vert_map.get(v) if from_positive else reverse_map.get(v)

    def counterpart_edge(e: bmesh.types.BMEdge, from_positive: bool):
        v1, v2 = e.verts
        mv1 = map_vert(v1, from_positive)
        mv2 = map_vert(v2, from_positive)
        if mv1 is None or mv2 is None:
            return None
        return edge_by_pair.get(tuple(sorted((mv1.index, mv2.index))))

    src_pos = source_positive

    if additive:
        # Union path – iterate edges on authoritative side only (skip centerline edges)
        for e in bm.edges:
            v1, v2 = e.verts
            any_pos = is_pos(v1) or is_pos(v2)
            any_neg = is_neg(v1) or is_neg(v2)
            if any_pos and any_neg:
                continue  # crossing edge (unlikely in clean symmetrical mesh)
            if on_center(v1) and on_center(v2):
                continue
            # filter to authoritative side
            if src_pos:
                if any_neg or not any_pos:
                    continue
            else:
                if any_pos or not any_neg:
                    continue
            mate = counterpart_edge(e, src_pos)
            if mate and mate is not e and (e.seam or mate.seam):
                e.seam = True
                mate.seam = True
        return

    # Copy mode: Phase 1 – propagate authoratitive seams over
    for e in bm.edges:
        v1, v2 = e.verts
        any_pos = is_pos(v1) or is_pos(v2)
        any_neg = is_neg(v1) or is_neg(v2)
        if any_pos and any_neg:
            continue
        if on_center(v1) and on_center(v2):
            continue
        if src_pos:
            if any_neg or not any_pos:
                continue
        else:
            if any_pos or not any_neg:
                continue
        mate = counterpart_edge(e, src_pos)
        if mate and mate is not e:
            mate.seam = e.seam

    # Phase 2 – enforce equality (clear target mismatches)
    for e in bm.edges:
        v1, v2 = e.verts
        any_pos = is_pos(v1) or is_pos(v2)
        any_neg = is_neg(v1) or is_neg(v2)
        if any_pos and any_neg:
            continue
        if on_center(v1) and on_center(v2):
            continue
        target_side = (src_pos and any_neg) or ((not src_pos) and any_pos)
        if not target_side:
            continue
        mate = counterpart_edge(e, not src_pos)
        if mate:
            e.seam = mate.seam


# Backwards compatibility alias (older code may call copy_mirrored_seams)
def copy_mirrored_seams(*args, **kwargs):  # pragma: no cover
    return mirror_sync_seams(*args, **kwargs)

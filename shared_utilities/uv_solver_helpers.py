import bpy
import bmesh
from mathutils import Vector, Matrix
from typing import Dict, List, Set, Tuple
import math


def compute_inverse_distance_weights(bm: bmesh.types.BMesh,
                                     uv_layer,
                                     axis: str = None,
                                     matrix_world: Matrix = None) -> Dict[int, List[Tuple[int, float]]]:
    """Compute inverse distance weights for UV Laplacian smoothing.

    Returns a dict mapping loop index -> list of (neighbor_loop_index, weight).
    Inverse distance weights are robust and reduce stretching.
    If axis is provided ('U' or 'V'), weights are modulated by edge alignment
    to that axis in UV space to prevent orthogonal edges from locking relaxation.
    """
    weights: Dict[int, List[Tuple[int, float]]] = {}

    axis_idx = 0 if axis == 'U' else 1

    for face in bm.faces:
        if not face.select:
            continue

        loops = list(face.loops)
        n = len(loops)

        for i, loop in enumerate(loops):
            loop_idx = loop.index
            if loop_idx not in weights:
                weights[loop_idx] = []

            # Get prev and next loops in this face
            next_loop = loops[(i + 1) % n]
            prev_loop = loops[(i - 1) % n]

            # Get coordinates (World or Local)
            p_curr = loop.vert.co
            p_next = next_loop.vert.co
            p_prev = prev_loop.vert.co

            if matrix_world:
                p_curr = matrix_world @ p_curr
                p_next = matrix_world @ p_next
                p_prev = matrix_world @ p_prev

            # Distance in 3D space
            dist_next = (p_curr - p_next).length
            dist_prev = (p_curr - p_prev).length

            # Base weight: Inverse distance
            w_next = 1.0 / max(1e-6, dist_next)
            w_prev = 1.0 / max(1e-6, dist_prev)

            # Directional modulation if axis specified
            if axis:
                uv_curr = loop[uv_layer].uv
                uv_next = next_loop[uv_layer].uv
                uv_prev = prev_loop[uv_layer].uv

                # Vector in UV space
                d_uv_next = uv_next - uv_curr
                d_uv_prev = uv_prev - uv_curr

                len_next = d_uv_next.length
                len_prev = d_uv_prev.length

                # Alignment factor: |cos(theta)|
                # If edge is parallel to relaxation axis, factor is 1.0
                # If edge is perpendicular, factor is 0.0 (or small epsilon)

                align_next = 1.0
                if len_next > 1e-6:
                    align_next = abs(d_uv_next[axis_idx]) / len_next

                align_prev = 1.0
                if len_prev > 1e-6:
                    align_prev = abs(d_uv_prev[axis_idx]) / len_prev

                # Soften the alignment to keep some coupling
                # 0.1 base + 0.9 * alignment
                w_next *= (0.1 + 0.9 * align_next)
                w_prev *= (0.1 + 0.9 * align_prev)

            # Add directed edge weights
            weights[loop_idx].append((next_loop.index, w_next))
            weights[loop_idx].append((prev_loop.index, w_prev))

    return weights


def get_boundary_loop_indices(bm: bmesh.types.BMesh,
                              uv_layer) -> Set[int]:
    """Get loop indices that are on UV island boundaries.

    These loops should be pinned (not moved) during relaxation.
    """
    boundary_loops: Set[int] = set()

    for edge in bm.edges:
        link_faces = [f for f in edge.link_faces if f.select]

        # Mesh boundary within selection
        if len(link_faces) == 1:
            for loop in link_faces[0].loops:
                if loop.vert in edge.verts:
                    boundary_loops.add(loop.index)
            continue

        if len(link_faces) < 2:
            continue

        # Check for UV discontinuity
        uv_at_vert: Dict[int, List[Vector]] = {}
        for face in link_faces:
            for loop in face.loops:
                if loop.vert in edge.verts:
                    uv = loop[uv_layer].uv.copy()
                    vert_idx = loop.vert.index
                    if vert_idx not in uv_at_vert:
                        uv_at_vert[vert_idx] = []
                    uv_at_vert[vert_idx].append((loop.index, uv))

        # If UVs differ at same vertex, it's a seam
        for vert_idx, uv_list in uv_at_vert.items():
            if len(uv_list) > 1:
                first_uv = uv_list[0][1]
                for loop_idx, uv in uv_list[1:]:
                    if (first_uv - uv).length > 1e-5:
                        for li, _ in uv_list:
                            boundary_loops.add(li)
                        break

    return boundary_loops


def build_uv_adjacency(bm: bmesh.types.BMesh,
                       uv_layer) -> Tuple[Dict[Tuple[int, int], Set[int]],
                                          Dict[int, Set[int]],
                                          Dict[int, Tuple[int, int]]]:
    """Build adjacency for UV loops within selected faces.

    Loops are considered connected if they share the same UV position
    (welded UV vertices). This properly handles multi-face UV islands.

    Returns:
        Tuple of (uv_to_loops, edge_adjacency, loop_to_uv_key):
        - uv_to_loops: maps quantized UV key -> set of all loop indices at that UV position
        - edge_adjacency: maps loop index -> set of neighbor loop indices (via face edges)
        - loop_to_uv_key: maps loop index -> its quantized UV key
    """
    # Group loops by their UV position (within tolerance)
    # Use a tolerance-based grouping for floating point UV coords
    uv_to_loops: Dict[Tuple[int, int], Set[int]] = {}
    loop_to_uv_key: Dict[int, Tuple[int, int]] = {}

    # Quantization factor (5 decimal places = 0.00001 precision)
    QUANT = 100000

    for face in bm.faces:
        if not face.select:
            continue
        for loop in face.loops:
            uv = loop[uv_layer].uv
            # Quantize UV to group nearby UVs
            key = (round(uv.x * QUANT), round(uv.y * QUANT))
            if key not in uv_to_loops:
                uv_to_loops[key] = set()
            uv_to_loops[key].add(loop.index)
            loop_to_uv_key[loop.index] = key

    # Build edge adjacency from face topology
    # For each loop, find adjacent loops (prev/next in face)
    edge_adjacency: Dict[int, Set[int]] = {}

    for face in bm.faces:
        if not face.select:
            continue
        loops = list(face.loops)
        n = len(loops)
        for i, loop in enumerate(loops):
            if loop.index not in edge_adjacency:
                edge_adjacency[loop.index] = set()
            # Adjacent loops in face (via edges)
            prev_loop = loops[(i - 1) % n]
            next_loop = loops[(i + 1) % n]
            edge_adjacency[loop.index].add(prev_loop.index)
            edge_adjacency[loop.index].add(next_loop.index)

    # Now build unified adjacency that respects UV welding
    # For each loop, its neighbors are:
    # 1. All loops sharing the same UV position (they move together)
    # 2. Edge neighbors of any loop in the same UV group
    unified_adjacency: Dict[int, Set[int]] = {}

    for loop_idx in loop_to_uv_key:
        uv_key = loop_to_uv_key[loop_idx]
        same_uv_loops = uv_to_loops[uv_key]

        # Collect all edge neighbors from all loops at this UV position
        all_edge_neighbors: Set[int] = set()
        for co_loop_idx in same_uv_loops:
            if co_loop_idx in edge_adjacency:
                all_edge_neighbors.update(edge_adjacency[co_loop_idx])

        # Remove self-group loops from edge neighbors
        all_edge_neighbors -= same_uv_loops

        # Map edge neighbors to their UV group representatives
        # (all loops at same UV position should get same neighbor set)
        neighbor_uv_keys: Set[Tuple[int, int]] = set()
        for neighbor_idx in all_edge_neighbors:
            if neighbor_idx in loop_to_uv_key:
                neighbor_uv_keys.add(loop_to_uv_key[neighbor_idx])

        # Store: this loop's neighbors are represented by one loop per UV group
        unified_adjacency[loop_idx] = all_edge_neighbors

    return uv_to_loops, unified_adjacency, loop_to_uv_key


def compute_ideal_relax_vectors(bm: bmesh.types.BMesh,
                                uv_layer,
                                axis: str,
                                matrix_world: Matrix = None) -> Dict[bmesh.types.BMFace, Vector]:
    """Compute the ideal 3D direction vector for the relaxation axis for each face.

    This is derived from the gradient of the CONSTRAINED axis.
    If we relax U, we keep V fixed. The direction of U should be orthogonal to the gradient of V.
    Ideal_U = Cross(FaceNormal, Gradient_V).

    Returns:
        Dict mapping Face -> 3D Vector (normalized)
    """
    face_vectors: Dict[bmesh.types.BMFace, Vector] = {}
    const_axis_idx = 1 if axis == 'U' else 0

    # First pass: Compute vectors for faces with non-degenerate constrained axis
    for face in bm.faces:
        if not face.select:
            continue

        # Need at least 3 points to compute gradient
        if len(face.verts) < 3:
            continue

        # Get 3D positions and Constrained UV values
        # We use the first 3 vertices of the face (triangulation assumption)
        # For better accuracy on quads, we could average, but first triangle is usually sufficient for direction.

        loops = face.loops
        p0 = loops[0].vert.co
        p1 = loops[1].vert.co
        p2 = loops[2].vert.co

        if matrix_world:
            p0 = matrix_world @ p0
            p1 = matrix_world @ p1
            p2 = matrix_world @ p2

        uv0 = loops[0][uv_layer].uv[const_axis_idx]
        uv1 = loops[1][uv_layer].uv[const_axis_idx]
        uv2 = loops[2][uv_layer].uv[const_axis_idx]

        v1 = p1 - p0
        v2 = p2 - p0
        normal = v1.cross(v2)

        if normal.length_squared < 1e-8:
            continue

        dc1 = uv1 - uv0
        dc2 = uv2 - uv0

        # Gradient of Constrained Axis (unnormalized)
        # Formula derived from linear interpolation on triangle
        grad_const = (v2 * dc1 - v1 * dc2).cross(normal)

        # Now compute Ideal Relax Direction
        if axis == 'U':  # Relax U, Const V
            # Ideal U = Grad V x Normal
            # Grad V is grad_const
            ideal_relax = grad_const.cross(normal)
        else:  # Relax V, Const U
            # Ideal V = Normal x Grad U
            # Grad U is grad_const
            ideal_relax = normal.cross(grad_const)

        if ideal_relax.length_squared > 1e-8:
            ideal_relax.normalize()
            face_vectors[face] = ideal_relax

    # Second pass: Fill in missing faces (constant constrained axis faces) by propagating
    # This handles the "perpendicular to projection" faces where constrained axis is constant.

    # Simple iterative propagation
    missing_faces = [f for f in bm.faces if f.select and f not in face_vectors]

    if missing_faces:
        # Build face adjacency
        face_adj: Dict[bmesh.types.BMFace, List[bmesh.types.BMFace]] = {}
        for face in bm.faces:
            if not face.select:
                continue
            face_adj[face] = []
            for edge in face.edges:
                for link_face in edge.link_faces:
                    if link_face != face and link_face.select:
                        face_adj[face].append(link_face)

        # Propagate
        changed = True
        while changed and missing_faces:
            changed = False
            remaining = []
            for face in missing_faces:
                # Average of valid neighbors
                avg_vec = Vector((0.0, 0.0, 0.0))
                count = 0
                for neighbor in face_adj.get(face, []):
                    if neighbor in face_vectors:
                        avg_vec += face_vectors[neighbor]
                        count += 1

                if count > 0:
                    avg_vec.normalize()
                    face_vectors[face] = avg_vec
                    changed = True
                else:
                    remaining.append(face)
            missing_faces = remaining

    return face_vectors


def apply_laplacian_smoothing(bm: bmesh.types.BMesh,
                              uv_layer,
                              iterations: int,
                              strength: float,
                              pinned_uv_keys: Set[Tuple[int, int]] = None,
                              uv_to_loops: Dict[Tuple[int,
                                                      int], Set[int]] = None,
                              loop_by_idx: Dict[int,
                                                bmesh.types.BMLoop] = None,
                              edge_data: List[Tuple[Tuple[int, int],
                                                    Tuple[int, int], float]] = None,
                              axis: str = None) -> None:
    """Apply Laplacian smoothing to UVs.

    Args:
        bm: BMesh
        uv_layer: UV layer
        iterations: Number of iterations
        strength: Smoothing strength (0-1)
        pinned_uv_keys: Set of UV keys to keep fixed
        uv_to_loops: Pre-computed UV adjacency (optional, will build if None)
        loop_by_idx: Pre-computed loop lookup (optional)
        edge_data: Pre-computed edge data (optional, used for adjacency)
        axis: If 'U' or 'V', only smooth along that axis. If None, smooth both.
    """
    if iterations <= 0 or strength <= 0:
        return

    if uv_to_loops is None:
        uv_to_loops, _, loop_to_uv_key = build_uv_adjacency(bm, uv_layer)

    # Need loop_by_idx if not provided
    if loop_by_idx is None:
        loop_by_idx = {l.index: l for f in bm.faces for l in f.loops}

    if pinned_uv_keys is None:
        pinned_uv_keys = set()

    # Helper to get current UV value
    def get_uv(uv_key: Tuple[int, int]) -> Vector:
        loops_at_key = uv_to_loops.get(uv_key)
        if loops_at_key:
            rep_loop = loop_by_idx.get(next(iter(loops_at_key)))
            if rep_loop:
                return rep_loop[uv_layer].uv.copy()
        return Vector((0.0, 0.0))

    # Helper to set UV value
    def set_uv(uv_key: Tuple[int, int], val: Vector):
        loops_at_key = uv_to_loops.get(uv_key)
        if loops_at_key:
            for loop_idx in loops_at_key:
                loop = loop_by_idx.get(loop_idx)
                if loop:
                    uv = loop[uv_layer].uv
                    if axis == 'U':
                        uv.x = val.x
                    elif axis == 'V':
                        uv.y = val.y
                    else:
                        uv.x = val.x
                        uv.y = val.y

    # Build adjacency list for Laplacian
    adj_list: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}

    if edge_data:
        # Use provided edge data (faster if already computed)
        for uv_key_a, uv_key_b, _ in edge_data:
            if uv_key_a not in adj_list:
                adj_list[uv_key_a] = []
            if uv_key_b not in adj_list:
                adj_list[uv_key_b] = []
            adj_list[uv_key_a].append(uv_key_b)
            adj_list[uv_key_b].append(uv_key_a)
    else:
        # Build from mesh topology
        # This is a simplified version, ideally we use the build_uv_adjacency output
        # But for now let's iterate edges
        _, unified_adjacency, loop_to_uv_key = build_uv_adjacency(bm, uv_layer)
        for loop_idx, neighbors in unified_adjacency.items():
            uv_key = loop_to_uv_key[loop_idx]
            if uv_key not in adj_list:
                adj_list[uv_key] = []

            for n_idx in neighbors:
                if n_idx in loop_to_uv_key:
                    n_key = loop_to_uv_key[n_idx]
                    if n_key != uv_key:  # Avoid self-loops
                        # Check if already added to avoid duplicates?
                        # List might have duplicates if multiple edges connect same UVs.
                        # Set is better.
                        pass

            # Actually, unified_adjacency gives loop neighbors. We want UV key neighbors.
            # Let's use a set to collect unique neighbor keys
            neighbor_keys = set()
            for n_idx in neighbors:
                if n_idx in loop_to_uv_key:
                    neighbor_keys.add(loop_to_uv_key[n_idx])

            adj_list[uv_key] = list(neighbor_keys)

    for _ in range(iterations):
        laplacian_forces: Dict[Tuple[int, int], Vector] = {}
        for uv_key, neighbors in adj_list.items():
            if uv_key in pinned_uv_keys:
                continue
            if not neighbors:
                continue

            # Calculate average position of neighbors
            avg_pos = Vector((0.0, 0.0))
            for n_key in neighbors:
                avg_pos += get_uv(n_key)
            avg_pos /= len(neighbors)

            current_pos = get_uv(uv_key)
            # Move towards average
            laplacian_forces[uv_key] = (avg_pos - current_pos) * strength

        # Apply Laplacian
        for uv_key, force in laplacian_forces.items():
            current = get_uv(uv_key)
            set_uv(uv_key, current + force)


def relax_uvs_axis_constrained(bm: bmesh.types.BMesh,
                               uv_layer,
                               axis: str,
                               iterations: int,
                               strength: float,
                               pin_boundary: bool,
                               laplacian_iterations: int = 10,
                               laplacian_strength: float = 0.5,
                               matrix_world: Matrix = None) -> int:
    """Perform axis-constrained UV relaxation using Geometric PBD.

    Uses a Position Based Dynamics (PBD) approach where each edge tries to
    maintain its 3D world-space length by adjusting its length along the
    relaxation axis, while respecting the fixed length along the constrained axis.
    This prevents skewing/shearing artifacts common in simple spring models.

    Args:
        bm: BMesh to operate on
        uv_layer: Active UV layer
        axis: 'U' or 'V' - which axis to relax along
        iterations: Number of relaxation iterations
        strength: Relaxation strength per iteration (0-1)
        pin_boundary: If True, don't move UV island boundary loops
        laplacian_iterations: Number of pre-pass Laplacian smoothing iterations
        laplacian_strength: Strength of Laplacian smoothing (0-1)
        matrix_world: Object world matrix for correct distance calculation

    Returns:
        Number of loops processed
    """
    # Collect selected face loops and build index lookup
    selected_loops: List[bmesh.types.BMLoop] = []
    loop_by_idx: Dict[int, bmesh.types.BMLoop] = {}

    # Pre-calculate bounds for scale preservation
    min_u, max_u = float('inf'), float('-inf')
    min_v, max_v = float('inf'), float('-inf')

    for face in bm.faces:
        if face.select:
            for loop in face.loops:
                selected_loops.append(loop)
                loop_by_idx[loop.index] = loop

                uv = loop[uv_layer].uv
                min_u = min(min_u, uv.x)
                max_u = max(max_u, uv.x)
                min_v = min(min_v, uv.y)
                max_v = max(max_v, uv.y)

    if not selected_loops:
        return 0

    width_old = max_u - min_u
    height_old = max_v - min_v
    longest_axis_len = max(width_old, height_old)

    # Determine which component to modify
    axis_idx = 0 if axis == 'U' else 1

    # Check if the UVs are degenerate along the relaxation axis
    axis_extent = width_old if axis == 'U' else height_old
    is_degenerate = axis_extent < 1e-4

    # Build adjacency with UV welding awareness
    uv_to_loops, adjacency, loop_to_uv_key = build_uv_adjacency(bm, uv_layer)

    # Build edge data with target lengths
    # For each UV vertex pair connected by an edge, store:
    # - The target length along the relaxation axis (derived from 3D length)
    # - A consistent direction based on the UV key ordering (not UV positions)

    # First, compute a global scale factor: UV units per world unit
    # We use a weighted approach that favors edges aligned with the CONSTRAINED axis.
    # This ensures that if the relaxation axis is collapsed (length 0), we still
    # derive the correct scale from the axis that is intact.

    # Constrained axis index (the one we are NOT relaxing)
    const_axis_idx = 1 if axis == 'U' else 0

    sum_delta_const = 0.0
    sum_weighted_3d = 0.0

    # Fallback accumulators in case everything is collapsed
    total_3d_length = 0.0
    total_uv_length = 0.0

    # edge_data stores: (uv_key_a, uv_key_b, target_3d_len)
    # Direction will be determined by consistent UV key ordering
    edge_data: List[Tuple[Tuple[int, int], Tuple[int, int], float]] = []
    processed_edge_pairs: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

    for face in bm.faces:
        if not face.select:
            continue

        loops = list(face.loops)
        n = len(loops)

        for i, loop in enumerate(loops):
            next_loop = loops[(i + 1) % n]

            uv_key_a = loop_to_uv_key.get(loop.index)
            uv_key_b = loop_to_uv_key.get(next_loop.index)

            if uv_key_a is None or uv_key_b is None:
                continue
            if uv_key_a == uv_key_b:
                continue

            # Normalize edge pair ordering to avoid duplicates
            # Always store with smaller key first for consistency
            if uv_key_a < uv_key_b:
                edge_pair = (uv_key_a, uv_key_b)
            else:
                edge_pair = (uv_key_b, uv_key_a)

            if edge_pair in processed_edge_pairs:
                continue
            processed_edge_pairs.add(edge_pair)

            # Compute 3D edge length
            p_a = loop.vert.co
            p_b = next_loop.vert.co
            if matrix_world:
                p_a = matrix_world @ p_a
                p_b = matrix_world @ p_b

            edge_3d_len = (p_b - p_a).length

            # Get UV positions for scale calculation
            uv_a = loop[uv_layer].uv
            uv_b = next_loop[uv_layer].uv

            edge_uv_len = (uv_b - uv_a).length
            delta_const = abs(uv_b[const_axis_idx] - uv_a[const_axis_idx])

            # Accumulate for fallback
            total_3d_length += edge_3d_len
            total_uv_length += edge_uv_len

            # Accumulate for weighted scale
            # Weight = delta_const / edge_uv_len (projection factor onto constrained axis)
            # Contribution to UV sum = edge_uv_len * Weight = delta_const
            # Contribution to 3D sum = edge_3d_len * Weight

            if edge_uv_len > 1e-6:
                weight = delta_const / edge_uv_len
                # Square the weight to strongly favor aligned edges?
                # Linear seems safer to avoid ignoring slightly rotated edges too much.
                # Let's stick to linear projection.

                sum_delta_const += delta_const
                sum_weighted_3d += edge_3d_len * weight

            # Store with consistent ordering (smaller key first)
            edge_data.append(edge_pair + (edge_3d_len,))

    if total_3d_length < 1e-9:
        return 0

    # Compute scale: UV units per 3D unit
    # Prefer the weighted scale derived from the constrained axis
    if sum_weighted_3d > 1e-9:
        uv_per_3d = sum_delta_const / sum_weighted_3d
    else:
        # Fallback: if no edges have significant extent on constrained axis
        # (e.g. a strip collapsed to a line on the relaxation axis), use global average
        uv_per_3d = total_uv_length / total_3d_length if total_3d_length > 1e-9 else 1.0

    # Safety clamp if scale is absurdly small (e.g. fully collapsed mesh)
    if uv_per_3d < 1e-6:
        uv_per_3d = 1.0  # Default to world scale if we can't determine anything

    # Get boundary loops to pin
    boundary_loops = get_boundary_loop_indices(
        bm, uv_layer) if pin_boundary else set()

    # Determine which UV groups are pinned
    pinned_uv_keys: Set[Tuple[int, int]] = set()
    for loop_idx in boundary_loops:
        if loop_idx in loop_to_uv_key:
            pinned_uv_keys.add(loop_to_uv_key[loop_idx])

    # Helper to get current UV value for a UV key
    def get_uv_val(uv_key: Tuple[int, int]) -> float:
        loops_at_key = uv_to_loops.get(uv_key)
        if loops_at_key:
            rep_loop = loop_by_idx.get(next(iter(loops_at_key)))
            if rep_loop:
                return rep_loop[uv_layer].uv[axis_idx]
        return 0.0

    # Helper to set UV value for all loops at a UV key
    def set_uv_val(uv_key: Tuple[int, int], val: float):
        loops_at_key = uv_to_loops.get(uv_key)
        if loops_at_key:
            for loop_idx in loops_at_key:
                loop = loop_by_idx.get(loop_idx)
                if loop:
                    uv = loop[uv_layer].uv
                    if axis_idx == 0:
                        uv.x = val
                    else:
                        uv.y = val

    # Compute Ideal Relax Vectors (Local Tangent Flow)
    # This gives us the "correct" 3D direction for the relaxation axis for each face,
    # derived from the fixed constrained axis.
    face_tangents = compute_ideal_relax_vectors(
        bm, uv_layer, axis, matrix_world)

    # Phase 1: Laplacian Smoothing (Untangling)
    # Run a few iterations of pure Laplacian smoothing to separate coincident vertices
    # and untangle folds before applying strict length constraints.
    # This is crucial for zero-area faces where PBD direction is ambiguous.

    if laplacian_iterations > 0:
        apply_laplacian_smoothing(
            bm, uv_layer, laplacian_iterations, laplacian_strength,
            pinned_uv_keys=pinned_uv_keys,
            uv_to_loops=uv_to_loops,
            loop_by_idx=loop_by_idx,
            edge_data=edge_data,
            axis=axis  # Only smooth along the relaxation axis
        )

    # Phase 2: Geometric PBD (Metric Fix)
    for _ in range(iterations):
        # Accumulate forces on each UV vertex
        forces: Dict[Tuple[int, int], float] = {}

        for uv_key_a, uv_key_b, edge_3d_len in edge_data:
            # Target total 2D length for this edge
            target_total_len = edge_3d_len * uv_per_3d

            # Get current positions
            val_a_relax = get_uv_val(uv_key_a)
            val_b_relax = get_uv_val(uv_key_b)

            # Get positions on the constrained axis (these are fixed/constant for this operation)
            # We need to look up the actual UV values for the constrained axis
            # Since we only stored 'val' (relax axis) in get_uv_val, we need to access the full UV
            # But wait, get_uv_val only returns the relax axis value.
            # We need to read the constrained axis value from the mesh.
            # Since we don't modify the constrained axis, we can read it once or read it here.
            # Let's read it from the representative loop.

            loops_a = uv_to_loops.get(uv_key_a)
            loops_b = uv_to_loops.get(uv_key_b)

            if not loops_a or not loops_b:
                continue

            loop_a = loop_by_idx.get(next(iter(loops_a)))
            loop_b = loop_by_idx.get(next(iter(loops_b)))

            if not loop_a or not loop_b:
                continue

            # Constrained axis index (the one we are NOT relaxing)
            const_axis_idx = 1 if axis == 'U' else 0

            const_val_a = loop_a[uv_layer].uv[const_axis_idx]
            const_val_b = loop_b[uv_layer].uv[const_axis_idx]

            delta_const = abs(const_val_b - const_val_a)

            # Calculate target delta for the relax axis using Pythagorean theorem
            # target_total_len^2 = delta_relax^2 + delta_const^2
            # delta_relax = sqrt(target_total_len^2 - delta_const^2)

            if target_total_len > delta_const:
                target_delta_relax = math.sqrt(
                    target_total_len**2 - delta_const**2)
            else:
                # Edge is too short to span the constrained gap; best we can do is 0 (vertical/horizontal line)
                target_delta_relax = 0.0

            # Current signed distance on relax axis
            current_delta_raw = val_b_relax - val_a_relax

            # Determine direction to apply correction
            # Use the Local Tangent Flow (Ideal U Vector) to determine direction
            # This is robust against reversals and zero-area faces

            # Get face for this edge (use loop_a's face)
            face = loop_a.face
            ideal_tangent = face_tangents.get(face)

            # If we don't have a tangent (e.g. isolated degenerate face), fallback to current delta
            if ideal_tangent:
                # Calculate 3D edge vector
                p_a = loop_a.vert.co
                p_b = loop_b.vert.co
                if matrix_world:
                    p_a = matrix_world @ p_a
                    p_b = matrix_world @ p_b
                vec_3d = p_b - p_a

                dot = vec_3d.dot(ideal_tangent)

                # If dot is near zero, the edge is perpendicular to the flow (vertical edge)
                # In this case, direction doesn't matter much as target_delta_relax should be small/zero
                # But if target_delta_relax is large (e.g. zero area face), we need a direction.
                # If dot is 0, it means this edge shouldn't have any U-length.

                if abs(dot) < 1e-6:
                    # Edge is perpendicular to U-flow. It should be vertical.
                    # Force target delta to 0?
                    # If the edge is truly vertical in 3D relative to U-flow, then yes.
                    # But let's trust the Pythagorean calc for magnitude, and just use current sign as fallback.
                    direction = 1.0 if current_delta_raw >= 0 else -1.0
                else:
                    direction = 1.0 if dot > 0 else -1.0
            else:
                # Fallback
                direction = 1.0 if current_delta_raw >= 0 else -1.0

            current_sign = direction

            # We want the new delta to be: target_delta_relax * current_sign
            target_val_diff = target_delta_relax * current_sign

            # Error = Target - Current
            # If we want delta to be 5, and it is 3, error is +2. We need to push B +1 and A -1.
            diff = target_val_diff - current_delta_raw

            move_amount = diff * 0.5 * strength

            if uv_key_a not in pinned_uv_keys:
                if uv_key_a not in forces:
                    forces[uv_key_a] = 0.0
                # Move A opposite to increase gap
                forces[uv_key_a] -= move_amount

            if uv_key_b not in pinned_uv_keys:
                if uv_key_b not in forces:
                    forces[uv_key_b] = 0.0
                forces[uv_key_b] += move_amount  # Move B along to increase gap

        # Apply accumulated forces
        for uv_key, force in forces.items():
            if uv_key in pinned_uv_keys:
                continue
            current_val = get_uv_val(uv_key)
            new_val = current_val + force
            set_uv_val(uv_key, new_val)

    return len(selected_loops)

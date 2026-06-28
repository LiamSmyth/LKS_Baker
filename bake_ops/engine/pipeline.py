"""High-level curvature map generation (multi-method batch)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .bake_context import context_to_input, load_bake_context
from .device import resolve_registry_device
from .orchestrator import BakeEngine, BakeRequest
from .settings.curvature_settings import Backend, CurvatureSettings
from .static_utilities.images import save_gray01
from .static_utilities.mesh_data import MeshData


@dataclass(frozen=True)
class MethodBackends:
    """Per-method execution backend ('cpu' = cpu-only, 'gpu' = uses GPU at any point)."""

    tangent: str
    world: str
    mesh: str | None = None
    dihedral: str | None = None
    tangent_mesh: str | None = None

    @property
    def summary(self) -> str:
        """Summary.

        Returns:
            ``str`` result.
        """
        values = (self.tangent, self.world, self.mesh, self.dihedral, self.tangent_mesh)
        return "gpu" if any(v == "gpu" for v in values if v) else "cpu"


@dataclass
class CurvatureOutputs:
    """All curvature method outputs from ``generate_curvature_maps``.

    Attributes:
        valid: H×W bool coverage mask from loaded bake textures.
        island_id: H×W int32 UV island labels.
        method_tangent: Packed tangent-divergence curvature.
        method_world: Packed world-divergence curvature.
        method_mesh: Optional mesh Laplacian packed map when ``mesh_data`` supplied.
        method_dihedral: Optional dihedral-edges packed map when mesh supplied.
        method_tangent_mesh: Optional tangent/mesh blend when mesh supplied.
        signed_tangent: Signed tangent divergence before packing.
        signed_world: Signed world divergence before packing.
        signed_mesh: Optional signed mesh Laplacian before packing.
        method_backends: Per-method ``"cpu"``/``"gpu"`` device actually used.
    """

    valid: np.ndarray
    island_id: np.ndarray
    method_tangent: np.ndarray
    method_world: np.ndarray
    method_mesh: np.ndarray | None
    method_dihedral: np.ndarray | None
    method_tangent_mesh: np.ndarray | None
    signed_tangent: np.ndarray
    signed_world: np.ndarray
    signed_mesh: np.ndarray | None
    method_backends: MethodBackends

    @property
    def backend_used(self) -> str:
        """Summary backend for legacy callers."""
        return self.method_backends.summary


def generate_curvature_maps(
    bake_dir: str | Path,
    settings: CurvatureSettings | None = None,
    *,
    mesh_data: MeshData | None = None,
) -> CurvatureOutputs:
    """Run standard curvature methods against exported bake textures.

    Args:
        bake_dir: Directory with at least a tangent normal map export.
        settings: Optional lab settings; defaults to ``CurvatureSettings()``.
        mesh_data: When provided, also runs mesh Laplacian, dihedral, and tangent/mesh blend on CPU.

    Returns:
        ``CurvatureOutputs`` with packed maps, signed fields, masks, and per-method backends.
    """
    settings = settings or CurvatureSettings()
    ctx = load_bake_context(bake_dir, settings)
    texture_device = resolve_registry_device(settings.backend)
    inputs = context_to_input(ctx, settings, mesh=mesh_data)

    engine = BakeEngine()
    tangent = engine.bake(
        BakeRequest(
            map_type="curvature",
            method_id="tangent_divergence",
            device=texture_device,
            inputs=inputs,
        )
    )
    world = engine.bake(
        BakeRequest(
            map_type="curvature",
            method_id="world_divergence",
            device=texture_device,
            inputs=inputs,
        )
    )

    method_mesh = None
    method_dihedral = None
    method_tangent_mesh = None
    signed_mesh = None

    if mesh_data is not None:
        mesh_out = engine.bake(
            BakeRequest(
                map_type="curvature",
                method_id="mesh_laplacian",
                device="cpu",
                inputs=inputs,
            )
        )
        method_mesh = mesh_out.output.packed
        signed_mesh = mesh_out.output.signed

        edge_out = engine.bake(
            BakeRequest(
                map_type="curvature",
                method_id="dihedral_edges",
                device="cpu",
                inputs=inputs,
            )
        )
        method_dihedral = edge_out.output.packed

        blend_out = engine.bake(
            BakeRequest(
                map_type="curvature",
                method_id="tangent_mesh_blend",
                device="cpu",
                inputs=inputs,
            )
        )
        method_tangent_mesh = blend_out.output.packed

    method_backends = MethodBackends(
        tangent=tangent.device,
        world=world.device,
        mesh="cpu" if method_mesh is not None else None,
        dihedral="cpu" if method_dihedral is not None else None,
        tangent_mesh="cpu" if method_tangent_mesh is not None else None,
    )

    return CurvatureOutputs(
        valid=ctx.valid,
        island_id=ctx.island_id,
        method_tangent=tangent.output.packed,
        method_world=world.output.packed,
        method_mesh=method_mesh,
        method_dihedral=method_dihedral,
        method_tangent_mesh=method_tangent_mesh,
        signed_tangent=tangent.output.signed,
        signed_world=world.output.signed,
        signed_mesh=signed_mesh,
        method_backends=method_backends,
    )


def write_outputs(outputs: CurvatureOutputs, out_dir: str | Path, *, prefix: str = "") -> None:
    """Write packed curvature PNGs named ``{prefix}{method}_{device}.png``.

    Args:
        outputs: Result bundle from ``generate_curvature_maps``.
        out_dir: Destination directory (created if missing).
        prefix: Optional filename prefix for batch exports.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    backends = outputs.method_backends

    save_gray01(
        out_dir / f"{prefix}tangent_divergence_{backends.tangent}.png",
        outputs.method_tangent,
    )
    save_gray01(
        out_dir / f"{prefix}world_divergence_{backends.world}.png",
        outputs.method_world,
    )

    if outputs.method_mesh is not None and backends.mesh:
        save_gray01(
            out_dir / f"{prefix}mesh_laplacian_{backends.mesh}.png",
            outputs.method_mesh,
        )
    if outputs.method_dihedral is not None and backends.dihedral:
        save_gray01(
            out_dir / f"{prefix}dihedral_edges_{backends.dihedral}.png",
            outputs.method_dihedral,
        )
    if outputs.method_tangent_mesh is not None and backends.tangent_mesh:
        save_gray01(
            out_dir / f"{prefix}tangent_mesh_blend_{backends.tangent_mesh}.png",
            outputs.method_tangent_mesh,
        )

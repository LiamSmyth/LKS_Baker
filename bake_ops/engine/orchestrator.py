"""Bake engine entry point for orchestrators."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .bake_context import BakeContext, context_to_input, load_bake_context
from .bake_map import BakeMapInput, BakeMapOutput
from .registry import resolve_bake_map
from .settings.curvature_settings import Backend, CurvatureSettings
from .static_utilities.debug_texels import resolve_coverage_mask, settings_debug_texel_fail


@dataclass
class BakeRequest:
    """Single bake invocation parameters for ``BakeEngine``.

    Attributes:
        map_type: Catalog map family (e.g. ``"curvature"``).
        method_id: Implementation id within ``map_type``.
        device: ``"cpu"``, ``"gpu"``, or ``Backend.AUTO``.
        bake_dir: Optional texture directory when ``inputs`` is omitted.
        inputs: Pre-built ``BakeMapInput``; overrides ``bake_dir`` when set.
        settings: Curvature/AO settings merged into inputs before bake.
    """

    map_type: str = "curvature"
    method_id: str = "soft_curvature"
    device: str | Backend = Backend.AUTO
    bake_dir: str | None = None
    inputs: BakeMapInput | None = None
    settings: CurvatureSettings = field(default_factory=CurvatureSettings)


@dataclass
class BakeResult:
    """Outcome of ``BakeEngine.bake`` including resolved implementation metadata.

    Attributes:
        output: Packed (and optional signed) arrays from the bake method.
        map_type: Resolved map type from the implementation class.
        method_id: Resolved method id from the implementation class.
        device: Actual device used (``"cpu"`` or ``"gpu"``).
        context: Optional ``BakeContext`` when textures were loaded from disk.
    """

    output: BakeMapOutput
    map_type: str
    method_id: str
    device: str
    context: BakeContext | None = None


class BakeEngine:
    """Resolve and run a single bake map."""

    def bake(self, request: BakeRequest) -> BakeResult:
        """Resolve a bake map implementation and run it once.

        Args:
            request: Map/method/device selection plus inputs or ``bake_dir``.

        Returns:
            ``BakeResult`` with output arrays and resolved implementation ids.
        """
        settings = request.settings
        ctx: BakeContext | None = None
        if request.inputs is None:
            if request.bake_dir is None:
                raise ValueError("bake_dir or inputs required")
            ctx = load_bake_context(request.bake_dir, settings)
            inputs = context_to_input(ctx, settings)
        else:
            inputs = request.inputs
            if inputs.settings is not settings:
                inputs = BakeMapInput(**{**inputs.__dict__, "settings": settings})

        impl = resolve_bake_map(request.map_type, request.method_id, request.device)
        output = impl.bake(inputs)
        coverage = resolve_coverage_mask(inputs.valid, output.valid)
        if output.valid is None:
            output = BakeMapOutput(
                packed=output.packed,
                signed=output.signed,
                valid=coverage,
                meta=dict(output.meta),
            )
        if settings_debug_texel_fail(settings):
            meta = dict(output.meta)
            meta["coverage_mask"] = coverage
            output = BakeMapOutput(
                packed=output.packed,
                signed=output.signed,
                valid=output.valid,
                meta=meta,
            )
        return BakeResult(
            output=output,
            map_type=impl.map_type,
            method_id=impl.method_id,
            device=impl.device,
            context=ctx,
        )

    def bake_packed(
        self,
        map_type: str,
        method_id: str,
        *,
        bake_dir: str | None = None,
        inputs: BakeMapInput | None = None,
        settings: CurvatureSettings | None = None,
        device: str | Backend = Backend.AUTO,
        **input_fields: Any,
    ) -> np.ndarray:
        """Convenience: return packed grayscale array only."""
        if inputs is None and input_fields:
            inputs = BakeMapInput(settings=settings or CurvatureSettings(), **input_fields)
        request = BakeRequest(
            map_type=map_type,
            method_id=method_id,
            device=device,
            bake_dir=bake_dir,
            inputs=inputs,
            settings=settings or CurvatureSettings(),
        )
        return self.bake(request).output.packed

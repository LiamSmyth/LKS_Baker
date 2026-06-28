"""AO-specific ``BakeMap`` helpers."""
from __future__ import annotations

from lks_baker.bake_ops.engine.bake_map import BakeMapInput
from lks_baker.bake_ops.engine.bake_maps.bake_map_implementation import BakeMapImplementation
from lks_baker.bake_ops.engine.settings.ao_settings import AoSettings


class AoMapImplementation(BakeMapImplementation):
    """Shared helpers mixed into AO CPU bake map classes."""

    @staticmethod
    def ao_settings(inputs: BakeMapInput) -> AoSettings:
        """Return per-invocation AO settings from ``inputs.extra``."""
        return inputs.extra.get("ao_settings", AoSettings())

    @staticmethod
    def require_object_normal_and_position(inputs: BakeMapInput) -> None:
        """Raise when object-space normal or position textures are missing."""
        if inputs.object_normal is None or inputs.position is None:
            raise ValueError("AO method requires normal_object and position textures")

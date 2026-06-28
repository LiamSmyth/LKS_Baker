"""H→L specular emit raster (CPU)."""
from __future__ import annotations

from typing import ClassVar

from lks_baker.bake_ops.engine.bake_map import BakeMapInput
from lks_baker.bake_ops.engine.map_types.specular.specular_map import SpecularMap
from lks_baker.bake_ops.engine.map_types.specular.specular_map_implementation import (
    SpecularMapImplementation,
)
from lks_baker.bake_ops.engine.map_types.specular.static_utilities.emit_raster import (
    emit_raster_specular,
)


class EmitRasterCpu(SpecularMap, SpecularMapImplementation):
    """Raycast specular emit from high mesh Principled materials onto low UV."""

    method_id: ClassVar[str] = "emit_raster"
    device: ClassVar[str] = "cpu"
    execution_kind: ClassVar[str] = "derive_mesh"
    cost_tier: ClassVar[int] = 2
    requires_meshes: ClassVar[frozenset[str]] = frozenset({"low", "high"})

    def bake(self, inputs: BakeMapInput):
        low = inputs.low_mesh
        high = inputs.high_mesh
        if low is None or high is None:
            raise ValueError("emit_raster requires low_mesh and high_mesh in BakeMapInput")
        image_size = inputs.image_size
        if image_size is None:
            raise ValueError("emit_raster requires image_size")

        material_data = inputs.extra.get("mesh_material_emit_data")
        if (
            material_data is None
            or not hasattr(material_data, "slot_emit_rgb")
            or not hasattr(material_data, "face_slot_index")
        ):
            raise ValueError("emit_raster requires MeshMaterialEmitData in inputs.extra")

        config = self.emit_raster_config(inputs)
        rgba, valid = emit_raster_specular(
            low,
            high,
            material_data,
            image_size,
            cage_extrusion=config.cage_extrusion,
            max_ray_distance=config.max_ray_distance,
        )
        if inputs.valid is not None and inputs.valid.shape == valid.shape:
            valid = valid & inputs.valid
            rgba[~valid] = 0.0
        return self.rgb_output(rgba, valid=valid)

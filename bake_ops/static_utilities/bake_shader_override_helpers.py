"""Store and restore high-mesh material slots during emit bake passes."""

from __future__ import annotations

import bpy


class BakeMaterialOverrideStack:
    """Per-bake-session snapshot stack for high mesh material slots."""

    def __init__(self) -> None:
        self._snapshots: dict[str, list[bpy.types.Material | None]] = {}

    def snapshot_object_slots(self, obj: bpy.types.Object) -> list[bpy.types.Material | None]:
        """Return a copy of current slot materials (does not mutate)."""
        return [slot.material for slot in obj.material_slots]

    def assign_slots(
        self,
        obj: bpy.types.Object,
        materials: list[bpy.types.Material | None],
        *,
        store_prior: bool = True,
    ) -> None:
        """Assign slot materials; optionally snapshot originals once per object."""
        if store_prior and obj.name not in self._snapshots:
            self._snapshots[obj.name] = self.snapshot_object_slots(obj)
        for index, material in enumerate(materials):
            while len(obj.material_slots) <= index:
                obj.data.materials.append(None)
            obj.material_slots[index].material = material

    def restore_all(self) -> None:
        """Restore all snapshotted objects to their prior slot materials."""
        for obj_name, materials in self._snapshots.items():
            obj = bpy.data.objects.get(obj_name)
            if obj is None:
                continue
            for index, material in enumerate(materials):
                if index >= len(obj.material_slots):
                    break
                obj.material_slots[index].material = material
        self._snapshots.clear()

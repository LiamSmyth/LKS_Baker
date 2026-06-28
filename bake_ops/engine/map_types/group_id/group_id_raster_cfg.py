"""Static config for the ``group_id_raster`` bake method."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lks_baker.bake_ops.engine.map_types.group_id.static_utilities.face_group_ids import (
    resolve_group_id_attribute_name,
)

if TYPE_CHECKING:
    from lks_baker.bake_ops.lks_bake_props import LKS_PG_BakeMapEntry


@dataclass
class GroupIdRasterConfig:
    """Face attribute source and background handling for group ID raster."""

    attribute_name: str = ".sculpt_face_set"
    treat_zero_as_background: bool = False


def config_from_entry(entry: LKS_PG_BakeMapEntry) -> GroupIdRasterConfig:
    """Build config from map-entry RNA."""
    attribute_name = resolve_group_id_attribute_name(
        preset=str(entry.lks_group_id_attr_preset),
        custom_name=str(entry.lks_group_id_attribute_name),
    )
    return GroupIdRasterConfig(
        attribute_name=attribute_name,
        treat_zero_as_background=bool(entry.lks_group_id_treat_zero_as_background),
    )

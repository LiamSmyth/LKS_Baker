"""Read-only catalog metadata for engine planner (no bpy)."""
from lks_baker.bake_ops.static_utilities.bake_map_catalog import (  # noqa: F401
    BAKE_MAP_CATALOG,
    BAKE_MAP_CATEGORIES,
    BAKE_MAP_CATEGORY_COLUMNS,
    BAKE_MAP_CATEGORY_LABELS,
    ENGINE_MAP_TYPE_ALIASES,
    LKS_BakeMapSpec,
    catalog_map_count,
    get_bake_map_spec,
    get_map_display_label,
    is_post_antialias_eligible,
    resolve_engine_map_type,
    resolve_map_enabled,
    seed_bake_project_map_entries_if_needed,
)

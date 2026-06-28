"""Static Marmoset-parity bake map catalog — no operator imports."""

from __future__ import annotations

from dataclasses import dataclass


BAKE_MAP_CATEGORIES: tuple[str, ...] = ('surface', 'lighting', 'masks', 'pbr')

BAKE_MAP_LIGHTING_IDS: frozenset[str] = frozenset({
    'complete_lighting',
    'diffuse_lighting',
    'specular_lighting',
    'indirect_lighting',
})

BAKE_MAP_CATEGORY_LABELS: dict[str, str] = {
    'surface': 'Surface',
    'lighting': 'Lighting',
    'masks': 'Masks',
    'pbr': 'PBR',
}

# Column layout for two-column Bakes UI (left / right).
BAKE_MAP_CATEGORY_COLUMNS: tuple[tuple[str, ...], tuple[str, ...]] = (
    ('surface', 'lighting'),
    ('masks', 'pbr'),
)

# Catalog map_ids that share another map's bake-engine ``map_type`` (separate UI/output row).
ENGINE_MAP_TYPE_ALIASES: dict[str, str] = {
    'ao_2': 'ao',
}


@dataclass(frozen=True)
class LKS_BakeMapSpec:
    """One catalog row for compile / execute filtering."""

    map_id: str
    label: str
    category: str
    output_suffix: str
    color_space: str
    default_enabled: bool
    blender_backend: str
    cycles_type: str | None
    normal_space: str | None
    phase1: str
    pass_group: str
    sort_order: int
    implemented: bool
    derive_from: tuple[str, ...] = ()
    derive_method: str | None = None
    post_denoise_eligible: bool = False
    post_antialias_eligible: bool = False
    pass_filter: frozenset[str] | None = None


def _spec(
    map_id: str,
    label: str,
    *,
    category: str,
    output_suffix: str,
    color_space: str = 'Non-Color',
    default_enabled: bool = False,
    blender_backend: str = 'cycles_native',
    cycles_type: str | None = None,
    normal_space: str | None = None,
    phase1: str = 'deferred',
    pass_group: str = 'raycast',
    sort_order: int = 0,
    implemented: bool = False,
    derive_from: tuple[str, ...] = (),
    derive_method: str | None = None,
    post_antialias_eligible: bool = False,
    post_denoise_eligible: bool = False,
    pass_filter: frozenset[str] | None = None,
) -> LKS_BakeMapSpec:
    return LKS_BakeMapSpec(
        map_id=map_id,
        label=label,
        category=category,
        output_suffix=output_suffix,
        color_space=color_space,
        default_enabled=default_enabled,
        blender_backend=blender_backend,
        cycles_type=cycles_type,
        normal_space=normal_space,
        phase1=phase1,
        pass_group=pass_group,
        sort_order=sort_order,
        implemented=implemented,
        derive_from=derive_from,
        derive_method=derive_method,
        post_antialias_eligible=post_antialias_eligible,
        post_denoise_eligible=post_denoise_eligible,
        pass_filter=pass_filter,
    )


BAKE_MAP_CATALOG: dict[str, LKS_BakeMapSpec] = {
    # --- Surface ---
    'normal': _spec(
        'normal', 'Normals',
        category='surface', output_suffix='normal',
        default_enabled=True, cycles_type='NORMAL',
        normal_space='TANGENT', phase1='yes', sort_order=10,
        implemented=True,
    ),
    'normal_object': _spec(
        'normal_object', 'Normals (Object)',
        category='surface', output_suffix='normal_object',
        default_enabled=True, cycles_type='NORMAL',
        normal_space='OBJECT', phase1='yes', sort_order=20,
        blender_backend='texture_derive',
        derive_from=('normal',),
        derive_method='normal_object_from_tangent',
        implemented=True,
    ),
    'height': _spec(
        'height', 'Height',
        category='surface', output_suffix='height',
        default_enabled=True, sort_order=30,
    ),
    'position': _spec(
        'position', 'Position',
        category='surface', output_suffix='position',
        default_enabled=True, cycles_type='POSITION', phase1='yes', sort_order=40,
        implemented=True,
    ),
    'curvature': _spec(
        'curvature', 'Curvature',
        category='surface', output_suffix='curvature',
        default_enabled=True, sort_order=50,
        blender_backend='texture_derive',
        derive_from=('normal_object',),
        derive_method='curvature_from_normal',
        pass_group='shader_curvature',
        implemented=True,
    ),
    'convexity': _spec(
        'convexity', 'Convexity',
        category='surface', output_suffix='convexity',
        default_enabled=True, sort_order=60,
        blender_backend='texture_derive',
        derive_from=('curvature',),
        derive_method='convexity_from_curvature',
        pass_group='shader_convexity',
        implemented=True,
    ),
    'cavity': _spec(
        'cavity', 'Cavity',
        category='surface', output_suffix='cavity',
        default_enabled=True, sort_order=70,
        blender_backend='texture_derive',
        derive_from=('curvature',),
        derive_method='cavity_from_curvature',
        pass_group='shader_cavity',
        implemented=True,
    ),
    'thickness': _spec(
        'thickness', 'Thickness',
        category='surface', output_suffix='thickness',
        default_enabled=True, sort_order=80,
    ),
    'bent_normal': _spec(
        'bent_normal', 'Bent Normals',
        category='surface', output_suffix='bent_normal',
        normal_space='TANGENT', sort_order=90,
        blender_backend='texture_derive',
        derive_from=('normal_object', 'position'),
        derive_method='hemisphere_trace',
        implemented=True,
    ),
    'bent_normal_object': _spec(
        'bent_normal_object', 'Bent Normals (Object)',
        category='surface', output_suffix='bent_normal_object',
        sort_order=100,
        blender_backend='texture_derive',
        derive_from=('normal_object', 'position'),
        derive_method='bent_normal_object',
        implemented=True,
    ),
    # --- Lighting ---
    'ao': _spec(
        'ao', 'Ambient Occlusion',
        category='lighting', output_suffix='ao',
        default_enabled=True, cycles_type='AO', phase1='yes', sort_order=110,
        implemented=True,
        post_antialias_eligible=True,
        post_denoise_eligible=True,
    ),
    'ao_2': _spec(
        'ao_2', 'Ambient Occlusion (2)',
        category='lighting', output_suffix='ao_2',
        cycles_type='AO', phase1='yes', sort_order=120,
        implemented=True,
        post_antialias_eligible=True,
        post_denoise_eligible=True,
    ),
    'complete_lighting': _spec(
        'complete_lighting', 'Complete Lighting',
        category='lighting', output_suffix='complete_lighting',
        color_space='sRGB', blender_backend='cycles_combined', cycles_type='COMBINED',
        pass_group='lighting', sort_order=130, implemented=True,
        pass_filter=frozenset({'DIRECT', 'INDIRECT', 'DIFFUSE', 'GLOSSY', 'TRANSMISSION'}),
        post_antialias_eligible=True, post_denoise_eligible=True,
    ),
    'diffuse_lighting': _spec(
        'diffuse_lighting', 'Diffuse Lighting',
        category='lighting', output_suffix='diffuse_lighting',
        color_space='sRGB', blender_backend='cycles_combined', cycles_type='COMBINED',
        pass_group='lighting', sort_order=140, implemented=True,
        pass_filter=frozenset({'DIRECT', 'INDIRECT', 'DIFFUSE'}),
        post_antialias_eligible=True, post_denoise_eligible=True,
    ),
    'specular_lighting': _spec(
        'specular_lighting', 'Specular Lighting',
        category='lighting', output_suffix='specular_lighting',
        color_space='sRGB', blender_backend='cycles_combined', cycles_type='COMBINED',
        pass_group='lighting', sort_order=150, implemented=True,
        pass_filter=frozenset({'DIRECT', 'INDIRECT', 'GLOSSY'}),
        post_antialias_eligible=True, post_denoise_eligible=True,
    ),
    'indirect_lighting': _spec(
        'indirect_lighting', 'Indirect Lighting',
        category='lighting', output_suffix='indirect_lighting',
        color_space='sRGB', blender_backend='cycles_combined', cycles_type='COMBINED',
        pass_group='lighting', sort_order=160, implemented=True,
        pass_filter=frozenset({'INDIRECT', 'DIFFUSE', 'GLOSSY'}),
        post_antialias_eligible=True, post_denoise_eligible=True,
    ),
    # --- Masks ---
    'material_id': _spec(
        'material_id', 'Material ID',
        category='masks', output_suffix='material_id',
        default_enabled=True, blender_backend='cycles_emit', cycles_type='EMIT',
        phase1='resource', pass_group='shader_id', sort_order=210,
        implemented=True,
    ),
    'object_id': _spec(
        'object_id', 'Object ID',
        category='masks', output_suffix='object_id',
        default_enabled=True, blender_backend='cycles_emit', cycles_type='EMIT',
        phase1='resource', pass_group='shader_id', sort_order=220,
        implemented=True,
    ),
    'group_id': _spec(
        'group_id', 'Group ID',
        category='masks', output_suffix='group_id',
        default_enabled=True, pass_group='id_mask', sort_order=230,
        blender_backend='texture_derive',
        derive_method='group_id_raster',
        implemented=True,
    ),
    'uv_island': _spec(
        'uv_island', 'UV Island',
        category='masks', output_suffix='uv_island',
        pass_group='id_mask', sort_order=240,
        blender_backend='texture_derive',
        derive_method='uv_island_from_mesh',
        implemented=True,
    ),
    'wireframe': _spec(
        'wireframe', 'Wireframe',
        category='masks', output_suffix='wireframe',
        pass_group='id_mask', sort_order=250,
        blender_backend='texture_derive',
        derive_method='wireframe_uv_raster',
        implemented=True,
    ),
    'alpha_mask': _spec(
        'alpha_mask', 'Alpha Mask',
        category='masks', output_suffix='alpha_mask',
        pass_group='id_mask', sort_order=260,
        blender_backend='texture_derive',
        derive_from=('transparency',),
        derive_method='alpha_mask_from_transparency',
        implemented=True,
    ),
    # --- PBR ---
    'albedo': _spec(
        'albedo', 'Albedo',
        category='pbr', output_suffix='albedo',
        color_space='sRGB', blender_backend='cycles_emit',
        default_enabled=True, cycles_type='EMIT', phase1='resource', pass_group='shader_pbr',
        sort_order=310,
        implemented=True,
        post_antialias_eligible=True,
    ),
    'specular': _spec(
        'specular', 'Specular',
        category='pbr', output_suffix='specular',
        blender_backend='cycles_emit', cycles_type='EMIT',
        phase1='resource', pass_group='shader_pbr',
        sort_order=330,
        implemented=True,
        post_antialias_eligible=True,
    ),
    'roughness': _spec(
        'roughness', 'Roughness',
        category='pbr', output_suffix='roughness',
        cycles_type='ROUGHNESS', phase1='yes', pass_group='shader_pbr', sort_order=350,
        implemented=True,
        post_antialias_eligible=True,
    ),
    'metalness': _spec(
        'metalness', 'Metalness',
        category='pbr', output_suffix='metalness',
        blender_backend='cycles_emit', cycles_type='EMIT',
        phase1='resource', pass_group='shader_pbr', sort_order=360,
        implemented=True,
        post_antialias_eligible=True,
    ),
    'emissive': _spec(
        'emissive', 'Emissive',
        category='pbr', output_suffix='emissive',
        color_space='sRGB', blender_backend='cycles_emit',
        cycles_type='EMIT', phase1='resource', pass_group='shader_pbr', sort_order=370,
        implemented=True,
    ),
    'transparency': _spec(
        'transparency', 'Transparency',
        category='pbr', output_suffix='transparency',
        blender_backend='cycles_emit', cycles_type='EMIT',
        pass_group='shader_pbr', sort_order=380,
        implemented=True,
    ),
    'vertex_color': _spec(
        'vertex_color', 'Vertex Color',
        category='pbr', output_suffix='vertex_color',
        color_space='sRGB', default_enabled=True,
        blender_backend='cycles_emit', cycles_type='EMIT',
        pass_group='shader_vcol', sort_order=390,
        implemented=True,
    ),
}


POST_ANTIALIAS_ELIGIBLE_MAPS: frozenset[str] = frozenset(
    map_id for map_id, spec in BAKE_MAP_CATALOG.items() if spec.post_antialias_eligible
)

EDGE_SENSITIVE_MAP_IDS: frozenset[str] = frozenset({
    'normal',
    'normal_object',
    'bent_normal',
    'bent_normal_object',
    'material_id',
    'object_id',
    'group_id',
    'uv_island',
    'wireframe',
    'alpha_mask',
})


def get_bake_map_spec(map_id: str) -> LKS_BakeMapSpec | None:
    return BAKE_MAP_CATALOG.get(map_id)


def resolve_engine_map_type(map_id: str) -> str:
    """Registry ``map_type`` for a catalog ``map_id`` (identity when not aliased)."""
    return ENGINE_MAP_TYPE_ALIASES.get(map_id, map_id)


def is_post_antialias_eligible(map_id: str) -> bool:
    """Return whether gear UI and bake executor may apply post-bake AA."""
    spec = get_bake_map_spec(map_id)
    return spec.post_antialias_eligible if spec is not None else False


def is_edge_sensitive_map(map_id: str) -> bool:
    """Return whether AA/denoise may visibly soften edges on this map type."""
    return map_id in EDGE_SENSITIVE_MAP_IDS


def iter_catalog_specs() -> list[LKS_BakeMapSpec]:
    return list(BAKE_MAP_CATALOG.values())


def iter_catalog_specs_for_category(category: str) -> list[LKS_BakeMapSpec]:
    return sorted(
        (spec for spec in BAKE_MAP_CATALOG.values() if spec.category == category),
        key=lambda spec: spec.sort_order,
    )


def catalog_map_count() -> int:
    return len(BAKE_MAP_CATALOG)


def get_map_display_label(map_id: str, *, spec: LKS_BakeMapSpec | None = None) -> str:
    """Catalog label with ``(TODO)`` suffix when the bake executor is not implemented."""
    resolved = spec if spec is not None else get_bake_map_spec(map_id)
    if resolved is None:
        return map_id
    if resolved.implemented:
        return resolved.label
    return f'{resolved.label} (TODO)'


def needs_bake_map_catalog_seed(project) -> bool:
    """True when catalog map_ids are missing from project.map_entries."""
    existing = {entry.map_id for entry in project.map_entries}
    return any(map_id not in existing for map_id in BAKE_MAP_CATALOG)


def seed_bake_project_map_entries(project) -> None:
    """Ensure one RNA row per catalog entry (preserves user edits on re-seed)."""
    from .bake_method_catalog import default_bake_method_for_map_id

    existing = {entry.map_id for entry in project.map_entries}
    for spec in sorted(iter_catalog_specs(), key=lambda spec: spec.sort_order):
        if spec.map_id in existing:
            continue
        entry = project.map_entries.add()
        entry.map_id = spec.map_id
        entry.enabled = spec.default_enabled
        entry.resolution = 0
        entry.samples = 0
        default_method = default_bake_method_for_map_id(spec.map_id)
        if default_method:
            entry.lks_bake_method = default_method


def seed_bake_project_map_entries_if_needed(project) -> bool:
    """Seed missing catalog rows; return True when rows were added."""
    if not needs_bake_map_catalog_seed(project):
        return False
    seed_bake_project_map_entries(project)
    return True


def resolve_map_enabled(project, map_id: str) -> bool:
    """Return whether a map_id is enabled on the project RNA."""
    for entry in project.map_entries:
        if entry.map_id == map_id:
            return entry.enabled
    spec = get_bake_map_spec(map_id)
    return spec.default_enabled if spec is not None else False

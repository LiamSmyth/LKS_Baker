"""RNA PropertyGroups for LKS BakeProject scaffolding."""

from __future__ import annotations

import bpy

from ..shared_utilities.lks_constants import (
    BAKE_CURVATURE_CONVEXITY_SIGN,
    BAKE_CURVATURE_DEVICE_DEFAULT,
    BAKE_CURVATURE_DEVICE_ITEMS,
    BAKE_CURVATURE_MAGNITUDE_GAIN,
    BAKE_CURVATURE_METHOD_DEFAULT,
    BAKE_CURVATURE_METHOD_ITEMS,
    BAKE_CURVATURE_RELATIVE_TO_BBOX,
    BAKE_CURVATURE_SAMPLING_RADIUS,
    BAKE_CURVATURE_UNITIZE_DEFAULT,
    BAKE_IMAGE_FILE_TYPE_DEFAULT,
    BAKE_IMAGE_FILE_TYPE_ITEMS,
    BAKE_EXPORT_MODE_DEFAULT,
    BAKE_EXPORT_MODE_ITEMS,
    BAKE_LOW_MATERIAL_SUFFIX,
    BAKE_MARGIN_DEFAULT,
)
from .static_utilities.bake_image_output_helpers import (
    bake_image_color_depth_default_for_file_type,
    bake_image_color_depth_items_for_file_type,
    valid_bake_image_color_depths,
)
from .static_utilities.bake_margin_helpers import BAKE_MARGIN_PRE_ERODE_DEFAULT
from .static_utilities.bake_resolution_helpers import (
    make_resolution_enum_property,
    sync_linked_resolution_axis,
)

BAKE_MODE_ITEMS: list[tuple[str, str, str, int]] = [
    ('HIGH_LOW', 'High to Low', 'Cross-mesh selected-to-active bake', 0),
    ('LOW_LOW', 'Low to Low', 'Bake shader/geo metadata from mesh to own textures', 1),
    ('MULTIRES', 'Multires', 'Multiresolution modifier bake', 2),
]


def _bake_map_method_enum_items(
    self: LKS_PG_BakeMapEntry,
    _context: bpy.types.Context,
) -> list[tuple[str, str, str]]:
    from .static_utilities.bake_method_catalog import iter_bake_method_enum_items

    return iter_bake_method_enum_items(self.map_id)


class LKS_PG_CurvatureSoftSettings(bpy.types.PropertyGroup):
    """Bake-engine soft curvature tuning (``soft_curvature`` method)."""

    normalize_each_scale: bpy.props.BoolProperty(
        name='Normalize Each Scale',
        description='Percentile-normalize curvature at each mip radius before blending',
        default=True,
    )
    normalize_percentile: bpy.props.FloatProperty(
        name='Scale Normalize %',
        description='Percentile for per-scale normalization (abs curvature)',
        default=95.0,
        min=50.0,
        max=99.9,
        precision=1,
    )
    convex_is_white: bpy.props.BoolProperty(
        name='Convex is White',
        description='Flip sign so convex areas pack bright (Substance-style)',
        default=True,
    )
    samples_per_radius: bpy.props.IntProperty(
        name='Ring Samples',
        description='Samples per ring offset (0 = auto from radius)',
        default=0,
        min=0,
        max=4096,
    )
    max_radius: bpy.props.IntProperty(
        name='Max Radius',
        description='Largest mip radius in texels (0 = full chain to half map size)',
        default=0,
        min=0,
        max=4096,
    )
    pack_strength: bpy.props.FloatProperty(
        name='Pack Strength',
        description='Final signed-to-grayscale contrast',
        default=0.5,
        min=0.0,
        max=1.0,
    )
    pack_percentile: bpy.props.FloatProperty(
        name='Pack Percentile',
        description='Percentile for final output tonemap',
        default=95.0,
        min=50.0,
        max=99.9,
        precision=1,
    )
    pack_flat: bpy.props.FloatProperty(
        name='Pack Flat',
        description='Mid-gray anchor for packed output',
        default=0.5,
        min=0.0,
        max=1.0,
    )


class LKS_PG_LightingBakeSettings(bpy.types.PropertyGroup):
    """Cycles COMBINED lighting bake overrides (``blender`` method)."""

    max_bounce_override: bpy.props.IntProperty(
        name='Max Bounces Override',
        description='Override scene max bounces for this map (0 = inherit scene)',
        default=0,
        min=0,
        max=1024,
    )
    clamp_direct: bpy.props.FloatProperty(
        name='Clamp Direct',
        description='Sample clamp for direct lighting (0 = inherit scene)',
        default=0.0,
        min=0.0,
        soft_max=100.0,
    )
    clamp_indirect: bpy.props.FloatProperty(
        name='Clamp Indirect',
        description='Sample clamp for indirect lighting (0 = inherit scene)',
        default=0.0,
        min=0.0,
        soft_max=100.0,
    )


class LKS_PG_BentNormalSettings(bpy.types.PropertyGroup):
    """Tangent-space bent-normal atlas sampling (``hemisphere_trace`` method)."""

    sample_count: bpy.props.IntProperty(
        name='Sample Count',
        description='Hemisphere sample count for bent-normal integration',
        default=16,
        min=4,
        max=64,
    )
    steps_per_direction: bpy.props.IntProperty(
        name='Steps per Direction',
        description='UV atlas march steps per hemisphere sample',
        default=8,
        min=1,
        max=32,
    )
    radius_world: bpy.props.FloatProperty(
        name='Radius (World)',
        description='World-space occlusion search radius',
        default=0.35,
        min=0.01,
        max=8.0,
        precision=3,
    )
    spread: bpy.props.FloatProperty(
        name='Hemisphere Spread',
        description='1.0 = full upper hemisphere; lower values tighten the cone',
        default=1.0,
        min=0.05,
        max=1.0,
        precision=2,
    )
    bias: bpy.props.FloatProperty(
        name='Bias',
        description='Self-occlusion bias for atlas march alignment',
        default=0.02,
        min=0.0,
        max=0.25,
        precision=3,
    )


class LKS_PG_BentNormalObjectSettings(bpy.types.PropertyGroup):
    """Object-space bent-normal atlas sampling (``bent_normal_object`` method)."""

    directions: bpy.props.IntProperty(
        name='Directions',
        description='Hemisphere sample count for bent-normal integration',
        default=12,
        min=4,
        max=64,
    )
    steps_per_direction: bpy.props.IntProperty(
        name='Steps per Direction',
        description='UV atlas march steps per hemisphere sample',
        default=8,
        min=1,
        max=32,
    )
    radius_world: bpy.props.FloatProperty(
        name='Radius (World)',
        description='World-space occlusion search radius',
        default=0.35,
        min=0.01,
        max=8.0,
        precision=3,
    )
    spread_angle_deg: bpy.props.FloatProperty(
        name='Spread Angle',
        description='Hemisphere cone half-angle in degrees (90 = full hemisphere)',
        default=90.0,
        min=5.0,
        max=90.0,
        precision=1,
    )
    bias: bpy.props.FloatProperty(
        name='Bias',
        description='Self-occlusion bias for atlas march alignment',
        default=0.02,
        min=0.0,
        max=0.25,
        precision=3,
    )


class LKS_PG_CurvatureLegacySettings(bpy.types.PropertyGroup):
    """Legacy TSNM filter tuning (SD / multiscale / single-scale)."""

    magnitude_gain: bpy.props.FloatProperty(
        name='Magnitude Gain',
        description='Scale angular normal deviation before packing',
        default=BAKE_CURVATURE_MAGNITUDE_GAIN,
        min=0.01,
        max=32.0,
    )
    sampling_radius: bpy.props.FloatProperty(
        name='Sampling Radius',
        description='SD disk-ray radius as fraction of map size (when relative to bbox)',
        default=BAKE_CURVATURE_SAMPLING_RADIUS,
        min=0.0001,
        max=0.25,
        precision=4,
    )
    relative_to_bbox: bpy.props.BoolProperty(
        name='Relative to Bbox',
        description='Scale SD sampling radius by max texture dimension',
        default=BAKE_CURVATURE_RELATIVE_TO_BBOX,
    )
    convexity_sign: bpy.props.FloatProperty(
        name='Convexity Sign',
        description='SD convexity sign multiplier (+1 = convex bright)',
        default=BAKE_CURVATURE_CONVEXITY_SIGN,
        min=-1.0,
        max=1.0,
    )


class LKS_PG_BakeMapEntry(bpy.types.PropertyGroup):
    """One row per catalog map_id; full 31-map seed on project create; phase 1 executes normal + normal_object only."""

    map_id: bpy.props.StringProperty(name='Map ID', default='')
    enabled: bpy.props.BoolProperty(name='Enabled', default=True)
    resolution: bpy.props.IntProperty(name='Resolution', default=0, min=0)
    samples: bpy.props.IntProperty(name='Samples', default=0, min=0)
    margin: bpy.props.IntProperty(
        name='Margin',
        description=(
            'Post-bake dilate override: 0 = use project default; '
            '-1 = infinite fill to image bounds; N > 0 = explicit pixel margin'
        ),
        default=0,
        min=-1,
    )
    lks_bake_margin_pre_erode: bpy.props.IntProperty(
        name='Margin Pre-Erode',
        description=(
            'Shrink the dilate seed mask inward before margin fill (pixels): '
            '0 = use project default; N > 0 = ignore N px of UV rim when sampling'
        ),
        default=0,
        min=0,
        max=32,
    )
    lks_bake_margin_adjust: bpy.props.IntProperty(
        name='Margin Adjust (legacy)',
        description='Deprecated — use Margin Pre-Erode (positive pixels)',
        default=0,
        min=-32,
        max=32,
        options={'HIDDEN'},
    )
    lks_bake_method: bpy.props.EnumProperty(
        name='Method',
        description='Bake engine method implementation for this map type',
        items=_bake_map_method_enum_items,
    )
    lks_curvature_method: bpy.props.EnumProperty(
        name='Curvature Method',
        description='Curvature derive kernel (legacy TSNM filters or bake-engine soft curvature)',
        items=BAKE_CURVATURE_METHOD_ITEMS,
        default=BAKE_CURVATURE_METHOD_DEFAULT,
    )
    lks_curvature_device: bpy.props.EnumProperty(
        name='Curvature Device',
        description='CPU/GPU backend when method uses the bake engine (Soft Curvature)',
        items=BAKE_CURVATURE_DEVICE_ITEMS,
        default=BAKE_CURVATURE_DEVICE_DEFAULT,
    )
    lks_curvature_unitize: bpy.props.BoolProperty(
        name='Unitize Curvature',
        description='Stretch signed curvature to full 0–1 range centered at 0.5',
        default=BAKE_CURVATURE_UNITIZE_DEFAULT,
    )
    lks_curvature_soft: bpy.props.PointerProperty(type=LKS_PG_CurvatureSoftSettings)
    lks_curvature_legacy: bpy.props.PointerProperty(type=LKS_PG_CurvatureLegacySettings)
    lks_bent_normal: bpy.props.PointerProperty(type=LKS_PG_BentNormalSettings)
    lks_bent_normal_object: bpy.props.PointerProperty(type=LKS_PG_BentNormalObjectSettings)
    lks_lighting: bpy.props.PointerProperty(type=LKS_PG_LightingBakeSettings)
    lks_wireframe_color: bpy.props.FloatVectorProperty(
        name='Wireframe Color',
        description='RGBA tint for wireframe lines',
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )
    lks_wireframe_aa_quality: bpy.props.EnumProperty(
        name='Wireframe AA Quality',
        description='Edge anti-aliasing width for wireframe raster',
        items=(
            ('LOW', 'Low', 'Narrow edge soften'),
            ('MEDIUM', 'Medium', 'Balanced anti-aliasing'),
            ('HIGH', 'High', 'Wide edge soften'),
        ),
        default='MEDIUM',
    )
    lks_wireframe_line_thickness: bpy.props.FloatProperty(
        name='Wireframe Line Thickness',
        description='Full stroke width in atlas texels (pixels)',
        default=1.5,
        min=0.5,
        max=32.0,
        precision=2,
    )
    lks_group_id_attr_preset: bpy.props.EnumProperty(
        name='Group ID Attribute Preset',
        description='Which face INT attribute encodes polygroups / face sets',
        items=(
            ('FACE_SET', 'Face Set', 'Blender sculpt face set (.sculpt_face_set)'),
            ('POLYGROUP', 'Polygroup', 'ZBrush-style polygroup attribute (polygroup/pg fallback chain)'),
            ('CUSTOM', 'Custom', 'User-specified face INT attribute name'),
        ),
        default='FACE_SET',
    )
    lks_group_id_attribute_name: bpy.props.StringProperty(
        name='Group ID Attribute',
        description='Custom face INT attribute name when preset is Custom',
        default='polygroup',
    )
    lks_group_id_treat_zero_as_background: bpy.props.BoolProperty(
        name='Zero Is Background',
        description='Treat group id 0 as empty background (unpainted texels)',
        default=False,
    )
    lks_post_denoise: bpy.props.BoolProperty(
        name='Denoise',
        description='Post-process denoise after bake (OIDN / map-aware)',
        default=False,
    )
    lks_post_antialias: bpy.props.BoolProperty(
        name='Antialias',
        description=(
            'Edge-aware antialiasing after bake (avoids 2× Cycles oversample); '
            'softens jagged edges without baking at higher resolution'
        ),
        default=False,
    )
    lks_post_antialias_strength: bpy.props.FloatProperty(
        name='Antialias Strength',
        description='Blend strength for post-bake edge-aware antialiasing',
        default=0.5,
        min=0.0,
        max=1.0,
    )


class LKS_PG_BakeGroupUiSlot(bpy.types.PropertyGroup):
    """Fixed placeholder row for bake group role UILists (never synced in draw)."""


def _select_bake_group_list_object(
    group: LKS_PG_BakeGroup,
    context: bpy.types.Context,
    objects: list[bpy.types.Object],
    index: int,
) -> None:
    if not (0 <= index < len(objects)):
        return
    obj = objects[index]
    if obj is None or obj.name not in bpy.data.objects:
        return
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _on_bake_group_high_index_changed(
    self: LKS_PG_BakeGroup,
    context: bpy.types.Context,
) -> None:
    from .helpers_bake_cleanup import find_bake_group_project, iter_bake_group_high_objects

    project = find_bake_group_project(context.scene, self)
    if project is None:
        return
    _select_bake_group_list_object(
        self,
        context,
        iter_bake_group_high_objects(project, self),
        self.active_high_index,
    )


def _on_bake_group_low_index_changed(
    self: LKS_PG_BakeGroup,
    context: bpy.types.Context,
) -> None:
    from .helpers_bake_cleanup import find_bake_group_project, iter_bake_group_low_objects

    project = find_bake_group_project(context.scene, self)
    if project is None:
        return
    _select_bake_group_list_object(
        self,
        context,
        iter_bake_group_low_objects(project, self),
        self.active_low_index,
    )


def _on_bake_group_name_changed(
    self: LKS_PG_BakeGroup,
    context: bpy.types.Context,
) -> None:
    """Rename group collection tree after RNA ``name`` edits."""
    from .helpers_bake_cleanup import rename_bake_group

    rename_bake_group(self, context.scene)


class LKS_PG_BakeGroup(bpy.types.PropertyGroup):
    """One bake group row under an LKS BakeProject."""

    name: bpy.props.StringProperty(
        name='Name',
        default='',
        update=_on_bake_group_name_changed,
    )
    high_root: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name='High Root',
        description='Deprecated — legacy organizer empty; export naming uses high_collection',
    )
    low_root: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name='Low Root',
        description='Deprecated — legacy organizer empty; export naming uses low_collection',
    )
    high_collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name='High Collection',
        description='Role subcollection ({name}_high/) — export-facing high stem',
    )
    low_collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name='Low Collection',
        description='Role subcollection ({name}_low/) — export-facing low stem',
    )
    high_assigned: bpy.props.BoolProperty(name='High Assigned', default=False)
    low_assigned: bpy.props.BoolProperty(name='Low Assigned', default=False)
    status_prepped: bpy.props.BoolProperty(name='Prepped', default=False)
    status_baked: bpy.props.BoolProperty(name='Baked', default=False)
    resolution_override: bpy.props.IntProperty(
        name='Resolution Override',
        description='Bake texture resolution for this group (0 = use project default)',
        default=0,
        min=0,
    )
    bake_samples_override: bpy.props.IntProperty(
        name='Samples Override',
        description='Cycles bake samples for this group (0 = use project default)',
        default=0,
        min=0,
    )
    sources_collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name='Group Collection',
        description='Bake group folder ({name}_BakeGroup/) — staging objects link here directly',
    )
    ui_list_slots: bpy.props.CollectionProperty(type=LKS_PG_BakeGroupUiSlot)
    active_high_index: bpy.props.IntProperty(
        name='Active High',
        default=0,
        min=0,
        update=_on_bake_group_high_index_changed,
    )
    active_low_index: bpy.props.IntProperty(
        name='Active Low',
        default=0,
        min=0,
        update=_on_bake_group_low_index_changed,
    )
    export_mode: bpy.props.EnumProperty(
        name='Export Mode',
        description='Default FBX packaging when exporting this bake group',
        items=BAKE_EXPORT_MODE_ITEMS,
        default=BAKE_EXPORT_MODE_DEFAULT,
    )


def _on_bake_project_name_changed(
    self: LKS_PG_BakeProject,
    context: bpy.types.Context,
) -> None:
    """Rename root collection and refresh default output_dir when RNA name edits."""
    from .helpers_bake_cleanup import rename_bake_project

    rename_bake_project(self, context.scene)


def _sync_active_project_from_group_index(
    self: LKS_PG_BakeProject,
    context: bpy.types.Context,
) -> None:
    """Selecting a group row in the outliner also activates its parent project."""
    scene = context.scene
    for index, scene_project in enumerate(scene.lks_bake_projects):
        if scene_project == self:
            scene.lks_active_bake_project_index = index
            return


def _on_bake_project_image_file_type_changed(
    self: LKS_PG_BakeProject,
    context: bpy.types.Context,
) -> None:
    valid = valid_bake_image_color_depths(self.lks_image_file_type)
    if self.lks_image_color_depth not in valid:
        self.lks_image_color_depth = bake_image_color_depth_default_for_file_type(
            self.lks_image_file_type,
        )


def _bake_project_image_color_depth_items(
    self: LKS_PG_BakeProject,
    context: bpy.types.Context,
):
    return bake_image_color_depth_items_for_file_type(self.lks_image_file_type)


def _on_bake_project_default_resolution_linked_changed(
    self: LKS_PG_BakeProject,
    context: bpy.types.Context,
) -> None:
    if self.default_resolution_linked:
        sync_linked_resolution_axis(
            self,
            source_axis='x',
            x_prop='default_resolution_x',
            y_prop='default_resolution_y',
            linked_prop='default_resolution_linked',
        )


def _on_bake_project_default_resolution_x_changed(
    self: LKS_PG_BakeProject,
    context: bpy.types.Context,
) -> None:
    sync_linked_resolution_axis(
        self,
        source_axis='x',
        x_prop='default_resolution_x',
        y_prop='default_resolution_y',
        linked_prop='default_resolution_linked',
    )


def _on_bake_project_default_resolution_y_changed(
    self: LKS_PG_BakeProject,
    context: bpy.types.Context,
) -> None:
    sync_linked_resolution_axis(
        self,
        source_axis='y',
        x_prop='default_resolution_x',
        y_prop='default_resolution_y',
        linked_prop='default_resolution_linked',
    )


class LKS_PG_BakeProject(bpy.types.PropertyGroup):
    """Scene-level bake project definition."""

    name: bpy.props.StringProperty(
        name='Name',
        default='BakeProject',
        update=_on_bake_project_name_changed,
    )
    root_collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name='Root Collection',
    )
    output_dir: bpy.props.StringProperty(
        name='Output Directory',
        default='//_bake/',
        subtype='DIR_PATH',
    )
    lks_material_prefix: bpy.props.StringProperty(
        name='Material Prefix',
        description=(
            'Prepended to baker-managed low material and texture filenames; '
            'empty uses scene material prefix'
        ),
        default='',
    )
    lks_material_suffix: bpy.props.StringProperty(
        name='Material Suffix',
        description='Appended to baker-managed low material and texture filenames',
        default=BAKE_LOW_MATERIAL_SUFFIX,
    )
    lks_image_file_type: bpy.props.EnumProperty(
        name='Image File Type',
        description='File format for baked texture images on disk',
        items=BAKE_IMAGE_FILE_TYPE_ITEMS,
        default=BAKE_IMAGE_FILE_TYPE_DEFAULT,
        update=_on_bake_project_image_file_type_changed,
    )
    lks_image_color_depth: bpy.props.EnumProperty(
        name='Bit Depth',
        description='Bit depth per channel when saving baked textures',
        items=_bake_project_image_color_depth_items,
        default=1,
    )
    bake_mode: bpy.props.EnumProperty(
        name='Bake Mode',
        items=BAKE_MODE_ITEMS,
        default='HIGH_LOW',
    )
    export_mode: bpy.props.EnumProperty(
        name='Export Mode',
        description='Default FBX packaging when exporting this bake project',
        items=BAKE_EXPORT_MODE_ITEMS,
        default=BAKE_EXPORT_MODE_DEFAULT,
    )
    default_resolution_x: make_resolution_enum_property(
        name='Default Resolution X',
        description='Default bake texture width (power of two)',
        update=_on_bake_project_default_resolution_x_changed,
    )
    default_resolution_y: make_resolution_enum_property(
        name='Default Resolution Y',
        description='Default bake texture height (power of two)',
        update=_on_bake_project_default_resolution_y_changed,
    )
    default_resolution_linked: bpy.props.BoolProperty(
        name='Link Resolution',
        description='Keep width and height the same',
        default=True,
        update=_on_bake_project_default_resolution_linked_changed,
    )
    default_bake_samples: bpy.props.IntProperty(
        name='Default Bake Samples',
        default=16,
        min=1,
    )
    default_bake_margin: bpy.props.IntProperty(
        name='Default Bake Margin',
        description=(
            'Project-level default margin: 0 = no dilation (skip); '
            '-1 = infinite fill to image bounds; N > 0 = explicit pixel margin'
        ),
        default=BAKE_MARGIN_DEFAULT,
        min=-1,
    )
    default_bake_margin_pre_erode: bpy.props.IntProperty(
        name='Default Margin Pre-Erode',
        description=(
            'Shrink dilate seed mask inward before margin fill (pixels): '
            '0 = off; N > 0 = ignore N px of aliased UV rim when sampling colors'
        ),
        default=BAKE_MARGIN_PRE_ERODE_DEFAULT,
        min=0,
        max=32,
    )
    cage_extrusion: bpy.props.FloatProperty(name='Cage Extrusion', default=0.01, min=0.0)
    max_ray_distance: bpy.props.FloatProperty(name='Max Ray Distance', default=0.0, min=0.0)
    use_cage: bpy.props.BoolProperty(name='Use Cage', default=True)
    use_gpu_bake: bpy.props.BoolProperty(name='GPU Bake', default=True)
    bake_groups: bpy.props.CollectionProperty(type=LKS_PG_BakeGroup)
    active_bake_group_index: bpy.props.IntProperty(
        name='Active Bake Group',
        default=0,
        min=0,
        update=_sync_active_project_from_group_index,
    )
    map_entries: bpy.props.CollectionProperty(type=LKS_PG_BakeMapEntry)
    active_bake_map_index: bpy.props.IntProperty(
        name='Active Bake Map',
        default=0,
        min=0,
    )
    lks_preview_map_id: bpy.props.StringProperty(
        name='Preview Map',
        description='Active solo eyeball preview map_id; empty = composite view',
        default='',
    )


_BAKE_PG_CLASSES: tuple[type, ...] = (
    LKS_PG_CurvatureSoftSettings,
    LKS_PG_CurvatureLegacySettings,
    LKS_PG_BentNormalSettings,
    LKS_PG_BentNormalObjectSettings,
    LKS_PG_LightingBakeSettings,
    LKS_PG_BakeMapEntry,
    LKS_PG_BakeGroupUiSlot,
    LKS_PG_BakeGroup,
    LKS_PG_BakeProject,
)

_SCENE_PROP_NAMES: tuple[str, ...] = (
    'lks_bake_projects',
    'lks_active_bake_project_index',
)


def read_active_bake_project_index(scene: bpy.types.Scene) -> int:
    """Return clamped active project index without mutating scene RNA."""
    projects = scene.lks_bake_projects
    if len(projects) == 0:
        return 0
    return min(
        max(scene.lks_active_bake_project_index, 0),
        len(projects) - 1,
    )


def clamp_active_bake_project_index(scene: bpy.types.Scene) -> None:
    """Keep active project index valid after list edits (operators only)."""
    scene.lks_active_bake_project_index = read_active_bake_project_index(scene)


def read_active_bake_group_index(project: LKS_PG_BakeProject) -> int:
    """Return clamped active group index without mutating project RNA."""
    groups = project.bake_groups
    if len(groups) == 0:
        return 0
    return min(
        max(project.active_bake_group_index, 0),
        len(groups) - 1,
    )


def clamp_active_bake_group_index(project: LKS_PG_BakeProject) -> None:
    """Keep active bake group index valid after list edits."""
    project.active_bake_group_index = read_active_bake_group_index(project)


def read_active_bake_map_index(project: LKS_PG_BakeProject) -> int:
    """Return clamped active map entry index without mutating project RNA."""
    entries = project.map_entries
    if len(entries) == 0:
        return 0
    return min(
        max(project.active_bake_map_index, 0),
        len(entries) - 1,
    )


def clamp_active_bake_map_index(project: LKS_PG_BakeProject) -> None:
    """Keep active bake map index valid after list edits."""
    project.active_bake_map_index = read_active_bake_map_index(project)


def get_active_bake_project(
    scene: bpy.types.Scene,
    *,
    write_back: bool = False,
) -> LKS_PG_BakeProject | None:
    """Return the active bake project RNA row, or None."""
    if write_back:
        clamp_active_bake_project_index(scene)
    index = read_active_bake_project_index(scene)
    projects = scene.lks_bake_projects
    if 0 <= index < len(projects):
        return projects[index]
    return None


def _on_active_bake_project_index_changed(
    self: bpy.types.Scene,
    context: bpy.types.Context,
) -> None:
    """Re-wire low material when the active bake project changes in the UI."""
    scene = context.scene if context is not None else self
    index = read_active_bake_project_index(scene)
    projects = scene.lks_bake_projects
    if not (0 <= index < len(projects)):
        return
    from .static_utilities.bake_map_catalog import seed_bake_project_map_entries_if_needed
    from .helpers_bake_run import refresh_bake_project_low_material

    project = projects[index]
    seed_bake_project_map_entries_if_needed(project)
    refresh_bake_project_low_material(scene, project)


def register_props() -> None:
    for cls in _BAKE_PG_CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.lks_bake_projects = bpy.props.CollectionProperty(
        type=LKS_PG_BakeProject,
    )
    bpy.types.Scene.lks_active_bake_project_index = bpy.props.IntProperty(
        name='Active Bake Project',
        default=0,
        min=0,
        update=_on_active_bake_project_index_changed,
    )


def unregister_props() -> None:
    for prop_name in reversed(_SCENE_PROP_NAMES):
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)

    for cls in reversed(_BAKE_PG_CLASSES):
        bpy.utils.unregister_class(cls)

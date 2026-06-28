"""Shared identifiers and paths used across LKS Ops."""

import math

# Mesh attributes
ATTR_SCULPT_FACE_SET = ".sculpt_face_set"

# UV layer naming (index 0 = active bake / viewport layer)
DEFAULT_UV_LAYER_NAMES: tuple[str, ...] = ('UVMap', 'Lightmap', 'Trim')
BAKE_UV_LAYER_COUNT = 1
ATTR_CREASE_EDGE = "crease_edge"
ATTR_SHADER_BEVEL_SIZE = "LKS Shader Bevel Size"

# Shader bevel node graph
NODE_NAME_SHADER_BEVEL = "LKS Shader Bevel"
NODE_NAME_SHADER_BEVEL_ATTR = "LKS Shader Bevel Attr"
MAT_NAME_DEFAULT_BEVEL = "LKS Default Bevel Material"

# Vertex colors and preview materials
MAT_VCOL_CURVATURE = "M_Vcol_Curvature"
VCOL_DEFAULT_NAME = "Col"
VCOL_OUTLINE_NAME = "Outline"

# Collision
MAT_UCX = "UCX_Material"
PREFIX_UCX = "UCX_"
PREFIX_UBX = "UBX_"
PREFIX_USP = "USP_"

# Custom subdiv geometry nodes
SUBDIV_GEO_NODES_GROUP = "LKS_CustomSubdiv_Mod"
SUBDIV_MODIFIER_NAME = "LKS_CustomSubdiv"
SUBDIV_NODE_GROUP_BLEND = "./assets/node_groups.blend"
SUBDIV_SOCKET_BASE = "Input_2"
SUBDIV_SOCKET_CREASE = "Input_3"
SUBDIV_SOCKET_POST_CREASE = "Input_4"

# Floater workflow
FLOATER_VG_SHRINKWRAP = "FloaterShrinkwrapGp"
FLOATER_VG_TRANSFER = "FloaterTransferGp"
FLOATER_MOD_SHRINKWRAP = "Floater_Shrinkwrap"
FLOATER_MOD_DISPLACE = "Floater_Displace"
FLOATER_MOD_DATA_TRANSFER = "Floater_DataTransfer"
FLOATER_OBJECT_PREFIX = "Floater_"
FLOATER_DEFORM_PLANE_PREFIX = "Floater_DeformPlane_"
FLOATER_MOD_SOLIDIFY = "Floater_Solidify"
FLOATER_MOD_MESH_DEFORM = "Floater_MeshDeform"
# Data Transfer loop types (Blender 5.1+: VCOL renamed to COLOR_CORNER)
FLOATER_DATA_TRANSFER_LOOP_TYPES = frozenset({"CUSTOM_NORMAL", "COLOR_CORNER"})

# Mirror / symmetry modifier names
# Primary name for the first stacked mirror; Blender appends .001, .002, … for each
# additional mirror created via modifiers.new(MOD_NAME_MIRROR, 'MIRROR').
MOD_NAME_MIRROR = "LKS Mirror"
LEGACY_MOD_NAME_MIRROR = "LKS_Symmetry"

# Group Pro
GPRO_INSTANCE_MOD = "GPro_Instance"
GPRO_COLL_SOCKET = "Socket_2"
COLINST_EXTRACTED_SUFFIX = "_extracted"

# Thumbnail rendering
MAT_THUMBNAIL = "Thumbnail_Mat"

# Normal Ops modifier names
MOD_NAME_NORMALS_SMOOTH_BY_ANGLE = "LKS Smooth By Angle"
MOD_NAME_NORMALS_WEIGHTED_NORMAL = "LKS Weighted Normal"
MOD_NAME_NORMALS_TRIANGULATE = "LKS Triangulate"

# Legacy Normal Ops modifier names (removed on clear / migrated on apply)
LEGACY_MOD_NAME_NORMALS_SMOOTH_BY_ANGLE = "LKS Normals Smooth By Angle"
LEGACY_MOD_NAME_NORMALS_WEIGHTED_NORMAL = "LKS Normals Weighted Normal"
LEGACY_MOD_NAME_NORMALS_TRIANGULATE = "LKS Normals Triangulate"

# Bevel Ops modifier names
MOD_NAME_BEVEL_LIMIT = "LKS Bevel Limit"
MOD_NAME_BEVEL_ANGLE = "LKS Bevel Angle"
LEGACY_MOD_NAME_BEVEL = "LKS Bevel"
MOD_NAME_BEVEL_SUBSURF = "LKS Subsurf"
MOD_NAME_BEVEL_DYNA_REMESH = "LKS Dynamesh Remesh"
MOD_NAME_BEVEL_DYNA_SMOOTH = "LKS Dynamesh Smooth"
MOD_NAME_BEVEL_DYNA_DECIMATE = "LKS Dynamesh Decimate"

# Legacy Bevel Ops modifier names (migrated on apply)
LEGACY_BEVEL_MOD_FWN_WEIGHT = "FWN_Bevel_Weight"
LEGACY_BEVEL_MOD_FWN_ANGLE = "FWN_Bevel_Angle"
LEGACY_BEVEL_MOD_FWN_WEIGHTED_NORMAL = "FWN_WeightedNormal"
LEGACY_BEVEL_MOD_FWN_TRIANGULATE = "FWN_Triangulate"
LEGACY_BEVEL_MOD_SUBSURF_BEVEL = "Subsurf_Bevel_OffsetLoops"
LEGACY_BEVEL_MOD_SUBSURF = "Subsurf_Base"
LEGACY_BEVEL_MOD_SUBSURF_WEIGHTED_NORMAL = "Subsurf_WeightedNormal"
LEGACY_BEVEL_MOD_DYNA_REMESH = "dynamesh_remesh"
LEGACY_BEVEL_MOD_DYNA_SMOOTH = "dynamesh_smooth"
LEGACY_BEVEL_MOD_DYNA_DECIMATE = "dynamesh_decimate"
LEGACY_BEVEL_MOD_DYNA_WEIGHTED_NORMAL = "dynamesh_weightedNormal"
LEGACY_BEVEL_MOD_AUTO_SMOOTH = "Auto Smooth"

# Bevel Ops hardcoded defaults
BEVEL_SMOOTH_ANGLE = math.pi
BEVEL_ANGLE_DEFAULT = math.radians(30.0)
BEVEL_ANGLE_SIZE_DEFAULT = 0.01
BEVEL_CUSP_ANGLE_DEFAULT = math.radians(30.0)
BEVEL_SEGMENTS_FWN = 1
BEVEL_SEGMENTS_SUBSURF = 2
BEVEL_PROFILE_FWN = 0.5
BEVEL_PROFILE_SUBSURF = 1.0
BEVEL_TRI_MIN_VERTICES_DEFAULT = 4

# Bake project lowpoly material (one texture set per project; export stem = RNA name)
BAKE_LOW_MATERIAL_DEFAULT_PREFIX = 'MI_'
BAKE_LOW_MATERIAL_SUFFIX = ''
BAKE_IMAGE_FILE_TYPE_DEFAULT = 'PNG'
BAKE_IMAGE_FILE_TYPE_ITEMS: tuple[tuple[str, str, str, int], ...] = (
    ('PNG', 'PNG', 'PNG image (lossless)', 0),
    ('JPEG', 'JPEG', 'JPEG image', 1),
    ('TGA', 'TGA', 'Targa image', 2),
    ('TIFF', 'TIFF', 'TIFF image', 3),
    ('EXR', 'OpenEXR', 'OpenEXR HDR image', 4),
)
BAKE_IMAGE_FILE_TYPE_EXTENSIONS: dict[str, str] = {
    'PNG': 'png',
    'JPEG': 'jpg',
    'TGA': 'tga',
    'TIFF': 'tif',
    'EXR': 'exr',
}
BAKE_IMAGE_BLENDER_FILE_FORMAT: dict[str, str] = {
    'PNG': 'PNG',
    'JPEG': 'JPEG',
    'TGA': 'TARGA',
    'TIFF': 'TIFF',
    'EXR': 'OPEN_EXR',
}
BAKE_IMAGE_COLOR_DEPTH_DEFAULT = '16'
BAKE_IMAGE_COLOR_DEPTHS_BY_FILE_TYPE: dict[str, tuple[tuple[str, str, str, int], ...]] = {
    'PNG': (
        ('8', '8-bit', 'Standard 8-bit PNG', 0),
        ('16', '16-bit', '16-bit PNG (recommended for bakes)', 1),
    ),
    'JPEG': (
        ('8', '8-bit', '8-bit JPEG (lossy)', 0),
    ),
    'TGA': (
        ('8', '8-bit', '8-bit Targa', 0),
    ),
    'TIFF': (
        ('8', '8-bit', '8-bit TIFF', 0),
        ('16', '16-bit', '16-bit TIFF', 1),
    ),
    'EXR': (
        ('16', 'Half', 'OpenEXR half precision (16-bit float)', 0),
        ('32', 'Float', 'OpenEXR full float (32-bit)', 1),
    ),
}
BAKE_IMAGE_COLOR_DEPTH_DEFAULTS_BY_FILE_TYPE: dict[str, str] = {
    'PNG': '16',
    'JPEG': '8',
    'TGA': '8',
    'TIFF': '16',
    'EXR': '16',
}
BAKE_IMAGE_SAVE_SCENE_NAME = '_lks_bake_image_save'

LKS_BAKE_EXPORT_TEMP_KEY = 'lks_bake_export_temp'

BAKE_PREP_COLLECTION_STEM = '_BAKE_PREP'


def is_bake_prep_collection_name(name: str) -> bool:
    """True for project/role temp folders named ``_BAKE_PREP`` or Blender-uniquified variants."""
    if name == BAKE_PREP_COLLECTION_STEM:
        return True
    return name.startswith(f'{BAKE_PREP_COLLECTION_STEM}.')


BAKE_TEXTURE_RESOLUTION_MIN = 64
BAKE_TEXTURE_RESOLUTION_MAX = 8192
BAKE_TEXTURE_RESOLUTION_DEFAULT = 2048
BAKE_TEXTURE_RESOLUTION_VALUES: tuple[int, ...] = (
    64,
    128,
    256,
    512,
    1024,
    2048,
    4096,
    8192,
)
BAKE_TEXTURE_RESOLUTION_ITEMS: tuple[tuple[str, str, str, int], ...] = tuple(
    (str(value), str(value), f'{value} px', index)
    for index, value in enumerate(BAKE_TEXTURE_RESOLUTION_VALUES)
)

BAKE_MARGIN_DEFAULT = 16
BAKE_MARGIN_NONE = 0
BAKE_MARGIN_INFINITE = -1
BAKE_CYCLES_MARGIN_CAP = 64

BAKE_BACKEND_PREFERENCE_DEFAULT = 'AUTO'
BAKE_BACKEND_PREFERENCE_ITEMS: tuple[tuple[str, str, str, int], ...] = (
    ('AUTO', 'Auto', 'Derive when inputs exist; otherwise mesh bake', 0),
    ('MESH_ONLY', 'Mesh Only', 'Force selected-to-active Cycles / EMIT bake', 1),
    ('DERIVE_ONLY', 'Derive Only', 'Fast 2D derive only; error if inputs missing', 2),
)

# When True, baker curvature derive returns flat mid-gray (legacy escape hatch).
BAKE_CURVATURE_STUB_ENABLED = False

# When True, curvature derive delegates to bake_ops engine (see blender/curvature_bridge).
BAKE_CURVATURE_USE_BAKE_ENGINE = False
BAKE_CURVATURE_ENGINE_METHOD = 'soft_curvature'
BAKE_CURVATURE_ENGINE_DEVICE = 'cpu'  # cpu | gpu | auto — production bakes are usually background

BAKE_CURVATURE_METHOD_DEFAULT = 'SD'
BAKE_CURVATURE_METHOD_ITEMS: tuple[tuple[str, str, str, int], ...] = (
    ('SD', 'Substance Designer', 'Disk-ray / blur sampling with per-tile tonemap', 0),
    ('MULTISCALE', 'Multiscale', 'Legacy multiscale edge accumulation (max-pool radii)', 1),
    ('SINGLE_SCALE', 'Single Scale', 'Fast neighbor-difference (legacy)', 2),
    (
        'SOFT_CURVATURE',
        'Soft Curvature',
        'Multi-scale soft curvature from low mesh + object normals (bake engine)',
        3,
    ),
)
# Per-map UI methods routed through bake_engine (see blender/curvature_bridge.py).
BAKE_CURVATURE_UI_ENGINE_METHODS: dict[str, str] = {
    'SOFT_CURVATURE': 'soft_curvature',
}
BAKE_CURVATURE_DEVICE_DEFAULT = 'AUTO'
BAKE_CURVATURE_DEVICE_ITEMS: tuple[tuple[str, str, str, int], ...] = (
    ('AUTO', 'Auto', 'GPU when available, otherwise CPU', 0),
    ('GPU', 'GPU', 'Blender GPU offscreen shaders', 1),
    ('CPU', 'CPU', 'CPU reference path (slower)', 2),
)
BAKE_CURVATURE_UNITIZE_DEFAULT = True
BAKE_CURVATURE_UNITIZE_FLOOR = 1e-8
BAKE_CURVATURE_UNITIZE_CONTRAST = 0.72
BAKE_CURVATURE_UNITIZE_PERCENTILE = 0.95
BAKE_CURVATURE_MAGNITUDE_GAIN = 2.0
BAKE_CURVATURE_MULTISCALE_RADII: tuple[int, ...] = (1, 2, 4, 8, 16)
BAKE_CURVATURE_FINEST_SIGN_EPS = 0.02
BAKE_CURVATURE_COARSE_SIGN_RADIUS = 8
BAKE_CURVATURE_FLAT_FACE_ALIGN = 0.92
BAKE_CURVATURE_POST_SMOOTH_RADIUS = 0
# Substance Designer Curvature baker settings (see curvature_lab/sd_curvature.py).
BAKE_CURVATURE_SECONDARY_RAYS = 256
BAKE_CURVATURE_SAMPLING_RADIUS = 0.01
BAKE_CURVATURE_TONEMAP_PERCENTILE = 0.995
BAKE_CURVATURE_RELATIVE_TO_BBOX = True
BAKE_CURVATURE_AUTO_TONEMAP_PER_TILE = True
BAKE_CURVATURE_TONEMAP_MIN = -1.0
BAKE_CURVATURE_TONEMAP_MAX = 1.0
BAKE_CURVATURE_GEOM_BLUR_RADIUS = 8
BAKE_CURVATURE_CONVEXITY_SIGN = 1.0
# When |dot(n_detail, n_geom)| is below this, sign uses component Laplacian along detail N.
BAKE_CURVATURE_GEOM_ALIGN_THRESHOLD = 0.85

BAKE_MAP_RENDER_TOOLTIP = (
    'Bake this map for the active project. Reuses existing dependency maps on disk when possible.'
)
BAKE_MAP_RENDER_CTRL_TOOLTIP = 'Ctrl+Click: rebuild all dependent maps from scratch.'

BAKE_EXPORT_MODE_DEFAULT = 'ONE_FBX'
BAKE_EXPORT_MODE_ITEMS: tuple[tuple[str, str, str, int], ...] = (
    ('ONE_FBX', 'One FBX', 'Single FBX; collections become parented empties', 0),
    (
        'HIGHS_AND_LOWS',
        'Highs and Lows',
        'Separate high and low FBX files per bake group',
        1,
    ),
)

# Bake / deep triangulation (TriangulateModifier RNA identifiers)
TRIANGULATE_QUAD_METHOD_DEFAULT = 'FIXED'
# Ngon RNA has no FIXED — CLIP is the deterministic alternative to Beauty.
TRIANGULATE_NGON_METHOD_DEFAULT = 'CLIP'
TRIANGULATE_QUAD_METHOD_ITEMS = (
    ('BEAUTY', 'Beauty', 'Split along the most attractive diagonal'),
    ('FIXED', 'Fixed', 'Fixed triangulation pattern for WYSIWYG bakes'),
    ('FIXED_ALTERNATE', 'Fixed Alternate', 'Fixed pattern with alternate diagonal'),
    ('SHORTEST_DIAGONAL', 'Shortest Diagonal', 'Split along the shortest diagonal'),
    ('LONGEST_DIAGONAL', 'Longest Diagonal', 'Split along the longest diagonal'),
)
TRIANGULATE_NGON_METHOD_ITEMS = (
    ('BEAUTY', 'Beauty', 'Split along the most attractive edges'),
    ('CLIP', 'Clip', 'Split along bound edges'),
)

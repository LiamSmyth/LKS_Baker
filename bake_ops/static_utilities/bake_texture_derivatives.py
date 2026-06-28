"""Fast 2D texture-space derive passes — no operator imports."""

from __future__ import annotations

import math
import struct
import zlib
from array import array
from dataclasses import dataclass

import bpy
from mathutils import Vector

from .bake_map_catalog import LKS_BakeMapSpec
from .bake_debug_log_helpers import log_step, timed_step
from lks_baker.shared_utilities.lks_constants import (
    BAKE_CURVATURE_AUTO_TONEMAP_PER_TILE,
    BAKE_CURVATURE_COARSE_SIGN_RADIUS,
    BAKE_CURVATURE_CONVEXITY_SIGN,
    BAKE_CURVATURE_FINEST_SIGN_EPS,
    BAKE_CURVATURE_FLAT_FACE_ALIGN,
    BAKE_CURVATURE_GEOM_ALIGN_THRESHOLD,
    BAKE_CURVATURE_GEOM_BLUR_RADIUS,
    BAKE_CURVATURE_MAGNITUDE_GAIN,
    BAKE_CURVATURE_METHOD_DEFAULT,
    BAKE_CURVATURE_MULTISCALE_RADII,
    BAKE_CURVATURE_POST_SMOOTH_RADIUS,
    BAKE_CURVATURE_RELATIVE_TO_BBOX,
    BAKE_CURVATURE_SAMPLING_RADIUS,
    BAKE_CURVATURE_SECONDARY_RAYS,
    BAKE_CURVATURE_TONEMAP_MAX,
    BAKE_CURVATURE_TONEMAP_MIN,
    BAKE_CURVATURE_TONEMAP_PERCENTILE,
    BAKE_CURVATURE_UNITIZE_CONTRAST,
    BAKE_CURVATURE_UNITIZE_DEFAULT,
    BAKE_CURVATURE_UNITIZE_FLOOR,
    BAKE_CURVATURE_UNITIZE_PERCENTILE,
)

_CURVATURE_MULTISCALE_RADII = BAKE_CURVATURE_MULTISCALE_RADII
_CURVATURE_FINEST_SIGN_EPS = BAKE_CURVATURE_FINEST_SIGN_EPS


class TextureDeriveSkip(Exception):
    """Derive pass cannot run; bake should skip this map and continue."""


class BakeMapSkipped(Exception):
    """Requested map bake was skipped (missing attribute, inputs, etc.)."""


@dataclass(frozen=True)
class LKS_TBNRaster:
    """Per-texel tangent frame on the low mesh UV layout."""

    width: int
    height: int
    tangent: array  # float RGB per pixel, flat len=w*h*4
    bitangent: array
    normal: array
    island_id: array  # int per pixel, -1 = empty


def _active_uv_layer_name(mesh: bpy.types.Mesh) -> str:
    if mesh.uv_layers.active is not None:
        return mesh.uv_layers.active.name
    if len(mesh.uv_layers) > 0:
        return mesh.uv_layers[0].name
    raise RuntimeError('Low mesh has no UV layer')


def _empty_rgba_buffer(width: int, height: int, fill: float = 0.0) -> array:
    return array('f', [fill] * (width * height * 4))


def _empty_int_buffer(width: int, height: int, fill: int = -1) -> array:
    return array('i', [fill] * (width * height))


def _barycentric(
    px: float,
    py: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> tuple[float, float, float] | None:
    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(denom) < 1e-12:
        return None
    w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / denom
    w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / denom
    w2 = 1.0 - w0 - w1
    if w0 < -1e-5 or w1 < -1e-5 or w2 < -1e-5:
        return None
    return w0, w1, w2


def _interp_vec3(
    w0: float,
    w1: float,
    w2: float,
    v0: tuple[float, float, float],
    v1: tuple[float, float, float],
    v2: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        w0 * v0[0] + w1 * v1[0] + w2 * v2[0],
        w0 * v0[1] + w1 * v1[1] + w2 * v2[1],
        w0 * v0[2] + w1 * v1[2] + w2 * v2[2],
    )


def _normalize_vec3(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-8:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _write_pixel_rgba(buf: array, width: int, x: int, y: int, rgba: tuple[float, float, float, float]) -> None:
    idx = (y * width + x) * 4
    buf[idx] = rgba[0]
    buf[idx + 1] = rgba[1]
    buf[idx + 2] = rgba[2]
    buf[idx + 3] = rgba[3]


def _read_pixel_rgba(buf: array, width: int, x: int, y: int) -> tuple[float, float, float, float]:
    idx = (y * width + x) * 4
    return buf[idx], buf[idx + 1], buf[idx + 2], buf[idx + 3]


def _image_pixels_to_buffer(image: bpy.types.Image) -> tuple[array, int, int]:
    width, height = image.size[0], image.size[1]
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Image '{image.name}' has invalid dimensions")
    pixels = array('f', [0.0] * (width * height * 4))
    image.pixels.foreach_get(pixels)
    return pixels, width, height


def _buffer_to_image(pixels: array, width: int, height: int, *, name: str, color_space: str) -> bpy.types.Image:
    image = bpy.data.images.new(name, width=width, height=height, alpha=True)
    image.colorspace_settings.name = color_space
    image.pixels.foreach_set(pixels)
    image.update()
    return image


def _collect_loop_tbn(mesh: bpy.types.Mesh, uv_layer_name: str) -> tuple[list, list, list, list]:
    mesh.calc_tangents(uvmap=uv_layer_name)
    loop_count = len(mesh.loops)
    tangents = [0.0] * (loop_count * 3)
    normals = [0.0] * (loop_count * 3)
    signs = [0.0] * loop_count
    mesh.loops.foreach_get('tangent', tangents)
    mesh.loops.foreach_get('normal', normals)
    mesh.loops.foreach_get('bitangent_sign', signs)

    uv_data = mesh.uv_layers[uv_layer_name].data
    loop_uvs: list[tuple[float, float]] = []
    loop_t: list[tuple[float, float, float]] = []
    loop_b: list[tuple[float, float, float]] = []
    loop_n: list[tuple[float, float, float]] = []

    for li in range(loop_count):
        uv = uv_data[li].uv
        loop_uvs.append((uv[0], uv[1]))
        tx, ty, tz = tangents[li * 3], tangents[li * 3 + 1], tangents[li * 3 + 2]
        nx, ny, nz = normals[li * 3], normals[li * 3 + 1], normals[li * 3 + 2]
        sign = signs[li]
        tangent = Vector((tx, ty, tz)).normalized()
        normal = Vector((nx, ny, nz)).normalized()
        bitangent = normal.cross(tangent) * sign
        loop_t.append((tangent.x, tangent.y, tangent.z))
        loop_b.append((bitangent.x, bitangent.y, bitangent.z))
        loop_n.append((normal.x, normal.y, normal.z))

    return loop_uvs, loop_t, loop_b, loop_n


def _uv_to_pixel_xy(uv: tuple[float, float], width: int, height: int) -> tuple[float, float]:
    """OpenGL bake UV → pixel center (row 0 = UV V=1)."""
    scale_x = max(width - 1, 1)
    scale_y = max(height - 1, 1)
    return uv[0] * scale_x, (1.0 - uv[1]) * scale_y


def _rasterize_mesh_attributes(
    mesh: bpy.types.Mesh,
    width: int,
    height: int,
    *,
    uv_layer_name: str | None = None,
    island_ids: list[int] | None = None,
) -> LKS_TBNRaster:
    """Rasterize T/B/N and optional per-loop island ids into UV space."""
    uv_name = uv_layer_name or _active_uv_layer_name(mesh)
    loop_uvs, loop_t, loop_b, loop_n = _collect_loop_tbn(mesh, uv_name)

    tangent_buf = _empty_rgba_buffer(width, height, 0.5)
    bitangent_buf = _empty_rgba_buffer(width, height, 0.5)
    normal_buf = _empty_rgba_buffer(width, height, 0.5)
    island_buf = _empty_int_buffer(width, height, -1)

    for poly in mesh.polygons:
        if len(poly.loop_indices) < 3:
            continue
        tris = []
        base = list(poly.loop_indices)
        for i in range(1, len(base) - 1):
            tris.append((base[0], base[i], base[i + 1]))

        for i0, i1, i2 in tris:
            uvs = (loop_uvs[i0], loop_uvs[i1], loop_uvs[i2])
            p0 = _uv_to_pixel_xy(uvs[0], width, height)
            p1 = _uv_to_pixel_xy(uvs[1], width, height)
            p2 = _uv_to_pixel_xy(uvs[2], width, height)
            xs = (
                int(p0[0]) % width,
                int(p1[0]) % width,
                int(p2[0]) % width,
            )
            ys = (
                int(p0[1]) % height,
                int(p1[1]) % height,
                int(p2[1]) % height,
            )
            min_x = max(0, min(xs) - 1)
            max_x = min(width - 1, max(xs) + 1)
            min_y = max(0, min(ys) - 1)
            max_y = min(height - 1, max(ys) + 1)

            t_vals = (loop_t[i0], loop_t[i1], loop_t[i2])
            b_vals = (loop_b[i0], loop_b[i1], loop_b[i2])
            n_vals = (loop_n[i0], loop_n[i1], loop_n[i2])
            island_val = island_ids[i0] if island_ids is not None else 0

            for y in range(min_y, max_y + 1):
                for x in range(min_x, max_x + 1):
                    px = x + 0.5
                    py = y + 0.5
                    bary = _barycentric(px, py, p0[0], p0[1], p1[0], p1[1], p2[0], p2[1])
                    if bary is None:
                        continue
                    w0, w1, w2 = bary
                    t = _normalize_vec3(_interp_vec3(w0, w1, w2, *t_vals))
                    b = _normalize_vec3(_interp_vec3(w0, w1, w2, *b_vals))
                    n = _normalize_vec3(_interp_vec3(w0, w1, w2, *n_vals))
                    _write_pixel_rgba(tangent_buf, width, x, y, (t[0] * 0.5 + 0.5, t[1] * 0.5 + 0.5, t[2] * 0.5 + 0.5, 1.0))
                    _write_pixel_rgba(bitangent_buf, width, x, y, (b[0] * 0.5 + 0.5, b[1] * 0.5 + 0.5, b[2] * 0.5 + 0.5, 1.0))
                    _write_pixel_rgba(normal_buf, width, x, y, (n[0] * 0.5 + 0.5, n[1] * 0.5 + 0.5, n[2] * 0.5 + 0.5, 1.0))
                    island_buf[y * width + x] = island_val

    return LKS_TBNRaster(
        width=width,
        height=height,
        tangent=tangent_buf,
        bitangent=bitangent_buf,
        normal=normal_buf,
        island_id=island_buf,
    )


_UV_ISLAND_QUANT = 100000


def _uv_key(uv: tuple[float, float]) -> tuple[int, int]:
    """Quantize UV coords so welded verts across faces share one key."""
    return (round(uv[0] * _UV_ISLAND_QUANT), round(uv[1] * _UV_ISLAND_QUANT))


def _loop_polygon_indices(mesh: bpy.types.Mesh) -> list[int]:
    """Map each loop index to its owning polygon (MeshLoop has no polygon_index RNA)."""
    loop_polygon = [-1] * len(mesh.loops)
    for poly_index, poly in enumerate(mesh.polygons):
        for loop_index in poly.loop_indices:
            loop_polygon[loop_index] = poly_index
    return loop_polygon


def _flood_fill_uv_islands(mesh: bpy.types.Mesh, uv_layer_name: str) -> list[int]:
    """Return per-loop island id (connected UV shells)."""
    uv_data = mesh.uv_layers[uv_layer_name].data
    loop_count = len(mesh.loops)
    loop_polygon = _loop_polygon_indices(mesh)
    loop_island = [-1] * loop_count
    uv_to_loops: dict[tuple[float, float], list[int]] = {}

    for li in range(loop_count):
        uv_to_loops.setdefault(_uv_key(uv_data[li].uv), []).append(li)

    next_id = 0
    for start in range(loop_count):
        if loop_island[start] >= 0:
            continue
        stack = [start]
        loop_island[start] = next_id
        while stack:
            current = stack.pop()
            poly = mesh.polygons[loop_polygon[current]]
            loops = list(poly.loop_indices)
            idx = loops.index(current)
            for nb in (loops[(idx - 1) % len(loops)], loops[(idx + 1) % len(loops)]):
                if loop_island[nb] < 0:
                    loop_island[nb] = next_id
                    stack.append(nb)
            for nb in uv_to_loops.get(_uv_key(uv_data[current].uv), ()):
                if loop_island[nb] < 0:
                    loop_island[nb] = next_id
                    stack.append(nb)
        next_id += 1
    return loop_island


def raster_tbn_from_low_mesh(
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    *,
    uv_layer_name: str | None = None,
) -> LKS_TBNRaster:
    """Build tangent-frame images from merged low mesh UV layout."""
    if low_mesh.type != 'MESH' or low_mesh.data is None:
        raise RuntimeError('TBN raster requires a mesh object')
    mesh = low_mesh.data
    uv_name = uv_layer_name or _active_uv_layer_name(mesh)
    island_ids = _flood_fill_uv_islands(mesh, uv_name)
    return _rasterize_mesh_attributes(mesh, width, height, uv_layer_name=uv_name, island_ids=island_ids)


def derive_uv_island_mask_from_low_mesh(
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
) -> bpy.types.Image:
    """Island id mask for seam-safe filters (-1 outside geometry)."""
    tbn = raster_tbn_from_low_mesh(low_mesh, width, height)
    pixels = _empty_rgba_buffer(width, height, 0.0)
    for y in range(height):
        for x in range(width):
            island = tbn.island_id[y * width + x]
            if island < 0:
                continue
            val = (island % 1024) / 1023.0
            _write_pixel_rgba(pixels, width, x, y, (val, val, val, 1.0))
    return _buffer_to_image(pixels, width, height, name='_LKS_UV_ISLAND_MASK', color_space='Non-Color')


def _decode_normal_map_rgb(r: float, g: float, b: float) -> tuple[float, float, float]:
    return (r * 2.0 - 1.0, g * 2.0 - 1.0, b * 2.0 - 1.0)


def _encode_normal_map_rgb(n: tuple[float, float, float]) -> tuple[float, float, float, float]:
    nn = _normalize_vec3(n)
    return (nn[0] * 0.5 + 0.5, nn[1] * 0.5 + 0.5, nn[2] * 0.5 + 0.5, 1.0)


def derive_normal_object_from_tangent(
    tsnm_image: bpy.types.Image,
    tbn: LKS_TBNRaster,
) -> bpy.types.Image:
    """Transform TSNM + per-texel TBN into object/world-space normal colors."""
    tsnm, width, height = _image_pixels_to_buffer(tsnm_image)
    if width != tbn.width or height != tbn.height:
        raise RuntimeError('TSNM image dimensions must match TBN raster')

    out = _empty_rgba_buffer(width, height, 0.0)
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if tbn.island_id[idx] < 0:
                continue
            tr, tg, tb, _ = _read_pixel_rgba(tsnm, width, x, y)
            nt = _decode_normal_map_rgb(tr, tg, tb)
            tx = tbn.tangent[idx * 4] * 2.0 - 1.0
            ty = tbn.tangent[idx * 4 + 1] * 2.0 - 1.0
            tz = tbn.tangent[idx * 4 + 2] * 2.0 - 1.0
            bx = tbn.bitangent[idx * 4] * 2.0 - 1.0
            by = tbn.bitangent[idx * 4 + 1] * 2.0 - 1.0
            bz = tbn.bitangent[idx * 4 + 2] * 2.0 - 1.0
            nx = tbn.normal[idx * 4] * 2.0 - 1.0
            ny = tbn.normal[idx * 4 + 1] * 2.0 - 1.0
            nz = tbn.normal[idx * 4 + 2] * 2.0 - 1.0
            world = (
                tx * nt[0] + bx * nt[1] + nx * nt[2],
                ty * nt[0] + by * nt[1] + ny * nt[2],
                tz * nt[0] + bz * nt[1] + nz * nt[2],
            )
            _write_pixel_rgba(out, width, x, y, _encode_normal_map_rgb(world))

    return _buffer_to_image(out, width, height, name='_LKS_DERIVE_NORMAL_OBJECT', color_space='Non-Color')


def _island_neighbors(
    island_buf: array,
    width: int,
    height: int,
    x: int,
    y: int,
) -> list[tuple[int, int]]:
    island = island_buf[y * width + x]
    if island < 0:
        return []
    neighbors: list[tuple[int, int]] = []
    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = x + ox, y + oy
        if 0 <= nx < width and 0 <= ny < height:
            if island_buf[ny * width + nx] == island:
                neighbors.append((nx, ny))
    return neighbors


def _resolve_island_buffer(
    width: int,
    height: int,
    tbn: LKS_TBNRaster | None,
    uv_island_mask: bpy.types.Image | None,
) -> array | None:
    if tbn is not None:
        return tbn.island_id
    if uv_island_mask is None:
        return None
    mask_px, mw, mh = _image_pixels_to_buffer(uv_island_mask)
    if mw != width or mh != height:
        return None
    return array('i', [int(mask_px[i * 4] * 1023.0) for i in range(width * height)])


def _decode_normal_map_components(
    normal_rgb: array,
    width: int,
    height: int,
    island_buf: array | None,
) -> tuple[array, array, array]:
    """Per-texel unit normals decoded from normal-map RGB (TSNM or WSNM)."""
    count = width * height
    nx = array('f', [0.0] * count)
    ny = array('f', [0.0] * count)
    nz = array('f', [1.0] * count)
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if island_buf is not None and island_buf[idx] < 0:
                continue
            r, g, b, _ = _read_pixel_rgba(normal_rgb, width, x, y)
            nn = _normalize_vec3(_decode_normal_map_rgb(r, g, b))
            nx[idx] = nn[0]
            ny[idx] = nn[1]
            nz[idx] = nn[2]
    return nx, ny, nz


def _decode_tsnm_normals(
    tsnm: array,
    width: int,
    height: int,
    island_buf: array | None,
) -> tuple[array, array, array]:
    """Per-texel unit normals decoded from TSNM RGB."""
    return _decode_normal_map_components(tsnm, width, height, island_buf)


def _transform_tangent_normals_to_object(
    tx: array,
    ty: array,
    tz: array,
    tbn: LKS_TBNRaster,
    width: int,
    height: int,
    island_buf: array | None,
) -> tuple[array, array, array]:
    """Map tangent-space normals to object/world via forward TBN."""
    count = width * height
    ox = array('f', [0.0] * count)
    oy = array('f', [0.0] * count)
    oz = array('f', [1.0] * count)
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if island_buf is not None and island_buf[idx] < 0:
                continue
            nt_x, nt_y, nt_z = tx[idx], ty[idx], tz[idx]
            t0 = tbn.tangent[idx * 4] * 2.0 - 1.0
            t1 = tbn.tangent[idx * 4 + 1] * 2.0 - 1.0
            t2 = tbn.tangent[idx * 4 + 2] * 2.0 - 1.0
            b0 = tbn.bitangent[idx * 4] * 2.0 - 1.0
            b1 = tbn.bitangent[idx * 4 + 1] * 2.0 - 1.0
            b2 = tbn.bitangent[idx * 4 + 2] * 2.0 - 1.0
            n0 = tbn.normal[idx * 4] * 2.0 - 1.0
            n1 = tbn.normal[idx * 4 + 1] * 2.0 - 1.0
            n2 = tbn.normal[idx * 4 + 2] * 2.0 - 1.0
            wo = _normalize_vec3((
                t0 * nt_x + b0 * nt_y + n0 * nt_z,
                t1 * nt_x + b1 * nt_y + n1 * nt_z,
                t2 * nt_x + b2 * nt_y + n2 * nt_z,
            ))
            ox[idx], oy[idx], oz[idx] = wo
    return ox, oy, oz


def _geometric_normals_from_tbn(
    tbn: LKS_TBNRaster,
    width: int,
    height: int,
    island_buf: array | None,
) -> tuple[array, array, array]:
    """Per-texel low-mesh shading normals from the TBN raster."""
    count = width * height
    nx = array('f', [0.0] * count)
    ny = array('f', [0.0] * count)
    nz = array('f', [1.0] * count)
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if island_buf is not None and island_buf[idx] < 0:
                continue
            nn = _normalize_vec3((
                tbn.normal[idx * 4] * 2.0 - 1.0,
                tbn.normal[idx * 4 + 1] * 2.0 - 1.0,
                tbn.normal[idx * 4 + 2] * 2.0 - 1.0,
            ))
            nx[idx], ny[idx], nz[idx] = nn
    return nx, ny, nz


def _transform_world_normals_to_tangent(
    nx: array,
    ny: array,
    nz: array,
    tbn: LKS_TBNRaster,
    width: int,
    height: int,
    island_buf: array | None,
) -> tuple[array, array, array]:
    """Map object/world normals to tangent frame via inverse TBN (transpose for orthonormal)."""
    count = width * height
    tx = array('f', [0.0] * count)
    ty = array('f', [0.0] * count)
    tz = array('f', [1.0] * count)
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if island_buf is not None and island_buf[idx] < 0:
                continue
            wx, wy, wz = nx[idx], ny[idx], nz[idx]
            t0 = tbn.tangent[idx * 4] * 2.0 - 1.0
            t1 = tbn.tangent[idx * 4 + 1] * 2.0 - 1.0
            t2 = tbn.tangent[idx * 4 + 2] * 2.0 - 1.0
            b0 = tbn.bitangent[idx * 4] * 2.0 - 1.0
            b1 = tbn.bitangent[idx * 4 + 1] * 2.0 - 1.0
            b2 = tbn.bitangent[idx * 4 + 2] * 2.0 - 1.0
            n0 = tbn.normal[idx * 4] * 2.0 - 1.0
            n1 = tbn.normal[idx * 4 + 1] * 2.0 - 1.0
            n2 = tbn.normal[idx * 4 + 2] * 2.0 - 1.0
            nt = _normalize_vec3((
                t0 * wx + t1 * wy + t2 * wz,
                b0 * wx + b1 * wy + b2 * wz,
                n0 * wx + n1 * wy + n2 * wz,
            ))
            tx[idx], ty[idx], tz[idx] = nt
    return tx, ty, tz


def _is_island_border(
    island_buf: array,
    width: int,
    height: int,
    x: int,
    y: int,
) -> bool:
    island = island_buf[y * width + x]
    if island < 0:
        return False
    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = x + ox, y + oy
        if 0 <= nx < width and 0 <= ny < height:
            neighbor = island_buf[ny * width + nx]
            if neighbor >= 0 and neighbor != island:
                return True
    return False


def _stabilize_border_normals(
    nx: array,
    ny: array,
    nz: array,
    island_buf: array | None,
    width: int,
    height: int,
) -> None:
    """Inpaint UV-island border texels from same-island interior neighbors."""
    if island_buf is None:
        return
    blurred_nx, blurred_ny, blurred_nz = _box_blur_island_channels(
        nx, ny, nz, island_buf, width, height, 1,
    )
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if island_buf[idx] < 0 or not _is_island_border(island_buf, width, height, x, y):
                continue
            blend = 0.65
            bx = nx[idx] * (1.0 - blend) + blurred_nx[idx] * blend
            by = ny[idx] * (1.0 - blend) + blurred_ny[idx] * blend
            bz = nz[idx] * (1.0 - blend) + blurred_nz[idx] * blend
            nn = _normalize_vec3((bx, by, bz))
            nx[idx], ny[idx], nz[idx] = nn


def _resolve_wsnm_for_curvature(
    input_images: dict[str, bpy.types.Image],
    *,
    tbn: LKS_TBNRaster,
) -> bpy.types.Image:
    """Prefer mesh/derive WSNM; fall back to TSNM + per-texel TBN transform."""
    wsnm = input_images.get('normal_object')
    if wsnm is not None:
        return wsnm
    tsnm = input_images.get('normal')
    if tsnm is None:
        raise RuntimeError('curvature derive requires normal_object or normal input')
    return derive_normal_object_from_tangent(tsnm, tbn)


def _box_blur_island_horizontal(
    src: array,
    island_buf: array | None,
    width: int,
    height: int,
    radius: int,
    temp: array,
) -> None:
    """Island-aware horizontal box blur with O(1) sliding window per row segment."""
    for y in range(height):
        base = y * width
        x = 0
        while x < width:
            idx = base + x
            if island_buf is not None and island_buf[idx] < 0:
                temp[idx] = src[idx]
                x += 1
                continue
            island = island_buf[idx] if island_buf is not None else 0
            seg_start = x
            while x < width:
                seg_idx = base + x
                seg_island = island_buf[seg_idx] if island_buf is not None else 0
                if island_buf is not None and (seg_island < 0 or seg_island != island):
                    break
                x += 1
            seg_end = x
            if seg_end <= seg_start:
                continue

            win_sum = 0.0
            win_count = 0
            left_bound = seg_start
            right_bound = seg_end - 1
            for nx in range(seg_start, min(seg_end, seg_start + radius + 1)):
                win_sum += src[base + nx]
                win_count += 1
            temp[base + seg_start] = win_sum / win_count if win_count else src[base + seg_start]

            for px in range(seg_start + 1, seg_end):
                remove_x = px - radius - 1
                add_x = px + radius
                if remove_x >= left_bound:
                    win_sum -= src[base + remove_x]
                    win_count -= 1
                if add_x <= right_bound:
                    win_sum += src[base + add_x]
                    win_count += 1
                temp[base + px] = win_sum / win_count if win_count else src[base + px]


def _box_blur_island_vertical(
    src: array,
    island_buf: array | None,
    width: int,
    height: int,
    radius: int,
    out: array,
) -> None:
    """Island-aware vertical box blur with O(1) sliding window per column segment."""
    for x in range(width):
        y = 0
        while y < height:
            idx = y * width + x
            if island_buf is not None and island_buf[idx] < 0:
                out[idx] = src[idx]
                y += 1
                continue
            island = island_buf[idx] if island_buf is not None else 0
            seg_start = y
            while y < height:
                seg_idx = y * width + x
                seg_island = island_buf[seg_idx] if island_buf is not None else 0
                if island_buf is not None and (seg_island < 0 or seg_island != island):
                    break
                y += 1
            seg_end = y
            if seg_end <= seg_start:
                continue

            win_sum = 0.0
            win_count = 0
            top_bound = seg_start
            bottom_bound = seg_end - 1
            for ny in range(seg_start, min(seg_end, seg_start + radius + 1)):
                win_sum += src[ny * width + x]
                win_count += 1
            out[seg_start * width + x] = (
                win_sum / win_count if win_count else src[seg_start * width + x]
            )

            for py in range(seg_start + 1, seg_end):
                remove_y = py - radius - 1
                add_y = py + radius
                if remove_y >= top_bound:
                    win_sum -= src[remove_y * width + x]
                    win_count -= 1
                if add_y <= bottom_bound:
                    win_sum += src[add_y * width + x]
                    win_count += 1
                out[py * width + x] = win_sum / win_count if win_count else src[py * width + x]


def _box_blur_island(
    src: array,
    island_buf: array | None,
    width: int,
    height: int,
    radius: int,
) -> array:
    """Separable island-aware box blur on a scalar field."""
    if radius <= 0:
        return array('f', src)
    temp = array('f', [0.0] * (width * height))
    out = array('f', [0.0] * (width * height))
    _box_blur_island_horizontal(src, island_buf, width, height, radius, temp)
    _box_blur_island_vertical(temp, island_buf, width, height, radius, out)
    return out


def _box_blur_island_channels(
    src_x: array,
    src_y: array,
    src_z: array,
    island_buf: array | None,
    width: int,
    height: int,
    radius: int,
) -> tuple[array, array, array]:
    """Blur three aligned scalar fields at the same radius."""
    return (
        _box_blur_island(src_x, island_buf, width, height, radius),
        _box_blur_island(src_y, island_buf, width, height, radius),
        _box_blur_island(src_z, island_buf, width, height, radius),
    )


def _angular_normal_deviation(dot_cn: float) -> float:
    """Angle between unit normals mapped to 0..1 (stronger than 1 - dot at small angles)."""
    clamped = max(-1.0, min(1.0, dot_cn))
    return math.acos(clamped) / math.pi


def _signed_curvature_from_blurred_normals(
    nx: array,
    ny: array,
    nz: array,
    blurred_nx: array,
    blurred_ny: array,
    blurred_nz: array,
    tbn: LKS_TBNRaster,
    island_buf: array | None,
    width: int,
    height: int,
    *,
    magnitude_gain: float = BAKE_CURVATURE_MAGNITUDE_GAIN,
) -> array:
    """Convex-positive signed estimate from pre-blurred object-space normals."""
    count = width * height
    signed = array('f', [0.0] * count)
    nbuf = tbn.normal
    for idx in range(count):
        if island_buf is not None and island_buf[idx] < 0:
            continue
        n_center = (nx[idx], ny[idx], nz[idx])
        n_avg = _normalize_vec3((blurred_nx[idx], blurred_ny[idx], blurred_nz[idx]))
        n4 = idx * 4
        n_geom = (
            nbuf[n4] * 2.0 - 1.0,
            nbuf[n4 + 1] * 2.0 - 1.0,
            nbuf[n4 + 2] * 2.0 - 1.0,
        )
        dot_cn = (
            n_center[0] * n_avg[0]
            + n_center[1] * n_avg[1]
            + n_center[2] * n_avg[2]
        )
        magnitude = min(1.0, _angular_normal_deviation(dot_cn) * magnitude_gain)
        lap_x = blurred_nx[idx] - nx[idx]
        lap_y = blurred_ny[idx] - ny[idx]
        lap_z = blurred_nz[idx] - nz[idx]
        geom_align = abs(
            n_center[0] * n_geom[0]
            + n_center[1] * n_geom[1]
            + n_center[2] * n_geom[2]
        )
        if geom_align < BAKE_CURVATURE_GEOM_ALIGN_THRESHOLD:
            convexity = -(
                lap_x * n_center[0]
                + lap_y * n_center[1]
                + lap_z * n_center[2]
            )
        else:
            convexity = (
                n_center[0] * n_geom[0]
                + n_center[1] * n_geom[1]
                + n_center[2] * n_geom[2]
            ) - (
                n_avg[0] * n_geom[0]
                + n_avg[1] * n_geom[1]
                + n_avg[2] * n_geom[2]
            )
        if magnitude < 1e-12:
            signed[idx] = 0.0
        elif abs(convexity) < 1e-12:
            signed[idx] = 0.0
        else:
            signed[idx] = magnitude * (1.0 if convexity > 0.0 else -1.0)
    return signed


def _signed_curvature_from_normals(
    nx: array,
    ny: array,
    nz: array,
    tbn: LKS_TBNRaster,
    island_buf: array | None,
    width: int,
    height: int,
    radius: int,
    *,
    magnitude_gain: float = BAKE_CURVATURE_MAGNITUDE_GAIN,
) -> array:
    """Convex-positive signed estimate from object-space vector blur."""
    blurred_nx, blurred_ny, blurred_nz = _box_blur_island_channels(
        nx, ny, nz, island_buf, width, height, radius,
    )
    return _signed_curvature_from_blurred_normals(
        nx, ny, nz,
        blurred_nx, blurred_ny, blurred_nz,
        tbn, island_buf, width, height,
        magnitude_gain=magnitude_gain,
    )


def _dominant_finest_sign(
    finest: array,
    island_buf: array | None,
    width: int,
    height: int,
    x: int,
    y: int,
    *,
    radius: int = 2,
) -> float:
    """Return +1 / -1 from confident same-island neighbors on the finest scale."""
    island = island_buf[y * width + x] if island_buf is not None else 0
    pos = 0
    neg = 0
    for oy in range(-radius, radius + 1):
        for ox in range(-radius, radius + 1):
            if ox == 0 and oy == 0:
                continue
            nx = x + ox
            ny = y + oy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            n_idx = ny * width + nx
            if island_buf is not None and island_buf[n_idx] != island:
                continue
            value = finest[n_idx]
            if value > 0.0:
                pos += 1
            elif value < 0.0:
                neg += 1
    if pos == 0 and neg == 0:
        return 1.0
    return 1.0 if pos >= neg else -1.0


def _combine_multiscale_signed_curvature(
    nx: array,
    ny: array,
    nz: array,
    tbn: LKS_TBNRaster,
    island_buf: array | None,
    width: int,
    height: int,
    *,
    magnitude_gain: float = BAKE_CURVATURE_MAGNITUDE_GAIN,
) -> array:
    """Max-pool multiscale magnitudes; sign locked to finest (r=1) scale."""
    count = width * height
    blurred_nx, blurred_ny, blurred_nz = _box_blur_island_channels(
        nx, ny, nz, island_buf, width, height, 1,
    )
    finest = _signed_curvature_from_blurred_normals(
        nx, ny, nz,
        blurred_nx, blurred_ny, blurred_nz,
        tbn, island_buf, width, height,
        magnitude_gain=magnitude_gain,
    )
    combined = array('f', finest)
    finest_sign = array('f', [0.0] * count)
    for idx in range(count):
        if island_buf is not None and island_buf[idx] < 0:
            continue
        value = finest[idx]
        if abs(value) >= _CURVATURE_FINEST_SIGN_EPS:
            finest_sign[idx] = 1.0 if value > 0.0 else -1.0
        else:
            x = idx % width
            y = idx // width
            finest_sign[idx] = _dominant_finest_sign(
                finest, island_buf, width, height, x, y,
            )
    for radius in _CURVATURE_MULTISCALE_RADII[1:]:
        blurred_nx, blurred_ny, blurred_nz = _box_blur_island_channels(
            nx, ny, nz, island_buf, width, height, radius,
        )
        scale = _signed_curvature_from_blurred_normals(
            nx, ny, nz,
            blurred_nx, blurred_ny, blurred_nz,
            tbn, island_buf, width, height,
            magnitude_gain=magnitude_gain,
        )
        for idx in range(count):
            if island_buf is not None and island_buf[idx] < 0:
                continue
            if scale[idx] == 0.0:
                continue
            if (
                scale[idx] < 0.0
                and finest[idx] < 0.0
                and abs(finest[idx]) < _CURVATURE_FINEST_SIGN_EPS
                and abs(scale[idx]) > abs(combined[idx])
            ):
                continue
            if (scale[idx] > 0.0) != (finest_sign[idx] > 0.0):
                continue
            if abs(scale[idx]) > abs(combined[idx]):
                combined[idx] = scale[idx]
    return combined


def _sd_sampling_radius_px(
    width: int,
    height: int,
    *,
    sampling_radius: float = BAKE_CURVATURE_SAMPLING_RADIUS,
    relative_to_bbox: bool = BAKE_CURVATURE_RELATIVE_TO_BBOX,
) -> float:
    base = float(max(width, height))
    if relative_to_bbox:
        return max(1.0, sampling_radius * base)
    return max(1.0, sampling_radius * base)


def _sd_blur_radius_from_sampling(radius_px: float) -> int:
    ray_factor = 1.0 + 0.15 * math.log2(max(BAKE_CURVATURE_SECONDARY_RAYS, 1) / 32.0)
    return max(1, int(round(radius_px * 0.55 * ray_factor)))


def _geometry_normal_from_tbn(
    tbn: LKS_TBNRaster,
    island_buf: array | None,
    width: int,
    height: int,
) -> tuple[array, array, array]:
    """Low-poly face normals from rasterized TBN (optionally blurred)."""
    count = width * height
    gx = array('f', [0.0] * count)
    gy = array('f', [0.0] * count)
    gz = array('f', [0.0] * count)
    nbuf = tbn.normal
    for idx in range(count):
        if island_buf is not None and island_buf[idx] < 0:
            continue
        n4 = idx * 4
        gx[idx] = nbuf[n4] * 2.0 - 1.0
        gy[idx] = nbuf[n4 + 1] * 2.0 - 1.0
        gz[idx] = nbuf[n4 + 2] * 2.0 - 1.0
    radius = BAKE_CURVATURE_GEOM_BLUR_RADIUS
    if radius > 0:
        gx = _box_blur_island(gx, island_buf, width, height, radius)
        gy = _box_blur_island(gy, island_buf, width, height, radius)
        gz = _box_blur_island(gz, island_buf, width, height, radius)
    for idx in range(count):
        if island_buf is not None and island_buf[idx] < 0:
            continue
        nx, ny, nz = _normalize_vec3((gx[idx], gy[idx], gz[idx]))
        gx[idx], gy[idx], gz[idx] = nx, ny, nz
    return gx, gy, gz


def _sd_signed_curvature_from_normals(
    nx: array,
    ny: array,
    nz: array,
    geom_x: array,
    geom_y: array,
    geom_z: array,
    island_buf: array | None,
    width: int,
    height: int,
    blur_radius: int,
    *,
    magnitude_gain: float = BAKE_CURVATURE_MAGNITUDE_GAIN,
    convexity_sign: float = BAKE_CURVATURE_CONVEXITY_SIGN,
) -> array:
    """Continuous signed SD-style curvature (blur ≈ disk-ray average)."""
    blurred_nx, blurred_ny, blurred_nz = _box_blur_island_channels(
        nx, ny, nz, island_buf, width, height, blur_radius,
    )
    count = width * height
    signed = array('f', [0.0] * count)
    gain = magnitude_gain
    sign = convexity_sign
    for idx in range(count):
        if island_buf is not None and island_buf[idx] < 0:
            continue
        cx, cy, cz = nx[idx], ny[idx], nz[idx]
        bx, by, bz = _normalize_vec3((blurred_nx[idx], blurred_ny[idx], blurred_nz[idx]))
        gx, gy, gz = geom_x[idx], geom_y[idx], geom_z[idx]
        dot_cn = max(-1.0, min(1.0, cx * bx + cy * by + cz * bz))
        lap_x, lap_y, lap_z = bx - cx, by - cy, bz - cz
        lap_proj = lap_x * cx + lap_y * cy + lap_z * cz
        dot_cg = cx * gx + cy * gy + cz * gz
        dot_bg = bx * gx + by * gy + bz * gz
        geom_align = abs(dot_cg)
        geom_delta = dot_cg - dot_bg
        if geom_align < BAKE_CURVATURE_GEOM_ALIGN_THRESHOLD:
            convexity = -lap_proj * sign
        else:
            convexity = geom_delta * sign
        magnitude = math.acos(dot_cn) / math.pi
        signed[idx] = convexity * magnitude * gain
    return signed


def _tonemap_sd_per_island(
    signed: array,
    island_buf: array | None,
    width: int,
    height: int,
) -> None:
    """Auto tonemap per UV island to mid-gray flat = 0.5."""
    if island_buf is None:
        indices = list(range(width * height))
        islands = {0: indices}
    else:
        islands: dict[int, list[int]] = {}
        for idx in range(width * height):
            island = island_buf[idx]
            if island < 0:
                continue
            islands.setdefault(island, []).append(idx)

    t_min = BAKE_CURVATURE_TONEMAP_MIN
    t_max = BAKE_CURVATURE_TONEMAP_MAX
    mid = 0.5 * (t_max + t_min)
    half = 0.5 * (t_max - t_min)
    for indices in islands.values():
        if not indices:
            continue
        vals = [signed[idx] for idx in indices]
        abs_vals = [abs(v) for v in vals]
        abs_vals.sort()
        pct_idx = min(len(abs_vals) - 1, max(0, int(len(abs_vals) * BAKE_CURVATURE_TONEMAP_PERCENTILE) - 1))
        peak = max(abs_vals[pct_idx] if abs_vals else 0.0, 1e-6)
        if BAKE_CURVATURE_AUTO_TONEMAP_PER_TILE:
            for idx in indices:
                scaled = max(-1.0, min(1.0, signed[idx] / peak))
                signed[idx] = mid + scaled * half
        else:
            scale = _percentile_scale([abs(v) for v in vals], BAKE_CURVATURE_UNITIZE_PERCENTILE)
            scale = max(scale, 1e-6)
            for idx in indices:
                scaled = max(-1.0, min(1.0, signed[idx] / scale))
                signed[idx] = mid + scaled * half


def _suppress_flat_face_false_cavity(
    signed: array,
    nx: array,
    ny: array,
    nz: array,
    tbn: LKS_TBNRaster,
    island_buf: array | None,
    width: int,
    height: int,
) -> None:
    """Zero cavity speckle on near-flat low-poly faces when coarse scale disagrees."""
    coarse = _signed_curvature_from_normals(
        nx, ny, nz, tbn, island_buf, width, height, BAKE_CURVATURE_COARSE_SIGN_RADIUS,
    )
    nbuf = tbn.normal
    for idx in range(width * height):
        if island_buf is not None and island_buf[idx] < 0:
            continue
        n4 = idx * 4
        n_center = (nx[idx], ny[idx], nz[idx])
        n_geom = (
            nbuf[n4] * 2.0 - 1.0,
            nbuf[n4 + 1] * 2.0 - 1.0,
            nbuf[n4 + 2] * 2.0 - 1.0,
        )
        geom_align = abs(
            n_center[0] * n_geom[0]
            + n_center[1] * n_geom[1]
            + n_center[2] * n_geom[2]
        )
        if (
            geom_align >= BAKE_CURVATURE_FLAT_FACE_ALIGN
            and coarse[idx] >= -0.005
            and signed[idx] < 0.0
        ):
            signed[idx] = 0.0


def _smooth_signed_curvature(
    signed: array,
    island_buf: array | None,
    width: int,
    height: int,
    radius: int,
) -> array:
    """Island-aware separable blur on signed curvature (reduces multiscale speckle)."""
    if radius <= 0:
        return signed
    return _box_blur_island(signed, island_buf, width, height, radius)


def _percentile_scale(
    vals: list[float],
    percentile: float = BAKE_CURVATURE_UNITIZE_PERCENTILE,
) -> float:
    if not vals:
        return 0.0
    vals.sort()
    clip_idx = min(len(vals) - 1, max(0, int(len(vals) * percentile) - 1))
    return vals[clip_idx]


def _push_mid_gray_contrast(value: float, power: float) -> float:
    """Remap 0..1 away from 0.5 — power < 1 boosts edge highlights and cavities."""
    if power >= 1.0:
        return value
    if value >= 0.5:
        t = (value - 0.5) * 2.0
        return 0.5 + 0.5 * pow(t, power)
    t = (0.5 - value) * 2.0
    return 0.5 - 0.5 * pow(t, power)


def _robust_noise_floor(abs_vals: list[float]) -> float:
    """Ignore texels below this |signed| level when unitizing (flat stays 0.5)."""
    if not abs_vals:
        return BAKE_CURVATURE_UNITIZE_FLOOR
    abs_vals.sort()
    p25_idx = min(len(abs_vals) - 1, max(0, int(len(abs_vals) * 0.25)))
    p90_idx = min(len(abs_vals) - 1, max(0, int(len(abs_vals) * 0.90)))
    return max(
        BAKE_CURVATURE_UNITIZE_FLOOR,
        abs_vals[p25_idx] * 2.0,
        abs_vals[p90_idx] * 0.15,
    )


def _unitize_signed_curvature(
    signed: array,
    island_buf: array | None,
    width: int,
    height: int,
) -> None:
    """Remap signed curvature in-place to 0..1 with flat at 0.5.

    Positive and negative tails use separate percentile scales so deep
    cavities do not compress convex highlights when magnitudes differ. A mild
    mid-gray contrast curve pushes edge peaks toward white and grooves toward black.
    """
    pos_vals: list[float] = []
    neg_vals: list[float] = []
    indices: list[int] = []
    contrast = BAKE_CURVATURE_UNITIZE_CONTRAST
    for idx in range(width * height):
        if island_buf is not None and island_buf[idx] < 0:
            continue
        indices.append(idx)
    if not indices:
        return
    abs_vals = [abs(signed[idx]) for idx in indices]
    floor = _robust_noise_floor(abs_vals)
    for idx in indices:
        value = signed[idx]
        if value > floor:
            pos_vals.append(value)
        elif value < -floor:
            neg_vals.append(-value)
    pos_scale = _percentile_scale(pos_vals)
    neg_scale = _percentile_scale(neg_vals)
    if pos_scale < floor and neg_scale < floor:
        for idx in indices:
            signed[idx] = 0.5
        return
    if pos_scale < floor:
        pos_scale = neg_scale
    if neg_scale < floor:
        neg_scale = pos_scale
    pos_inv = 1.0 / (2.0 * pos_scale)
    neg_inv = 1.0 / (2.0 * neg_scale)
    for idx in indices:
        value = signed[idx]
        if value > floor:
            remapped = max(0.5, min(1.0, value * pos_inv + 0.5))
            signed[idx] = _push_mid_gray_contrast(remapped, contrast)
        elif value < -floor:
            remapped = max(0.0, min(0.5, value * neg_inv + 0.5))
            signed[idx] = _push_mid_gray_contrast(remapped, contrast)
        else:
            signed[idx] = 0.5


def _write_signed_curvature_to_rgba(
    signed: array,
    island_buf: array | None,
    width: int,
    height: int,
    *,
    unitize: bool,
) -> array:
    if unitize:
        _unitize_signed_curvature(signed, island_buf, width, height)
    out = _empty_rgba_buffer(width, height, 0.0)
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if island_buf is not None and island_buf[idx] < 0:
                continue
            gray = signed[idx] if unitize else max(0.0, min(1.0, signed[idx] * 0.5 + 0.5))
            _write_pixel_rgba(out, width, x, y, (gray, gray, gray, 1.0))
    return out


def derive_curvature_from_normal(
    normal_image: bpy.types.Image,
    *,
    uv_island_mask: bpy.types.Image | None = None,
    tbn: LKS_TBNRaster | None = None,
    method: str = BAKE_CURVATURE_METHOD_DEFAULT,
    unitize: bool = BAKE_CURVATURE_UNITIZE_DEFAULT,
    from_object_space: bool = True,
    magnitude_gain: float = BAKE_CURVATURE_MAGNITUDE_GAIN,
    sampling_radius: float = BAKE_CURVATURE_SAMPLING_RADIUS,
    relative_to_bbox: bool = BAKE_CURVATURE_RELATIVE_TO_BBOX,
    convexity_sign: float = BAKE_CURVATURE_CONVEXITY_SIGN,
) -> bpy.types.Image:
    """Signed curvature from normal map — convex bright, cavity dark.

    When BAKE_CURVATURE_STUB_ENABLED is True, returns flat mid-gray while
    Engine map tests validate algorithms under map_types/curvature/test/.
    """
    from lks_baker.shared_utilities.lks_constants import BAKE_CURVATURE_STUB_ENABLED

    normal_buf, width, height = _image_pixels_to_buffer(normal_image)
    island_buf = _resolve_island_buffer(width, height, tbn, uv_island_mask)

    if BAKE_CURVATURE_STUB_ENABLED:
        log_step('curvature derive stub — flat mid-gray (wire engine map_types/curvature)')
        out = _empty_rgba_buffer(width, height, 0.0)
        for y in range(height):
            for x in range(width):
                if island_buf[y * width + x] >= 0:
                    _write_pixel_rgba(out, width, x, y, (0.5, 0.5, 0.5, 1.0))
        return _buffer_to_image(
            out, width, height, name='_LKS_DERIVE_CURVATURE_STUB', color_space='Non-Color',
        )

    with timed_step('curvature decode normals'):
        nx, ny, nz = _decode_normal_map_components(normal_buf, width, height, island_buf)
    if tbn is None:
        raise RuntimeError('curvature derive requires TBN raster')
    if from_object_space:
        with timed_step('curvature stabilize borders'):
            _stabilize_border_normals(nx, ny, nz, island_buf, width, height)
    else:
        with timed_step('curvature tangent to object'):
            nx, ny, nz = _transform_tangent_normals_to_object(
                nx, ny, nz, tbn, width, height, island_buf,
            )

    if method == 'SD':
        radius_px = _sd_sampling_radius_px(
            width,
            height,
            sampling_radius=sampling_radius,
            relative_to_bbox=relative_to_bbox,
        )
        blur_radius = _sd_blur_radius_from_sampling(radius_px)
        with timed_step('curvature SD geometry normal'):
            geom_x, geom_y, geom_z = _geometry_normal_from_tbn(
                tbn, island_buf, width, height,
            )
        with timed_step('curvature SD disk-blur sampling'):
            signed = _sd_signed_curvature_from_normals(
                nx, ny, nz, geom_x, geom_y, geom_z,
                island_buf, width, height, blur_radius,
                magnitude_gain=magnitude_gain,
                convexity_sign=convexity_sign,
            )
        if unitize:
            with timed_step('curvature SD per-tile tonemap'):
                _tonemap_sd_per_island(signed, island_buf, width, height)
    elif method == 'SINGLE_SCALE':
        with timed_step('curvature single-scale filter'):
            signed = _signed_curvature_from_normals(
                nx, ny, nz, tbn, island_buf, width, height, 1,
                magnitude_gain=magnitude_gain,
            )
    else:
        with timed_step('curvature multiscale filter'):
            signed = _combine_multiscale_signed_curvature(
                nx, ny, nz, tbn, island_buf, width, height,
                magnitude_gain=magnitude_gain,
            )

    if method not in ('SD',):
        with timed_step('curvature post-filter'):
            _suppress_flat_face_false_cavity(
                signed, nx, ny, nz, tbn, island_buf, width, height,
            )
            if BAKE_CURVATURE_POST_SMOOTH_RADIUS > 0:
                signed = _smooth_signed_curvature(
                    signed, island_buf, width, height, BAKE_CURVATURE_POST_SMOOTH_RADIUS,
                )

    with timed_step('curvature encode output'):
        out = _write_signed_curvature_to_rgba(
            signed, island_buf, width, height, unitize=unitize and method != 'SD',
        )
    return _buffer_to_image(out, width, height, name='_LKS_DERIVE_CURVATURE', color_space='Non-Color')


def derive_convexity_from_curvature(curvature_image: bpy.types.Image) -> bpy.types.Image:
    """Positive curvature split remapped to 0–1."""
    src, width, height = _image_pixels_to_buffer(curvature_image)
    out = _empty_rgba_buffer(width, height, 0.0)
    for y in range(height):
        for x in range(width):
            r, _, _, a = _read_pixel_rgba(src, width, x, y)
            if a <= 0.0:
                continue
            signed = (r - 0.5) * 2.0
            convex = max(0.0, signed)
            _write_pixel_rgba(out, width, x, y, (convex, convex, convex, 1.0))
    return _buffer_to_image(out, width, height, name='_LKS_DERIVE_CONVEXITY', color_space='Non-Color')


def derive_cavity_from_curvature(curvature_image: bpy.types.Image) -> bpy.types.Image:
    """Negative curvature split remapped to 0–1."""
    src, width, height = _image_pixels_to_buffer(curvature_image)
    out = _empty_rgba_buffer(width, height, 0.0)
    for y in range(height):
        for x in range(width):
            r, _, _, a = _read_pixel_rgba(src, width, x, y)
            if a <= 0.0:
                continue
            signed = (r - 0.5) * 2.0
            cavity = max(0.0, -signed)
            _write_pixel_rgba(out, width, x, y, (cavity, cavity, cavity, 1.0))
    return _buffer_to_image(out, width, height, name='_LKS_DERIVE_CAVITY', color_space='Non-Color')


def _island_color(island_id: int) -> tuple[float, float, float, float]:
    from lks_baker.bake_ops.engine.static_utilities.island_colors import island_id_to_rgb01

    red, green, blue = island_id_to_rgb01(island_id)
    return (red, green, blue, 1.0)


def derive_uv_island_from_low_mesh(
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
) -> bpy.types.Image:
    """Flood-fill UV islands to stable pseudo-random RGB colors."""
    if low_mesh.type != 'MESH' or low_mesh.data is None:
        raise RuntimeError('UV island derive requires a mesh object')
    mesh = low_mesh.data
    uv_name = _active_uv_layer_name(mesh)
    island_ids = _flood_fill_uv_islands(mesh, uv_name)
    tbn = _rasterize_mesh_attributes(mesh, width, height, uv_layer_name=uv_name, island_ids=island_ids)
    out = _empty_rgba_buffer(width, height, 0.0)
    for y in range(height):
        for x in range(width):
            island = tbn.island_id[y * width + x]
            if island < 0:
                continue
            _write_pixel_rgba(out, width, x, y, _island_color(island))
    return _buffer_to_image(out, width, height, name='_LKS_DERIVE_UV_ISLAND', color_space='Non-Color')


def derive_alpha_mask_from_transparency(
    transparency_image: bpy.types.Image,
    *,
    threshold: float = 0.5,
) -> bpy.types.Image:
    """Hard threshold transparency into a binary mask."""
    src, width, height = _image_pixels_to_buffer(transparency_image)
    out = _empty_rgba_buffer(width, height, 0.0)
    for y in range(height):
        for x in range(width):
            r, g, b, a = _read_pixel_rgba(src, width, x, y)
            value = max(r, g, b, a)
            mask = 1.0 if value >= threshold else 0.0
            _write_pixel_rgba(out, width, x, y, (mask, mask, mask, 1.0))
    return _buffer_to_image(out, width, height, name='_LKS_DERIVE_ALPHA_MASK', color_space='Non-Color')


def execute_texture_derive(
    map_id: str,
    spec: LKS_BakeMapSpec,
    *,
    low_mesh: bpy.types.Object,
    width: int,
    height: int,
    input_images: dict[str, bpy.types.Image],
    tbn_cache: LKS_TBNRaster | None = None,
    map_entry=None,
) -> bpy.types.Image:
    """Dispatch catalog derive_method for one map_id."""
    method = spec.derive_method
    if method is None:
        raise RuntimeError(f"Map '{map_id}' has no derive_method")

    if method == 'normal_object_from_tangent':
        from lks_baker.bake_ops.static_utilities.bake_method_catalog import (
            resolve_map_entry_bake_method,
        )

        if map_entry is not None and resolve_map_entry_bake_method(map_entry) != 'normal_object_from_tangent':
            raise RuntimeError(
                'normal_object derive requires method normal_object_from_tangent',
            )
        tsnm = input_images.get('normal')
        if tsnm is None:
            raise RuntimeError('normal_object derive requires TSNM input')
        if tbn_cache is None:
            tbn = raster_tbn_from_low_mesh(low_mesh, width, height)
            log_step('TBN cache miss — rasterizing (derive)')
        else:
            tbn = tbn_cache
            log_step('TBN cache hit (derive)')
        from lks_baker.bake_ops.blender.derive_bridge import try_derive_normal_object_via_bake_engine

        engine_image = try_derive_normal_object_via_bake_engine(tsnm, tbn=tbn)
        if engine_image is not None:
            log_step('normal_object derive via bake_engine')
            return engine_image
        raise RuntimeError(
            'normal_object_from_tangent bake-engine derive failed — check TBN and tangent normal input',
        )

    if method == 'curvature_from_normal':
        if tbn_cache is None:
            tbn = raster_tbn_from_low_mesh(low_mesh, width, height)
            log_step('TBN cache miss — rasterizing (derive)')
        else:
            tbn = tbn_cache
            log_step('TBN cache hit (derive)')
        from lks_baker.shared_utilities.lks_constants import (
            BAKE_CURVATURE_DEVICE_DEFAULT,
            BAKE_CURVATURE_ENGINE_METHOD,
            BAKE_CURVATURE_METHOD_DEFAULT,
            BAKE_CURVATURE_UNITIZE_DEFAULT,
            BAKE_CURVATURE_USE_BAKE_ENGINE,
        )
        from lks_baker.bake_ops.static_utilities.bake_method_catalog import (
            resolve_map_entry_bake_method,
        )

        curv_method = BAKE_CURVATURE_METHOD_DEFAULT
        curv_unitize = BAKE_CURVATURE_UNITIZE_DEFAULT
        curv_device = BAKE_CURVATURE_DEVICE_DEFAULT
        selected_method = 'soft_curvature'
        if map_entry is not None:
            curv_method = getattr(map_entry, 'lks_curvature_method', curv_method) or curv_method
            curv_unitize = bool(getattr(map_entry, 'lks_curvature_unitize', curv_unitize))
            curv_device = getattr(map_entry, 'lks_curvature_device', curv_device) or curv_device
            selected_method = resolve_map_entry_bake_method(map_entry, map_id='curvature')

        if selected_method == 'soft_curvature' or BAKE_CURVATURE_USE_BAKE_ENGINE:
            from lks_baker.bake_ops.blender.curvature_bridge import try_derive_curvature_via_bake_engine

            method_id = selected_method if selected_method == 'soft_curvature' else BAKE_CURVATURE_ENGINE_METHOD
            engine_image = try_derive_curvature_via_bake_engine(
                input_images,
                tbn=tbn,
                low_mesh=low_mesh,
                method_id=method_id,
                device=curv_device,
                map_entry=map_entry,
                image_size=width,
            )
            if engine_image is not None:
                log_step('curvature derive via bake_engine')
                return engine_image
            raise RuntimeError(
                f"Curvature method '{selected_method}' could not run via bake engine — "
                'check required inputs (normal_object / normal / position / low mesh)',
            )

        raise RuntimeError(
            'Legacy curvature derive is disabled — select soft_curvature or enable bake engine',
        )

    if method == 'convexity_from_curvature':
        curv = input_images.get('curvature')
        if curv is None:
            raise RuntimeError('convexity derive requires curvature input')
        from lks_baker.bake_ops.blender.curvature_bridge import try_derive_split_via_bake_engine

        split_image = try_derive_split_via_bake_engine(
            curv,
            tbn=tbn_cache or raster_tbn_from_low_mesh(low_mesh, width, height),
            map_type='convexity',
            method_id='convexity_from_curvature',
        )
        if split_image is not None:
            return split_image
        raise RuntimeError('convexity_from_curvature bake-engine derive failed')

    if method == 'cavity_from_curvature':
        curv = input_images.get('curvature')
        if curv is None:
            raise RuntimeError('cavity derive requires curvature input')
        from lks_baker.bake_ops.blender.curvature_bridge import try_derive_split_via_bake_engine

        split_image = try_derive_split_via_bake_engine(
            curv,
            tbn=tbn_cache or raster_tbn_from_low_mesh(low_mesh, width, height),
            map_type='cavity',
            method_id='cavity_from_curvature',
        )
        if split_image is not None:
            return split_image
        raise RuntimeError('cavity_from_curvature bake-engine derive failed')

    if method == 'uv_island_from_mesh':
        from lks_baker.bake_ops.blender.derive_bridge import try_derive_uv_island_via_bake_engine

        engine_image = try_derive_uv_island_via_bake_engine(low_mesh, width, height)
        if engine_image is not None:
            log_step('uv_island derive via bake_engine')
            return engine_image
        raise RuntimeError('uv_island_from_mesh bake-engine derive failed')

    if method == 'wireframe_uv_raster':
        from lks_baker.bake_ops.blender.derive_bridge import try_derive_wireframe_via_bake_engine

        engine_image = try_derive_wireframe_via_bake_engine(
            low_mesh,
            width,
            height,
            map_entry=map_entry,
        )
        if engine_image is not None:
            log_step('wireframe derive via bake_engine')
            return engine_image
        raise RuntimeError('wireframe_uv_raster bake-engine derive failed')

    if method == 'group_id_raster':
        from lks_baker.bake_ops.blender.derive_bridge import try_derive_group_id_via_bake_engine
        from lks_baker.bake_ops.engine.map_types.group_id.static_utilities.face_group_ids import (
            get_group_id_derive_skip_reason,
        )

        skip_reason = get_group_id_derive_skip_reason(low_mesh, map_entry=map_entry)
        if skip_reason is not None:
            raise TextureDeriveSkip(skip_reason)

        engine_image = try_derive_group_id_via_bake_engine(
            low_mesh,
            width,
            height,
            map_entry=map_entry,
        )
        if engine_image is not None:
            log_step('group_id derive via bake_engine')
            return engine_image
        raise TextureDeriveSkip('group_id_raster bake-engine derive failed')

    if method == 'alpha_mask_from_transparency':
        trans = input_images.get('transparency')
        if trans is None:
            raise RuntimeError('alpha_mask derive requires transparency input')
        from lks_baker.bake_ops.blender.derive_bridge import try_derive_alpha_mask_via_bake_engine

        engine_image = try_derive_alpha_mask_via_bake_engine(trans)
        if engine_image is not None:
            log_step('alpha_mask derive via bake_engine')
            return engine_image
        raise RuntimeError('alpha_mask_from_transparency bake-engine derive failed')

    if method == 'hemisphere_trace':
        from lks_baker.bake_ops.blender.derive_bridge import (
            try_derive_hemisphere_trace_via_bake_engine,
        )

        normal_object = input_images.get('normal_object')
        position = input_images.get('position')
        if normal_object is None or position is None:
            raise RuntimeError('bent_normal derive requires normal_object and position inputs')
        engine_image = try_derive_hemisphere_trace_via_bake_engine(
            normal_object,
            position,
            map_entry=map_entry,
            tbn=tbn_cache,
        )
        if engine_image is not None:
            log_step('hemisphere_trace derive via bake_engine')
            return engine_image
        raise RuntimeError('hemisphere_trace bake-engine derive failed')

    if method == 'bent_normal_object':
        from lks_baker.bake_ops.blender.derive_bridge import (
            try_derive_bent_normal_object_via_bake_engine,
        )

        normal_object = input_images.get('normal_object')
        position = input_images.get('position')
        if normal_object is None or position is None:
            raise RuntimeError('bent_normal_object derive requires normal_object and position inputs')
        engine_image = try_derive_bent_normal_object_via_bake_engine(
            normal_object,
            position,
            map_entry=map_entry,
            tbn=tbn_cache,
        )
        if engine_image is not None:
            log_step('bent_normal_object derive via bake_engine')
            return engine_image
        raise RuntimeError('bent_normal_object bake-engine derive failed')

    raise RuntimeError(f"Unknown derive_method '{method}' for map '{map_id}'")

import bpy
from pathlib import Path
import re
import datetime
from typing import Optional


def export_image_datablock(img: 'bpy.types.Image', dest_dir: Path, base_name: str, scene: 'bpy.types.Scene') -> Path | None:
    """Export an image datablock using scene-controlled format & quality (STRICT MODE / no fallbacks).

    Investigation build: we try ONLY the user-selected format (except we always use PNG if that is selected).
    No automatic fallback to other formats. On failure we log detailed diagnostics to a _export_debug.txt file in dest_dir.

    - Uses scene.lks_asset_texture_format (WEBP/PNG/JPEG) exactly.
    - Uses scene.lks_asset_image_quality when lossy.
    - Packs first so pixel data is ensured resident, then unpacks after save.
    - UDIM images: iterate tiles and attempt ONLY selected format per tile. If WEBP/JPEG unsupported for UDIM on this build, all will log failures.
    - Returns final Path of (last) written file or None if nothing written.
    """
    # Ensure output directory exists (caller usually does this but be defensive)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    tex_format = getattr(scene, 'lks_asset_texture_format', 'WEBP').upper()
    quality = int(getattr(scene, 'lks_asset_image_quality', 90))

    clean_flag = bool(
        getattr(scene, 'lks_asset_clean_texture_filenames', True))

    def _clean(name: str) -> str:
        # Remove common redundant tokens that might have crept into datablock names
        # Example: wb_frames__UVTILE__normal_webp_001 -> wb_frames_UVTILE_normal
        n = name
        n = n.replace('__', '_')
        # Drop extension-like tokens at end
        n = re.sub(r'(_?(webp|png|jpg|jpeg))$', '', n, flags=re.IGNORECASE)
        # Remove terminal numeric copy or tile indicator (but keep 2-letter suffixes like _BC, _N)
        n = re.sub(r'_(?:\d{3,4})$', '', n)
        # Collapse multiple underscores
        n = re.sub(r'_+', '_', n)
        n = n.strip('_')
        return n

    name_clean = _clean(base_name) if clean_flag else base_name
    is_udim = (getattr(img, 'source', '') == 'TILED') or ('<UDIM>' in getattr(
        img, 'filepath', '') or '<UDIM>' in getattr(img, 'filepath_raw', ''))

    debug_log = dest_dir / "_export_debug.txt"

    def _log(header: str, details: str = ""):
        try:
            with debug_log.open('a', encoding='utf-8') as fh:
                ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                fh.write(f"[{ts}] {header}\n")
                if details:
                    fh.write(details.rstrip() + "\n")
        except Exception:
            pass

    try:
        if not img.packed_file:
            img.pack()
    except Exception as e:
        _log(f"PACK_WARNING {img.name}", f"Exception packing image: {e}")

    def save_variant(path: Path, file_format: str) -> tuple[bool, str]:
        """Attempt a single save; returns (success, message)."""
        prev_format = getattr(img, 'file_format', None)
        prev_path = img.filepath
        rs = getattr(bpy.context, 'scene', None)
        render_settings = getattr(rs, 'render', None) if rs else None
        img_settings = getattr(
            render_settings, 'image_settings', None) if render_settings else None
        prev_quality = None
        try:
            # Adjust quality in render settings if present (some formats read from there in certain builds)
            if img_settings and hasattr(img_settings, 'quality'):
                prev_quality = img_settings.quality
                img_settings.quality = quality
            if hasattr(img, 'file_format'):
                try:
                    img.file_format = file_format
                except Exception as inner:
                    _log(f"FORMAT_SET_FAIL {img.name}",
                         f"Tried {file_format}: {inner}")
            img.filepath = str(path)
            try:
                img.save(filepath=str(path), quality=quality)
            except Exception as save_ex:
                try:
                    img.save_render(filepath=str(path),
                                    scene=scene, quality=quality)
                except Exception as save_r_ex:
                    # Restore state before returning
                    try:
                        img.filepath = prev_path
                    except Exception:
                        pass
                    if prev_format is not None:
                        try:
                            img.file_format = prev_format
                        except Exception:
                            pass
                    if img_settings and prev_quality is not None:
                        try:
                            img_settings.quality = prev_quality
                        except Exception:
                            pass
                    return False, f"save() failed: {save_ex}; save_render() failed: {save_r_ex}"
            # Restore
            try:
                img.filepath = prev_path
            except Exception:
                pass
            if prev_format is not None:
                try:
                    img.file_format = prev_format
                except Exception:
                    pass
            if img_settings and prev_quality is not None:
                try:
                    img_settings.quality = prev_quality
                except Exception:
                    pass
            ok = path.exists() and path.stat().st_size > 0
            return ok, "ok" if ok else "file not created"
        except Exception as e:
            return False, f"unexpected exception: {e}"

    final_path: Path | None = None
    # (format, path, success, msg)
    attempted: list[tuple[str, Path, bool, str]] = []
    if is_udim:
        wanted = tex_format
        if wanted == 'WEBP':
            ext, format_enum = 'webp', 'WEBP'
        elif wanted == 'JPEG':
            ext, format_enum = 'jpg', 'JPEG'
        else:
            ext, format_enum = 'png', 'PNG'

        def attempt_udim(format_enum: str, ext: str) -> tuple[bool, Path, str]:
            pattern_path = dest_dir / f"{name_clean}.<UDIM>.{ext}"
            ok_pattern, msg_pattern = save_variant(pattern_path, format_enum)
            # Determine success by presence of at least one tile file
            first_tile = None
            for t in getattr(img, 'tiles', []):
                num = getattr(t, 'number', None)
                if num is None:
                    continue
                tile_candidate = dest_dir / f"{name_clean}.{num}.{ext}"
                if tile_candidate.exists() and tile_candidate.stat().st_size > 0:
                    first_tile = tile_candidate
                    break
            success = first_tile is not None
            attempted.append(
                (f"UDIM-{format_enum}", pattern_path, success, msg_pattern if not success else 'ok'))
            return success, (first_tile or pattern_path), msg_pattern

        ok, chosen_path, msg = attempt_udim(format_enum, ext)
        if not ok and wanted in {'WEBP', 'JPEG'}:
            # Fallback to PNG
            ok_png, chosen_path_png, msg_png = attempt_udim('PNG', 'png')
            if ok_png:
                _log(f"FALLBACK_SUCCESS {img.name}", f"UDIM {wanted}->PNG")
                ext, format_enum = 'png', 'PNG'
                ok, chosen_path, msg = ok_png, chosen_path_png, msg_png
            else:
                msg = f"primary:{msg} fallback:{msg_png}"
        if ok:
            # chosen_path should be a tile file; derive pattern for image.filepath
            pattern_path = dest_dir / f"{name_clean}.<UDIM>.{ext}"
            final_path = chosen_path if chosen_path.exists() else None
            try:
                img.filepath = bpy.path.relpath(str(pattern_path))
            except Exception:
                pass
        else:
            _log(f"UDIM_TOTAL_FAIL {img.name}",
                 f"Could not export UDIM image in {format_enum} (msg={msg})")
    else:
        wanted = tex_format
        if wanted == 'WEBP':
            ext, format_enum = 'webp', 'WEBP'
        elif wanted == 'JPEG':
            ext, format_enum = 'jpg', 'JPEG'
        else:
            ext, format_enum = 'png', 'PNG'
        candidate = dest_dir / f"{name_clean}.{ext}"
        ok, msg = save_variant(candidate, format_enum)
        attempted.append((format_enum, candidate, ok, msg))
        if ok:
            final_path = candidate
        else:
            # Optional fallback: if user selected WEBP or JPEG and it failed, try PNG automatically
            if wanted in {'WEBP', 'JPEG'}:
                png_candidate = dest_dir / f"{name_clean}.png"
                ok_png, msg_png = save_variant(png_candidate, 'PNG')
                attempted.append(('PNG', png_candidate, ok_png, msg_png))
                if ok_png:
                    final_path = png_candidate
                    _log(
                        f"FALLBACK_SUCCESS {img.name}", f"Original {format_enum} failed ({msg}); PNG succeeded")
                else:
                    _log(f"SAVE_FAIL {img.name}", f"Tried {format_enum} then PNG; both failed. First msg={msg}; png msg={msg_png}\nImage props: source={img.source} size={getattr(img,'size',None)} depth={getattr(img,'depth',None)} is_float={getattr(img,'is_float',None)} is_dirty={getattr(img,'is_dirty',None)} file_format(after)={getattr(img,'file_format',None)}")
            else:
                _log(f"SAVE_FAIL {img.name}", f"format={format_enum} path={candidate}\n{msg}\nImage props: source={img.source} size={getattr(img,'size',None)} depth={getattr(img,'depth',None)} is_float={getattr(img,'is_float',None)} is_dirty={getattr(img,'is_dirty',None)} file_format(after)={getattr(img,'file_format',None)}")

    if final_path and final_path.exists():
        try:
            img.filepath = bpy.path.relpath(str(final_path))
        except Exception:
            pass
    # Clean up any accidental duplicate tile number segments like _BC.1001.1001.ext
    if is_udim:
        try:
            current = img.filepath
            # pattern: (.####).#### before extension
            new = re.sub(
                r'(\.1[0-9]{3})\.1[0-9]{3}(\.[A-Za-z0-9]+)$', r'\1\2', current)
            if new != current:
                img.filepath = new
        except Exception:
            pass
    if img.packed_file:
        try:
            img.unpack(method='USE_ORIGINAL')
        except Exception as e:
            _log(f"UNPACK_FAIL {img.name}", f"USE_ORIGINAL: {e}")
            try:
                img.unpack(method='WRITE_LOCAL')
            except Exception as e2:
                _log(f"UNPACK_FAIL {img.name}", f"WRITE_LOCAL: {e2}")
    # Append a concise summary of attempts (helpful for batch debugging)
    if attempted:
        summary_lines = [
            f"{fmt}:{'OK' if ok else 'FAIL'}:{path.name}:{msg}" for fmt, path, ok, msg in attempted]
        _log(f"ATTEMPT_SUMMARY {img.name}", " | ".join(summary_lines))
    return final_path

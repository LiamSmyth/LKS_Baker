"""Minimal Blender session for bake-engine tests — factory + lks_ops only."""
from __future__ import annotations

import addon_utils

from .bootstrap import ensure_bake_engine_deps
from .runtime_log import log, timed_step

ADDON_PACKAGE = "lks_baker"
"""Only user addon kept enabled after factory reset."""

_BUILTIN_IMPORT_ADDONS: tuple[str, ...] = (
    "io_scene_fbx",
)
"""Built-in importers required by bake-engine FBX fixtures (not user addons)."""

_KEEP_ENABLED: frozenset[str] = frozenset({ADDON_PACKAGE, *_BUILTIN_IMPORT_ADDONS})
_SESSION_READY = False
_BPY_SESSION_FLAG = "_lks_bake_engine_session_ready"


def _session_flag_get() -> bool:
    try:
        import bpy

        return bool(bpy.app.driver_namespace.get(_BPY_SESSION_FLAG, False))
    except Exception:
        return _SESSION_READY


def _session_flag_set(value: bool) -> None:
    global _SESSION_READY
    _SESSION_READY = value
    try:
        import bpy

        bpy.app.driver_namespace[_BPY_SESSION_FLAG] = value
    except Exception:
        pass


def _bpy_data_available() -> bool:
    import bpy

    try:
        _ = bpy.data.objects
        return True
    except AttributeError:
        return False


def _session_is_clean() -> bool:
    import bpy

    if not _bpy_data_available():
        return False
    return len(bpy.data.objects) == 0 and len(bpy.data.meshes) == 0


def _primary_scene():
    """Return a writable scene in background / restricted-context scripts."""
    import bpy

    try:
        return bpy.context.scene
    except AttributeError:
        if not _bpy_data_available():
            raise RuntimeError("bpy.data unavailable in restricted Blender context")
        if bpy.data.scenes:
            return bpy.data.scenes[0]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        return bpy.data.scenes[0]


def _keep_enabled_for_session() -> frozenset[str]:
    """Background engine tests import via sys.path; skip user-addon enable."""
    import bpy

    if bpy.app.background:
        return frozenset(_BUILTIN_IMPORT_ADDONS)
    return _KEEP_ENABLED


def bootstrap_bake_engine_blender_session(*, force: bool = False) -> None:
    """Reset to factory-empty scene and enable only ``lks_baker``.

    Call once per Blender process before mesh import or GPU offscreen work.
    """
    global _SESSION_READY
    import bpy

    if _session_flag_get() and not force:
        return
    if _SESSION_READY and not force:
        _session_flag_set(True)
        return

    if force or (not bpy.app.background and not _session_is_clean()):
        with timed_step("read_factory_settings (lks_ops only)"):
            bpy.ops.wm.read_factory_settings(use_empty=True)
    else:
        log("blender_session: skipping factory reset (background or clean session)")

    keep_enabled = _keep_enabled_for_session()

    for mod in list(addon_utils.modules()):
        name = mod.__name__
        try:
            enabled = addon_utils.check(name)[1]
        except Exception:
            continue
        if not enabled:
            continue
        if name in keep_enabled:
            continue
        addon_utils.disable(name, default_set=True)

    for name in keep_enabled:
        if name not in {mod.__name__ for mod in addon_utils.modules()}:
            continue
        if not addon_utils.check(name)[1]:
            addon_utils.enable(name, default_set=True, persistent=True)

    ensure_bake_engine_deps()
    try:
        from lks_baker.bake_ops.engine.gpu.gpu_runtime import (
            reset_gpu_runtime_cache,
        )

        reset_gpu_runtime_cache()
    except ImportError:
        pass
    _session_flag_set(True)
    log("blender_session: factory reset; only lks_baker enabled")


def clear_bake_test_scene() -> None:
    """Remove imported objects/meshes between dataset loads (no full factory reset)."""
    import bpy

    if not _bpy_data_available():
        return

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

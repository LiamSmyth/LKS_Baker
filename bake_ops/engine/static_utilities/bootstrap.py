"""Ensure numpy/scipy/Pillow import under Blender --factory-startup."""
from __future__ import annotations

import site
import sys

from .runtime_log import log, timed_step


def ensure_bake_engine_deps() -> None:
    """Ensure bake engine deps.
    """
    log("bootstrap: checking numpy/scipy/PIL")
    user_site = site.getusersitepackages()
    if user_site and user_site not in sys.path:
        sys.path.insert(0, user_site)
        log(f"bootstrap: added user site {user_site!r}")

    missing: list[str] = []
    for name in ("numpy", "scipy", "PIL"):
        with timed_step(f"import {name}"):
            try:
                __import__(name)
            except ImportError:
                missing.append(name)

    if missing:
        blender_hint = ""
        try:
            import bpy

            binary = getattr(bpy.app, "binary_path", None)
            if binary:
                blender_hint = f' Install with: "{binary}" -m pip install scipy pillow'
        except ImportError:
            pass
        raise ImportError(
            "Missing Python packages for bake engine tests: "
            + ", ".join(missing)
            + f". Tried user site: {user_site!r}."
            + blender_hint
            + " Or run without --factory-startup."
        )
    log("bootstrap: deps OK")

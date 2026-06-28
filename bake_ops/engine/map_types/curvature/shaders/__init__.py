"""Load curvature-specific GLSL fragment sources."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lks_baker.bake_ops.engine.gpu.shaders import FULLSCREEN_VERT

_SHADER_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=16)
def load_shader(name: str) -> str:
    path = _SHADER_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


SOFT_CURVATURE_FRAG = load_shader("soft_curvature_frag.glsl")


def reload_shaders() -> None:
    """Clear cached GLSL sources (dev edits without restarting Blender)."""
    load_shader.cache_clear()
    globals().update(
        {
            "SOFT_CURVATURE_FRAG": load_shader("soft_curvature_frag.glsl"),
        }
    )


__all__ = (
    "FULLSCREEN_VERT",
    "SOFT_CURVATURE_FRAG",
    "load_shader",
    "reload_shaders",
)

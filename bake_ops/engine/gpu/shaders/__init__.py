"""Shared GLSL sources for engine GPU offscreen passes."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_SHADER_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=16)
def load_shader(name: str) -> str:
    path = _SHADER_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


FULLSCREEN_VERT = load_shader("fullscreen_vert.glsl")


def reload_shaders() -> None:
    """Clear cached GLSL sources (dev edits without restarting Blender)."""
    load_shader.cache_clear()
    globals()["FULLSCREEN_VERT"] = load_shader("fullscreen_vert.glsl")

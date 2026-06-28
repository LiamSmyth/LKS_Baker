"""Load bent-normal GLSL fragment sources."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lks_baker.bake_ops.engine.gpu.shaders import FULLSCREEN_VERT

_SHADER_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=8)
def load_shader(name: str) -> str:
    path = _SHADER_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


BENT_NORMAL_OBJECT_DIR_FRAG = load_shader("bent_normal_object_dir_frag.glsl")


def reload_shaders() -> None:
    """Clear cached GLSL sources."""
    load_shader.cache_clear()
    globals()["BENT_NORMAL_OBJECT_DIR_FRAG"] = load_shader("bent_normal_object_dir_frag.glsl")


__all__ = (
    "FULLSCREEN_VERT",
    "BENT_NORMAL_OBJECT_DIR_FRAG",
    "load_shader",
    "reload_shaders",
)

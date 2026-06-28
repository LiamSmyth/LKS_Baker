"""Load wireframe map-type GLSL sources."""
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


WIREFRAME_UV_RASTER_FRAG = load_shader("wireframe_uv_raster_frag.glsl")


def reload_shaders() -> None:
    """Clear cached GLSL sources (dev edits without restarting Blender)."""
    load_shader.cache_clear()
    globals().update(
        {
            "WIREFRAME_UV_RASTER_FRAG": load_shader("wireframe_uv_raster_frag.glsl"),
        }
    )


__all__ = (
    "FULLSCREEN_VERT",
    "WIREFRAME_UV_RASTER_FRAG",
    "load_shader",
    "reload_shaders",
)

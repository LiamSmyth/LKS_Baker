"""Load image-filter GLSL sources."""
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


SWITCH_NORMAL_FRAG = load_shader("switch_normal_frag.glsl")
FLIP_PNG_V_FRAG = load_shader("flip_png_v_frag.glsl")
NORMALIZE_SIGNED_FRAG = load_shader("normalize_signed_frag.glsl")
NORMALIZE_POSITIVE_FRAG = load_shader("normalize_positive_frag.glsl")
BLUR_PASS_FRAG = load_shader("blur_pass_frag.glsl")
DILATE_COLOR_PASS_FRAG = load_shader("dilate_color_pass_frag.glsl")
DILATE_VALID_PASS_FRAG = load_shader("dilate_valid_pass_frag.glsl")


def reload_shaders() -> None:
    """Clear cached GLSL sources (dev edits without restarting Blender)."""
    load_shader.cache_clear()
    globals().update(
        {
            "SWITCH_NORMAL_FRAG": load_shader("switch_normal_frag.glsl"),
            "FLIP_PNG_V_FRAG": load_shader("flip_png_v_frag.glsl"),
            "NORMALIZE_SIGNED_FRAG": load_shader("normalize_signed_frag.glsl"),
            "NORMALIZE_POSITIVE_FRAG": load_shader("normalize_positive_frag.glsl"),
            "BLUR_PASS_FRAG": load_shader("blur_pass_frag.glsl"),
            "DILATE_COLOR_PASS_FRAG": load_shader("dilate_color_pass_frag.glsl"),
            "DILATE_VALID_PASS_FRAG": load_shader("dilate_valid_pass_frag.glsl"),
        }
    )


__all__ = (
    "BLUR_PASS_FRAG",
    "DILATE_COLOR_PASS_FRAG",
    "DILATE_VALID_PASS_FRAG",
    "FLIP_PNG_V_FRAG",
    "FULLSCREEN_VERT",
    "NORMALIZE_POSITIVE_FRAG",
    "NORMALIZE_SIGNED_FRAG",
    "SWITCH_NORMAL_FRAG",
    "load_shader",
    "reload_shaders",
)

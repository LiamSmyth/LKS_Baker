"""Shared Blender gpu offscreen runtime (upload, draw, readback)."""
from __future__ import annotations

import numpy as np

from lks_baker.bake_ops.engine.static_utilities.runtime_log import log, timed_step

_GPU_RUNTIME: bool | None = None


def reset_gpu_runtime_cache() -> None:
    """Clear cached GPUOffScreen probe (after factory reset or new GL context)."""
    global _GPU_RUNTIME
    _GPU_RUNTIME = None


def _read_color_rgba(fb, width: int, height: int, *, offscreen_format: str) -> np.ndarray:
    """Read an offscreen color attachment using Blender's documented buffer layout."""
    pixel_count = width * height * 4
    if offscreen_format == "RGBA8":
        read_fmt = "UBYTE"
        scale = 1.0 / 255.0
    else:
        read_fmt = "FLOAT"
        scale = 1.0

    buf = fb.read_color(0, 0, width, height, 4, 0, read_fmt)
    buf.dimensions = pixel_count
    rgba = np.array(buf[:], dtype=np.float32).reshape(height, width, 4)
    if scale != 1.0:
        rgba *= scale
    return rgba


def gpu_module_available() -> bool:
    """Return True when the ``gpu`` module imports."""
    try:
        import gpu  # noqa: F401

        return True
    except ImportError:
        return False


def gpu_runtime_available() -> bool:
    """True only when GPUOffScreen can actually be allocated (not in --background)."""
    global _GPU_RUNTIME
    if _GPU_RUNTIME is not None:
        return _GPU_RUNTIME
    if not gpu_module_available():
        _GPU_RUNTIME = False
        return False
    try:
        import gpu

        with timed_step("GPUOffScreen probe (8x8)"):
            offscreen = gpu.types.GPUOffScreen(8, 8)
            del offscreen
        _GPU_RUNTIME = True
        log("gpu_runtime_available=True")
    except Exception as exc:
        _GPU_RUNTIME = False
        log(f"gpu_runtime_available=False ({type(exc).__name__}: {exc})")
    return _GPU_RUNTIME


def gpu_available() -> bool:
    """Legacy alias for ``gpu_module_available``."""
    return gpu_module_available()


def encode_normal_rgba(normal: np.ndarray) -> np.ndarray:
    rgba = np.ones((*normal.shape[:2], 4), dtype=np.float32)
    rgba[..., :3] = (normal * 0.5 + 0.5).clip(0.0, 1.0)
    return rgba


def upload_rgba_texture(rgba: np.ndarray):
    """Upload PNG-layout RGBA (row 0 = top) for OpenGL V=1-at-top sampling."""
    import gpu

    upload = np.ascontiguousarray(np.flipud(rgba.astype(np.float32)))
    height, width = upload.shape[:2]
    buffer = gpu.types.Buffer("FLOAT", upload.size, upload)
    return gpu.types.GPUTexture(size=(width, height), format="RGBA32F", data=buffer)


def upload_island_texture(island_id: np.ndarray):
    import gpu

    upload = np.ascontiguousarray(np.flipud(island_id.astype(np.float32)))
    height, width = upload.shape[:2]
    buffer = gpu.types.Buffer("FLOAT", upload.size, upload)
    return gpu.types.GPUTexture(size=(width, height), format="R32F", data=buffer)


def _compile_gpu_shader(
    vert: str,
    frag: str,
    sampler_names: list[str],
    push_constants: list[tuple[str, str, int]],
):
    import gpu
    from gpu.types import GPUShaderCreateInfo, GPUStageInterfaceInfo

    iface = GPUStageInterfaceInfo("bake_engine_iface")
    iface.smooth("VEC2", "texCoord_interp")

    info = GPUShaderCreateInfo()
    info.vertex_in(0, "VEC2", "pos")
    info.vertex_out(iface)
    info.fragment_out(0, "VEC4", "fragColor")
    info.vertex_source(vert)
    info.fragment_source(frag)
    for type_name, name, size in push_constants:
        if size:
            info.push_constant(type_name, name, size)
        else:
            info.push_constant(type_name, name)
    for slot, name in enumerate(sampler_names):
        info.sampler(slot, "FLOAT_2D", name)
    return gpu.shader.create_from_info(info)


def _set_shader_uniform(shader, name: str, value: object) -> None:
    if isinstance(value, int) and not isinstance(value, bool):
        shader.uniform_int(name, value)
    elif isinstance(value, (list, tuple)):
        shader.uniform_float(name, value)
    else:
        shader.uniform_float(name, float(value))


_OFFSCREEN_FORMAT = "RGBA32F"
"""Internal offscreen color attachment — MUST stay ≥16-bit (see bake-engine-internal-bit-depth.mdc)."""


def _png_layout_from_readback(field: np.ndarray) -> np.ndarray:
    """Flip readback rows to PNG layout (row 0 = top), matching CPU numpy arrays."""
    return np.flipud(field.astype(np.float32, copy=False))


def upload_float_rgb_texture(rgb: np.ndarray, *, alpha: float = 1.0):
    """Upload H×W×3 float field as RGBA32F (PNG row 0 = top)."""
    height, width = rgb.shape[:2]
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[..., :3] = rgb.astype(np.float32, copy=False)
    rgba[..., 3] = alpha
    return upload_rgba_texture(rgba)


def upload_offset_table(offsets: list[tuple[int, int]]):
    """Upload (dx, dy) integer ring offsets as a 1×N RG32F lookup texture."""
    import gpu

    count = len(offsets)
    if count <= 0:
        count = 1
        table = np.zeros((1, 1, 2), dtype=np.float32)
    else:
        table = np.zeros((1, count, 2), dtype=np.float32)
        for index, (dy, dx) in enumerate(offsets):
            table[0, index, 0] = float(dx)
            table[0, index, 1] = float(dy)
    flat = np.ascontiguousarray(table.reshape(-1))
    buffer = gpu.types.Buffer("FLOAT", flat.size, flat)
    return gpu.types.GPUTexture(size=(count, 1), format="RG32F", data=buffer)


class FullscreenOffscreenSession:
    """Reuse one compiled shader + ``GPUOffScreen`` for many fullscreen draws.

    When *ping_pong* is ``True`` a second internal ``GPUOffScreen`` is
    allocated and ``draw_gpu_color_texture`` alternates between the two on
    every call.  This prevents read-write aliasing (grid/plaid artifacts) when
    the texture returned by one call is fed back as a sampler input on the
    next call to the same session — the common pattern in multi-pass BFS /
    JFA loops.
    """

    def __init__(
        self,
        vert: str,
        frag: str,
        width: int,
        height: int,
        *,
        sampler_names: tuple[str, ...],
        push_constants: tuple[tuple[str, str, int], ...],
        ping_pong: bool = False,
    ) -> None:
        import gpu
        from gpu_extras.batch import batch_for_shader

        self._width = width
        self._height = height
        self._offscreen: object | None = None
        self._offscreen_b: object | None = None
        self._ping_pong_write_to_b: bool = False
        self._last_written_offscreen: object | None = None
        with timed_step(f"GPUOffScreen session {width}x{height}"):
            self._offscreen = gpu.types.GPUOffScreen(width, height, format=_OFFSCREEN_FORMAT)
            if ping_pong:
                self._offscreen_b = gpu.types.GPUOffScreen(width, height, format=_OFFSCREEN_FORMAT)
        with timed_step("GPUShader compile (session)"):
            self._shader = _compile_gpu_shader(
                vert,
                frag,
                list(sampler_names),
                list(push_constants),
            )
        coords = ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0))
        self._batch = batch_for_shader(self._shader, "TRI_STRIP", {"pos": coords})

    def draw_rgba(
        self,
        uniforms: dict[str, object],
        textures: dict[str, object],
    ) -> np.ndarray:
        import gpu
        from mathutils import Matrix

        if self._offscreen is None:
            raise RuntimeError("FullscreenOffscreenSession already freed")

        with self._offscreen.bind():
            fb = gpu.state.active_framebuffer_get()
            gpu.state.viewport_set(0, 0, self._width, self._height)
            gpu.state.scissor_set(0, 0, self._width, self._height)
            gpu.state.blend_set("NONE")
            gpu.state.depth_test_set("NONE")
            fb.clear(color=(0.0, 0.0, 0.0, 0.0))
            self._shader.bind()
            for name, value in uniforms.items():
                _set_shader_uniform(self._shader, name, value)
            for name, tex in textures.items():
                self._shader.uniform_sampler(name, tex)
            with gpu.matrix.push_pop():
                gpu.matrix.load_matrix(Matrix.Identity(4))
                gpu.matrix.load_projection_matrix(Matrix.Identity(4))
                self._batch.draw(self._shader)
            rgba = _read_color_rgba(
                fb,
                self._width,
                self._height,
                offscreen_format=_OFFSCREEN_FORMAT,
            )
        return _png_layout_from_readback(rgba)

    def draw_gpu_color_texture(
        self,
        uniforms: dict[str, object],
        textures: dict[str, object],
    ) -> object:
        """Run one fullscreen pass; return the color attachment (no CPU readback).

        When the session was created with *ping_pong=True*, alternates between
        two internal offscreens so the previously returned ``texture_color`` is
        never the render target for this call — avoiding read-write aliasing
        when the caller feeds the result straight back as a sampler input.
        """
        import gpu
        from mathutils import Matrix

        if self._offscreen is None:
            raise RuntimeError("FullscreenOffscreenSession already freed")

        if self._offscreen_b is not None:
            target = self._offscreen_b if self._ping_pong_write_to_b else self._offscreen
            self._ping_pong_write_to_b = not self._ping_pong_write_to_b
        else:
            target = self._offscreen

        with target.bind():
            fb = gpu.state.active_framebuffer_get()
            gpu.state.viewport_set(0, 0, self._width, self._height)
            gpu.state.scissor_set(0, 0, self._width, self._height)
            gpu.state.blend_set("NONE")
            gpu.state.depth_test_set("NONE")
            fb.clear(color=(0.0, 0.0, 0.0, 0.0))
            self._shader.bind()
            for name, value in uniforms.items():
                _set_shader_uniform(self._shader, name, value)
            for name, tex in textures.items():
                self._shader.uniform_sampler(name, tex)
            with gpu.matrix.push_pop():
                gpu.matrix.load_matrix(Matrix.Identity(4))
                gpu.matrix.load_projection_matrix(Matrix.Identity(4))
                self._batch.draw(self._shader)
            self._last_written_offscreen = target
            return target.texture_color

    def read_color_rgba(self) -> np.ndarray:
        """Read the last ``draw_gpu_color_texture`` result via ``read_color()``."""
        import gpu

        target = self._last_written_offscreen or self._offscreen
        if target is None:
            raise RuntimeError("FullscreenOffscreenSession already freed")

        with target.bind():
            fb = gpu.state.active_framebuffer_get()
            rgba = _read_color_rgba(
                fb,
                self._width,
                self._height,
                offscreen_format=_OFFSCREEN_FORMAT,
            )
        return _png_layout_from_readback(rgba)

    def free(self) -> None:
        if self._offscreen is not None:
            self._offscreen.free()
            self._offscreen = None
        if self._offscreen_b is not None:
            self._offscreen_b.free()
            self._offscreen_b = None


def run_fullscreen_shader_rgba(
    vert: str,
    frag: str,
    width: int,
    height: int,
    uniforms: dict[str, object],
    textures: dict[str, object],
    *,
    sampler_names: tuple[str, ...],
    push_constants: tuple[tuple[str, str, int], ...],
) -> np.ndarray:
    """Run a single fullscreen pass; compiles shader and allocates FBO each call."""
    session = FullscreenOffscreenSession(
        vert,
        frag,
        width,
        height,
        sampler_names=sampler_names,
        push_constants=push_constants,
    )
    try:
        return session.draw_rgba(uniforms, textures)
    finally:
        session.free()


def run_fullscreen_shader(
    vert: str,
    frag: str,
    width: int,
    height: int,
    uniforms: dict[str, object],
    textures: dict[str, object],
    *,
    sampler_names: tuple[str, ...],
    push_constants: tuple[tuple[str, str, int], ...],
) -> np.ndarray:
    """Run fullscreen shader; return the red channel in PNG row order."""
    rgba = run_fullscreen_shader_rgba(
        vert,
        frag,
        width,
        height,
        uniforms,
        textures,
        sampler_names=sampler_names,
        push_constants=push_constants,
    )
    return rgba[..., 0].astype(np.float32, copy=False)

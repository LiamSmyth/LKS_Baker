"""Resolve Blender executable and launch headless test scripts."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def resolve_blender_exe(
    *,
    cli_value: str | None = None,
    allow_running_inside_blender: bool = True,
) -> str:
    """Return a Blender binary path from CLI, env, running session, or PATH."""
    if cli_value:
        path = Path(cli_value).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Blender executable not found: {cli_value}")
        return str(path.resolve())

    env = os.environ.get("BLENDER_EXE", "").strip()
    if env:
        path = Path(env).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"BLENDER_EXE points to missing file: {env}")
        return str(path.resolve())

    if allow_running_inside_blender:
        try:
            import bpy

            binary = getattr(bpy.app, "binary_path", None)
            if binary:
                return str(Path(binary).resolve())
        except ImportError:
            pass

        exe = Path(sys.executable)
        if "blender" in exe.name.lower():
            return str(exe.resolve())

    found = shutil.which("blender")
    if found:
        return str(Path(found).resolve())

    raise RuntimeError(
        "Blender executable required. Pass --blender-exe PATH or set BLENDER_EXE."
    )


def add_blender_exe_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--blender-exe",
        dest="blender_exe",
        default=None,
        help="Path to blender.exe (overrides BLENDER_EXE)",
    )


def launch_docstring(script_file: Path, *, suite: str | None = None) -> str:
    """Canonical launch lines for test module docstrings."""
    rel = script_file.as_posix()
    suite_line = f"\n  python tests/run_tests.py --suite {suite}" if suite else ""
    return (
        "Launch (system Python):\n"
        f"  python tests/run_tests.py --script {rel} --mode blender\n"
        f"  python tests/blender_headless.py --blender-exe PATH --script {rel}\n"
        "Launch (inside Blender):\n"
        f"  blender.exe --background --factory-startup --python-exit-code 1 "
        f"--python {rel}"
        f"{suite_line}"
    )


def run_blender_python_script(
    blender_exe: str,
    script_path: Path,
    *,
    background: bool = True,
    factory_startup: bool = True,
    python_exit_code: int = 1,
    cwd: Path | None = None,
    timeout: float | None = 600.0,
    extra_blender_args: Sequence[str] = (),
    script_args: Sequence[str] = (),
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a Python script inside Blender."""
    script_path = script_path.resolve()
    if not script_path.is_file():
        raise FileNotFoundError(script_path)

    cmd: list[str] = [blender_exe]
    if background:
        cmd.append("--background")
    if factory_startup:
        cmd.append("--factory-startup")
    cmd.extend(["--python-exit-code", str(python_exit_code), "--python", str(script_path)])
    if script_args:
        cmd.append("--")
        cmd.extend(script_args)

    if extra_blender_args:
        cmd[1:1] = list(extra_blender_args)

    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)

    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        timeout=timeout,
        check=False,
        text=True,
        env=run_env,
    )


def build_launch_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    add_blender_exe_argument(parser)
    return parser

"""Reload every importable Python module in the addon from disk.

Used on addon enable and by the debug hot-reload operator so in-memory code
matches files on disk before bpy classes are registered.
"""
from __future__ import annotations

import importlib
import pathlib
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _ModuleEntry:
    name: str
    is_package_init: bool
    depth: int


def _resolve_root_pkg_name(root_pkg_name: str | None) -> str:
    if root_pkg_name:
        return root_pkg_name
    if __package__:
        return __package__
    return "lks_baker"


def _addon_root_path(root_pkg_name: str) -> pathlib.Path:
    root_module = sys.modules.get(root_pkg_name)
    if root_module is None or not getattr(root_module, "__file__", None):
        raise RuntimeError(f"Package {root_pkg_name!r} is not loaded.")
    return pathlib.Path(root_module.__file__).resolve().parent


def collect_addon_module_entries(root_pkg_name: str | None = None) -> list[_ModuleEntry]:
    """Return every importable module entry discovered under the addon root."""
    pkg_name = _resolve_root_pkg_name(root_pkg_name)
    root_path = _addon_root_path(pkg_name)
    entries: list[_ModuleEntry] = []

    for py_path in sorted(root_path.rglob("*.py")):
        rel_parts = py_path.relative_to(root_path).parts
        if any(part.startswith(".") or part == "__pycache__" for part in rel_parts):
            continue
        # Dev probe/headless scripts under tests/ are not addon runtime modules.
        if rel_parts and rel_parts[0] == "tests":
            continue

        if py_path.name == "__init__.py":
            if len(rel_parts) == 1:
                continue
            mod_name = pkg_name + "." + ".".join(rel_parts[:-1])
            is_init = True
        else:
            mod_name = pkg_name + "." + ".".join(
                py_path.relative_to(root_path).with_suffix("").parts
            )
            is_init = False

        entries.append(
            _ModuleEntry(
                name=mod_name,
                is_package_init=is_init,
                depth=mod_name.count("."),
            )
        )

    seen: set[str] = set()
    unique: list[_ModuleEntry] = []
    for entry in entries:
        if entry.name in seen:
            continue
        seen.add(entry.name)
        unique.append(entry)
    return unique


def _sort_entries_for_reload(entries: list[_ModuleEntry]) -> list[_ModuleEntry]:
    # Deepest leaf modules first; package __init__ modules after their siblings.
    return sorted(
        entries,
        key=lambda entry: (-entry.depth, 1 if entry.is_package_init else 0, entry.name),
    )


def reload_addon_python_modules(
    root_pkg_name: str | None = None,
    *,
    reload_register_main: bool = True,
) -> tuple[list[str], list[str]]:
    """Import/reload every addon module from disk in dependency-safe order."""
    pkg_name = _resolve_root_pkg_name(root_pkg_name)
    importlib.invalidate_caches()

    entries = _sort_entries_for_reload(collect_addon_module_entries(pkg_name))
    register_addon_name = f"{pkg_name}.register_addon"

    reloaded: list[str] = []
    failed: list[str] = []

    for entry in entries:
        if reload_register_main and entry.name == register_addon_name:
            continue
        if _reload_module(entry.name, reloaded, failed):
            continue

    if reload_register_main:
        _reload_module(register_addon_name, reloaded, failed)

    print(
        f"[LKS Baker] Reloaded {len(reloaded)} Python modules"
        + (f" ({len(failed)} failed)" if failed else "")
    )
    return reloaded, failed


def _reload_module(mod_name: str, reloaded: list[str], failed: list[str]) -> bool:
    try:
        mod = sys.modules.get(mod_name)
        if mod is None:
            mod = importlib.import_module(mod_name)
        else:
            importlib.reload(mod)
        reloaded.append(mod_name)
        return True
    except Exception as exc:
        failed.append(mod_name)
        print(f"[LKS Baker] Failed to reload {mod_name}: {exc}")
        return False

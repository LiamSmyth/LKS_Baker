"""Operator test discovery helpers (no bpy dependency)."""

from __future__ import annotations

import ast
from pathlib import Path

ADDON_PACKAGE = "lks_baker"
REGISTER_MAIN = "register_main.py"

_SKIP_DIR_NAMES = {"_deprecated", ".deprecated", "__pycache__"}
_SKIP_FILE_PREFIXES = ("register_", "ui_", "helpers_")
_SKIP_FILE_NAMES = {"__init__.py"}


def should_skip_operator_file(path: Path) -> bool:
    if path.name in _SKIP_FILE_NAMES:
        return True
    if any(part in _SKIP_DIR_NAMES for part in path.parts):
        return True
    if any(path.name.startswith(p) for p in _SKIP_FILE_PREFIXES):
        return True
    if path.name.startswith(("LKS_UL_", "VIEW3D_PT_", "LKS_PT_")):
        return True
    return False


def _is_operator_ast_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Attribute) and base.attr == "Operator":
            return True
        if isinstance(base, ast.Name) and base.id == "Operator":
            return True
    return False


def discover_operator_classes_in_file(path: Path) -> list[str]:
    """Parse a module file and return Operator subclass names."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef) and _is_operator_ast_class(node)]


def module_import_path(addon_root: Path, operator_file: Path) -> str:
    rel = operator_file.resolve().relative_to(addon_root)
    parts = list(rel.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return f"{ADDON_PACKAGE}." + ".".join(parts)


def addon_parent_depth(test_path: Path) -> int:
    """Index into Path.parents for the directory containing register_main.py."""
    for depth, parent in enumerate(test_path.resolve().parents):
        if (parent / REGISTER_MAIN).is_file():
            return depth
    return 3

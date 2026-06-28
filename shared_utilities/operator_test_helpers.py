"""Shared helpers for headless operator loadability and poll tests."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any, Callable

import addon_utils
import bpy

from .operator_test_discovery import (
    ADDON_PACKAGE,
    REGISTER_MAIN,
    addon_parent_depth,
    discover_operator_classes_in_file,
    module_import_path,
    should_skip_operator_file,
)


def resolve_addon_root_from_test_file(test_file: Path) -> Path:
    """Walk parents until the directory containing register_main.py is found."""
    path = test_file.resolve()
    for parent in path.parents:
        if (parent / REGISTER_MAIN).is_file():
            return parent
    raise FileNotFoundError(
        f"Could not resolve addon root from {test_file} (no {REGISTER_MAIN} in parents)"
    )


def bootstrap_addon(test_file: Path | None = None) -> Path:
    """Enable only lks_baker for headless test scripts. Returns addon root."""
    if test_file is not None:
        addon_root = resolve_addon_root_from_test_file(test_file)
    else:
        addon_root = Path(__file__).resolve().parents[1]

    parent = str(addon_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    enabled = {m.__name__ for m in addon_utils.modules()}
    if ADDON_PACKAGE not in enabled:
        import lks_baker  # noqa: F401

        lks_baker.register()
    else:
        addon_utils.enable(ADDON_PACKAGE, default_set=True, persistent=True)

    return addon_root


def collect_operator_classes_in_module(module: Any) -> list[type]:
    """Return Operator subclasses defined in module (not re-imported bases)."""
    ops: list[type] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, bpy.types.Operator):
            continue
        if obj is bpy.types.Operator:
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        ops.append(obj)
    ops.sort(key=lambda cls: cls.__name__)
    return ops


def _operator_registered(op_class: type) -> bool:
    bl_idname = getattr(op_class, "bl_idname", None)
    if not bl_idname or not isinstance(bl_idname, str):
        return False
    parts = bl_idname.split(".", 1)
    if len(parts) != 2:
        return False
    cat, name = parts
    try:
        op_mod = getattr(bpy.ops, cat)
        return hasattr(op_mod, name)
    except AttributeError:
        return False


def test_operator_loadability(op_class: type, label: str | None = None) -> list[str]:
    """Layer 2: bl_idname, bl_label, and bpy.ops registration."""
    tag = label or op_class.__name__
    failures: list[str] = []

    bl_idname = getattr(op_class, "bl_idname", None)
    if not bl_idname or not isinstance(bl_idname, str):
        failures.append(f"{tag}: missing or invalid bl_idname")
    elif "." not in bl_idname:
        failures.append(f"{tag}: bl_idname must be 'category.name', got {bl_idname!r}")

    bl_label = getattr(op_class, "bl_label", None)
    if not bl_label or not isinstance(bl_label, str):
        failures.append(f"{tag}: missing or invalid bl_label")

    if bl_idname and not _operator_registered(op_class):
        failures.append(f"{tag}: {bl_idname} not registered in bpy.ops")

    status = "FAIL" if failures else "PASS"
    print(f"  [{status}] loadability {tag}")
    return failures


def get_view3d_override() -> dict[str, Any] | None:
    """Best-effort VIEW_3D context dict for temp_override (headless-safe)."""
    wm = bpy.context.window_manager
    if wm is None:
        return None
    for window in wm.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            return {
                "window": window,
                "screen": screen,
                "area": area,
                "region": region,
                "scene": bpy.context.scene,
            }
    return None


def test_operator_poll_false_default_context(
    op_class: type,
    label: str | None = None,
    *,
    allow_true_without_view3d: bool = False,
) -> tuple[list[str], str | None]:
    """Layer 4: poll is False without mesh selection, or skip when poll needs only VIEW_3D."""
    tag = label or op_class.__name__
    if not hasattr(op_class, "poll"):
        print(f"  [SKIP] poll {tag}: no poll() defined")
        return [], "no poll"

    def _poll() -> bool:
        return bool(op_class.poll(bpy.context))

    try:
        if _poll() is False:
            print(f"  [PASS] poll_false {tag} (default context)")
            return [], None

        view3d = get_view3d_override()
        if view3d is not None:
            cleared = {
                **view3d,
                "active_object": None,
                "selected_objects": [],
            }
            with bpy.context.temp_override(**cleared):
                if _poll() is False:
                    print(f"  [PASS] poll_false {tag} (no active mesh)")
                    return [], None

        if allow_true_without_view3d and view3d is None:
            print(f"  [SKIP] poll {tag}: True without VIEW_3D (no override available)")
            return [], "poll true without view3d"

        if view3d is not None:
            with bpy.context.temp_override(**view3d):
                if _poll() is True:
                    print(
                        f"  [SKIP] poll {tag}: True with VIEW_3D only "
                        "(valid minimal context; add layer-3 execute test)"
                    )
                    return [], "poll true view3d only"

        msg = f"{tag}: expected poll() False on default or cleared-mesh context, got True"
        print(f"  [FAIL] poll_false {tag}")
        return [msg], None
    except Exception as exc:
        msg = f"{tag}: poll() raised {type(exc).__name__}: {exc}"
        print(f"  [FAIL] poll {tag}: {exc}")
        return [msg], None


def invoke_operator(
    bl_idname: str,
    *,
    context_override: dict[str, Any] | None = None,
    **kwargs: Any,
) -> set[str]:
    """Invoke bpy.ops operator; optional temp_override context."""
    cat, name = bl_idname.split(".", 1)
    op_callable = getattr(getattr(bpy.ops, cat), name)
    if context_override:
        with bpy.context.temp_override(**context_override):
            return set(op_callable(**kwargs))
    return set(op_callable(**kwargs))


def create_mesh_cube(name: str = "TestCube") -> bpy.types.Object:
    """Minimal mesh cube linked to the active collection."""
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    if cube is not None:
        cube.name = name
    return cube


def select_active(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def run_test_suite(failures: list[str], suite_name: str = "operator tests") -> None:
    """Print summary and exit 0/1 for headless Blender."""
    if failures:
        print(f"\n{suite_name}: {len(failures)} failure(s)")
        for item in failures:
            print(f"  FAIL: {item}")
        raise SystemExit(1)
    print(f"\n{suite_name}: all passed")
    raise SystemExit(0)


def run_named_tests(tests: list[tuple[str, Callable[[], list[str]]]]) -> None:
    """Run (name, fn) pairs; fn returns failure messages."""
    failures: list[str] = []
    for name, fn in tests:
        print(f"\n== {name} ==")
        try:
            failures.extend(fn())
        except Exception as exc:
            msg = f"{name}: unhandled {type(exc).__name__}: {exc}"
            print(f"  [FAIL] {msg}")
            failures.append(msg)
    run_test_suite(failures)


def import_operator_module(addon_root: Path, operator_file: Path) -> Any:
    bootstrap_addon()
    dotted = module_import_path(addon_root, operator_file)
    return importlib.import_module(dotted)

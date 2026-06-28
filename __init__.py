"""LKS Baker — Blender addon.

Minimal __init__.py: deep-reloads all submodules then delegates to register_addon.
"""

import importlib
import sys

bl_info = {
    "name": "LKS Baker",
    "author": "LKS",
    "version": (1, 0, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > LKS Baker",
    "description": "LKS Baker — standalone texture baking toolkit",
    "category": "3D View",
}

_PACKAGE: str = __package__


def _reload_package() -> None:
    """Deep-reload all modules under this package (deepest first)."""
    pkg_modules: list[str] = sorted(
        [name for name in sys.modules if name ==
            _PACKAGE or name.startswith(_PACKAGE + ".")],
        key=lambda n: n.count("."),
        reverse=True,
    )
    for mod_name in pkg_modules:
        try:
            importlib.reload(sys.modules[mod_name])
        except Exception as exc:
            print(f"[{_PACKAGE}] reload skip {mod_name}: {exc}")


def register() -> None:
    _reload_package()
    from . import register_addon
    register_addon.register_addon()


def unregister() -> None:
    from . import register_addon
    register_addon.unregister_addon()

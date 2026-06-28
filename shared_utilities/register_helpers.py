"""Shared bpy class registration helpers for submodule registrars."""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Sequence

import bpy


def register_classes(classes: Sequence[type]) -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_classes(classes: Sequence[type]) -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


def reload_modules(modules: Iterable) -> None:
    for module in modules:
        importlib.reload(module)

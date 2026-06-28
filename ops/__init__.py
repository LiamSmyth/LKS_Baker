"""Operators for LKS Baker.

Import all operator classes and register them here.
Add new operators as separate files in ops/, then import and add to opsToRegister.
"""

import bpy

# from .my_operator import LKS_OT_MyOperator

opsToRegister: tuple = (
    # LKS_OT_MyOperator,
)


def register() -> None:
    for cls in opsToRegister:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(opsToRegister):
        bpy.utils.unregister_class(cls)

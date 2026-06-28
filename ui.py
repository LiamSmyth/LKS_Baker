"""UI panels for LKS Baker.

Defines the root sidebar panel. Submodule panels parent to ROOT_PANEL_ID.
"""

import bpy

# Other addons / submodules reference this to set bl_parent_id
ROOT_PANEL_ID: str = "VIEW3D_PT_lks_baker"


class VIEW3D_PT_AddonRoot(bpy.types.Panel):
    """LKS Baker root panel."""

    bl_idname = ROOT_PANEL_ID
    bl_label = "LKS Baker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LKS Baker"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        # Add addon-level UI here
        # layout.operator("object.lks_baker_do_thing")


_classes: tuple = (
    VIEW3D_PT_AddonRoot,
)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

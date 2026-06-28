"""Properties for LKS Baker.

Register scene-level properties used by the addon.
Add custom properties here as needed.
"""

import bpy


# Property name constants — use these everywhere to avoid typos
# PROP_MY_SETTING = "lks_baker_my_setting"


def register() -> None:
    """Register addon properties on bpy.types.Scene."""
    # Example:
    # setattr(bpy.types.Scene, PROP_MY_SETTING, bpy.props.BoolProperty(
    #     name="My Setting",
    #     default=False,
    # ))
    pass


def unregister() -> None:
    """Remove addon properties from bpy.types.Scene."""
    # Example:
    # if hasattr(bpy.types.Scene, PROP_MY_SETTING):
    #     delattr(bpy.types.Scene, PROP_MY_SETTING)
    pass

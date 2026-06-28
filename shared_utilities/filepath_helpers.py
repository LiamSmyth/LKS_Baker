from pathlib import Path
import bpy


def get_abspath_from_relpath(relative_path: str) -> Path:

    # Get the directory of the current blend file
    absolute_path = Path(bpy.path.abspath(relative_path))

    return absolute_path

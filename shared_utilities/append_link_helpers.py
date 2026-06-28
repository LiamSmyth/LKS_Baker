import bpy
import os
from enum import Enum
from pathlib import Path


class BlendImportTypes(Enum):
    """
    Enum for the types of data that can be imported from a Blender file.
    """
    MESH = "Mesh"
    MATERIAL = "Material"
    NODETREE = "NodeTree"
    OBJECT = "Object"
    SCENE = "Scene"
    COLLECTION = "Collection"
    WORLD = "World"
    LIGHT = "Light"
    CAMERA = "Camera"
    CURVE = "Curve"
    FONT = "Font"
    GREASEPENCIL = "GreasePencil"
    ANNOTATION = "Annotation"
    IMAGE = "Image"
    LATTICE = "Lattice"
    MASK = "Mask"
    MOVIECLIP = "MovieClip"
    PAINTCURVE = "PaintCurve"
    PALETTE = "Palette"
    PARTICLESETTINGS = "ParticleSettings"
    SHAPEKEY = "ShapeKey"
    SOUND = "Sound"
    SPEAKER = "Speaker"
    TEXT = "Text"
    VOLUME = "Volume"
    WINDOWMANAGER = "WindowManager"
    WORKSPACE = "WorkSpace"
    # Add other data types as needed


# Mapping from data type string to bpy.data collection attribute name
_DATA_TYPE_TO_ATTR = {
    'Mesh': 'meshes',
    'Material': 'materials',
    'NodeTree': 'node_groups',
    'Object': 'objects',
    'Scene': 'scenes',
    'Collection': 'collections',
    'World': 'worlds',
    'Light': 'lights',
    'Camera': 'cameras',
    'Curve': 'curves',
    'Font': 'fonts',
    'GreasePencil': 'grease_pencils',
    'Annotation': 'annotations',
    'Image': 'images',
    'Lattice': 'lattices',
    'Mask': 'masks',
    'MovieClip': 'movieclips',
    'PaintCurve': 'paint_curves',
    'Palette': 'palettes',
    'ParticleSettings': 'particles',
    'ShapeKey': 'shape_keys',
    'Sound': 'sounds',
    'Speaker': 'speakers',
    'Text': 'texts',
    'Volume': 'volumes',
    'WindowManager': 'window_managers',
    'WorkSpace': 'workspaces',
}


def add_data_from_blender_file(data_type: str, data_name: str, blendfile_path: Path, link: bool = False):
    """
    Adds data from a Blender file to the current blendfile.

    Uses bpy.data.libraries.load() which is context-independent and works
    in both Object mode and Edit mode (unlike bpy.ops.wm.append).

    Args:
        data_type (str): The type of data to add (e.g., 'Mesh', 'Material', 'Object').
        data_name (str): The name of the data to add.
        blendfile_path (Path): The path to the Blender file.
        link (bool, optional): Whether to link the data or append it. Defaults to False.

    Returns:
        bpy.types.ID: The last matching data block that was added.

    Raises:
        Exception: If the specified data type is not recognized.
        Exception: If no data is found starting with the specified name.
    """
    attr_name = _DATA_TYPE_TO_ATTR.get(data_type)
    if not attr_name:
        raise Exception(f"Data type {data_type} not recognized.")

    # Get absolute path to the Blender file as a string
    blender_file_path = str(blendfile_path.absolute())

    # Use bpy.data.libraries.load() - context-independent, works in any mode
    with bpy.data.libraries.load(blender_file_path, link=link) as (data_from, data_to):
        # Get the source collection from the external file
        source_names = getattr(data_from, attr_name)
        if data_name not in source_names:
            raise Exception(
                f"No data named '{data_name}' found in {blender_file_path}")
        # Assign the names we want to load to the target collection
        setattr(data_to, attr_name, [data_name])

    # Retrieve the loaded data block from local bpy.data
    data_collection = getattr(bpy.data, attr_name)

    # Filter data blocks with a name starting with data_name
    matching_data_blocks = [
        db for db in data_collection if db.name.startswith(data_name)]

    if not matching_data_blocks:
        raise Exception(f"No data found starting with the name: {data_name}")

    # Return the last matching data block
    return matching_data_blocks[-1]


def add_mesh_from_blender_file(mesh_name: str, blendfile_path: Path, link=False) -> bpy.types.Mesh:
    """
    Adds a mesh object from a Blender file.

    Args:
        mesh_name (str): The name of the mesh object to be added.
        blendfile_path (Path): The path to the Blender file.
        link (bool, optional): Whether to link the mesh object or append it. Defaults to False.

    Returns:
        bpy.types.Mesh: The added mesh object.
    """
    return add_data_from_blender_file(BlendImportTypes.MESH.value, mesh_name, blendfile_path, link)


def add_material_from_blender_file(material_name: str, blendfile_path: Path, link=False) -> bpy.types.Material:
    """
    Adds a material from a Blender file.

    Args:
        material_name (str): The name of the material to add.
        blendfile_path (Path): The path to the Blender file.
        link (bool, optional): Whether to link the material or append it. Defaults to False.

    Returns:
        bpy.types.Material: The added material.
    """
    return add_data_from_blender_file(BlendImportTypes.MATERIAL.value, material_name, blendfile_path, link)


def add_node_tree_from_blender_file(node_tree_name: str, blendfile_path: Path, link=False) -> bpy.types.NodeTree:
    """
    Adds a node tree from a Blender file.

    Args:
        node_tree_name (str): The name of the node tree to add.
        blendfile_path (Path): The path to the Blender file.
        link (bool, optional): Whether to link the node tree or not. Defaults to False.

    Returns:
        bpy.types.NodeTree: The added node tree.
    """
    return add_data_from_blender_file(BlendImportTypes.NODETREE.value, node_tree_name, blendfile_path, link)


def add_object_from_blender_file(object_name: str, blendfile_path: Path, link: bool = False) -> bpy.types.Object:
    """
    Adds an object from a Blender file to the current scene.

    Args:
        object_name (str): The name of the object to be added.
        blendfile_path (Path): The path to the Blender file.
        link (bool, optional): Whether to link the object or append it. Defaults to False.

    Returns:
        bpy.types.Object: The added object.
    """
    return add_data_from_blender_file(BlendImportTypes.OBJECT.value, object_name, blendfile_path, link)

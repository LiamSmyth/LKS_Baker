import bpy


def delete_everything() -> None:
    """
    Deletes all objects, meshes, lights, cameras, images, collections, brushes, materials, texts, textures, node groups,
    linestyles, and actions from the current Blender scene.
    """
    for scene in bpy.data.scenes:
        scene: bpy.types.Scene = scene
        for obj in scene.objects:
            obj: bpy.types.Object = obj
            bpy.data.objects.remove(obj, do_unlink=True)

    for bpy_data_iter in (
            bpy.data.objects,
            bpy.data.meshes,
            bpy.data.lights,
            bpy.data.cameras,
            bpy.data.images,
            bpy.data.collections,
            bpy.data.brushes,
            bpy.data.materials,
            bpy.data.texts,
            bpy.data.textures,
            bpy.data.node_groups,
            bpy.data.linestyles,
            bpy.data.actions,
    ):
        for id_data in bpy_data_iter:
            id_data: bpy.types.ID = id_data
            bpy_data_iter.remove(id_data, do_unlink=True)

import bpy
import os
import pathlib
import random
import math
import enum
import mathutils
import numpy


def get_selection_bbox_extents():
    sel = []
    selUnfiltered = bpy.context.selected_objects

    for obj in selUnfiltered:
        if obj.type == "MESH":
            sel.append(obj)

    if (len(sel) == 0):
        return

    obj = sel[0]
    min_bbox = mathutils.Vector([math.inf, math.inf, math.inf])
    max_bbox = mathutils.Vector([-math.inf, -math.inf, -math.inf])

    for obj in sel:
        obj: bpy.types.Object = obj

        local_bbox_pts = obj.bound_box

        world_bbox_pts = []
        for vector in local_bbox_pts:

            world_bbox_pts.append(mathutils.Matrix(
                obj.matrix_world) @ mathutils.Vector(vector))

        for pt_pos in world_bbox_pts:
            # print(str(pt_pos))
            i = 0
            for component in pt_pos:
                # print(str(component))
                min_bbox[i] = min(min_bbox[i], component)
                max_bbox[i] = max(max_bbox[i], component)
                i += 1

    print('Min bbox extent: (' + str(min_bbox[0]) + ", " +
          str(min_bbox[1]) + ", " + str(min_bbox[2]) + ")")
    print('Max bbox extent: (' + str(max_bbox[0]) + ", " +
          str(max_bbox[1]) + ", " + str(max_bbox[2]) + ")")

    extents = [min_bbox, max_bbox]
    return extents


def get_selection_bbox_centroid():
    extents = get_selection_bbox_extents()
    min_extent: mathutils.Vector = extents[0]
    max_extent: mathutils.Vector = extents[1]

    centroid = (((max_extent - min_extent) / 2) + min_extent)

    print('centroid: ' + str(centroid))

    return centroid


def get_selection_bbox_size():
    extents = get_selection_bbox_extents()
    centroid = get_selection_bbox_centroid()
    min_extent_local = extents[0] - centroid
    max_extent_local = extents[1] - centroid

    size = mathutils.Vector([0, 0, 0])
    i = 0
    for component in size:
        size[i] = abs(min_extent_local[i]) + abs(max_extent_local[i])
        i += 1

    return size


def add_box_at_selection():
    centroid = get_selection_bbox_centroid()
    size = get_selection_bbox_size()

    bpy.ops.mesh.primitive_cube_add(location=centroid, scale=size, size=1)


def move_selected_bbox_centroid_to_origin():
    sel = bpy.context.selected_objects
    centroid = get_selection_bbox_centroid()
    print(centroid)
    for obj in sel:
        obj.location = obj.location - centroid


def move_selected_to_origin_and_set_size(targetSize=1):
    sel = bpy.context.selected_objects
    move_selected_bbox_centroid_to_origin()
    extents = get_selection_bbox_extents()

    bpy.ops.object.make_single_user(
        object=True, obdata=True, material=False, animation=False)
    # bpy.ops.view3d.snap_cursor_to_center()
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
    bpy.ops.object.transform_apply(
        location=True, rotation=True, scale=True)

    current_size = get_selection_bbox_size()
    maxDimension = 0

    for component in current_size:
        maxDimension = max(maxDimension, component)

    scaleFactor = targetSize / maxDimension

    for obj in sel:
        obj.scale = [scaleFactor, scaleFactor, scaleFactor]

    bpy.ops.object.transform_apply(
        location=True, rotation=True, scale=True)
    # print(size)


def move_selected_to_floor():
    sel = bpy.context.selected_objects
    extents = get_selection_bbox_extents()
    min_z = extents[0][2]

    for obj in sel:
        obj.location[2] = obj.location[2] - min_z


def calculateFlipXFormAboutCursorForObj(obj: bpy.types.Object, flipAxisXYZ: int = 0):
    """
    Calculates the transformation matrix required to flip an object around a specified axis, with the cursor as the pivot point.

    Args:
        obj (bpy.types.Object): The object to be flipped.
        flipAxisXYZ (int, optional): The axis around which to flip the object. Defaults to 0.

    Returns:
        list: A list containing the flipped location, rotation, and scale values.
    """
    cursorPos = bpy.context.scene.cursor.location
    obj.rotation_mode = 'XYZ'
    location = obj.location.copy()
    rotation = obj.rotation_euler.copy()
    scale = obj.scale.copy()

    # manip loc
    location[flipAxisXYZ] = (
        location[flipAxisXYZ] - cursorPos[flipAxisXYZ]) * -1 + cursorPos[flipAxisXYZ]

    i = 0
    for axis in rotation:
        if i == flipAxisXYZ:
            pass
        else:
            rotation[i] = rotation[i] * -1
        i += 1

    scale[flipAxisXYZ] = scale[flipAxisXYZ] * -1

    return [location, rotation, scale]

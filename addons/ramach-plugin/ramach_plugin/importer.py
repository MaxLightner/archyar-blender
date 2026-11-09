"""Import helpers: preserve source topology and clean only imported assets."""

from pathlib import Path
import math

import bmesh
import bpy
from mathutils import Vector


EXTENSIONS = {'.obj', '.fbx', '.glb', '.gltf'}


def _import_file(filepath):
    ext = filepath.suffix.lower()
    if ext == '.obj':
        bpy.ops.wm.obj_import(filepath=str(filepath))
    elif ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=str(filepath), use_image_search=True)
    elif ext in {'.glb', '.gltf'}:
        bpy.ops.import_scene.gltf(filepath=str(filepath))
    else:
        raise ValueError(f"Unsupported format: {ext}")


def mesh_counts(objects):
    triangles = quads = ngons = 0
    seen_meshes = set()
    for obj in objects:
        if obj.type != 'MESH' or obj.data in seen_meshes:
            continue
        seen_meshes.add(obj.data)
        for face in obj.data.polygons:
            if len(face.vertices) == 3:
                triangles += 1
            elif len(face.vertices) == 4:
                quads += 1
            else:
                ngons += 1
    return triangles, quads, ngons


def clean_imported_meshes(objects, merge_distance, recover_quads):
    """Weld only vertices *inside the same mesh*; do not join separate objects."""
    merged = 0
    seen_meshes = set()
    for obj in objects:
        if obj.type != 'MESH' or obj.data in seen_meshes:
            continue
        mesh = obj.data
        seen_meshes.add(mesh)
        if mesh.shape_keys:
            continue  # BMesh conversion could invalidate shape keys.
        if not merge_distance and not recover_quads:
            continue
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            before = len(bm.verts)
            if merge_distance:
                bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=merge_distance)
                merged += before - len(bm.verts)
            if recover_quads:
                triangle_faces = [face for face in bm.faces if len(face.verts) == 3]
                if triangle_faces:
                    bmesh.ops.join_triangles(
                        bm, faces=triangle_faces,
                        angle_face_threshold=math.radians(30),
                        angle_shape_threshold=math.radians(30),
                        cmp_seam=True, cmp_sharp=True, cmp_uvs=True,
                        cmp_vcols=True, cmp_materials=True,
                    )
            bm.to_mesh(mesh)
            mesh.update()
        finally:
            bm.free()
    return merged


def world_mesh_bounds(objects):
    mesh_objects = [obj for obj in objects if obj.type == 'MESH']
    if not mesh_objects:
        return None
    first = mesh_objects[0].matrix_world @ Vector(mesh_objects[0].bound_box[0])
    mins = list(first)
    maxs = list(first)
    for obj in mesh_objects:
        matrix = obj.matrix_world
        for corner in obj.bound_box:
            point = matrix @ Vector(corner)
            for axis in range(3):
                mins[axis] = min(mins[axis], point[axis])
                maxs[axis] = max(maxs[axis], point[axis])
    return Vector(mins), Vector(maxs)


def model_dimensions(root):
    if root is None:
        return (0.0, 0.0, 0.0)
    descendants = list(root.children_recursive)
    bounds = world_mesh_bounds(descendants)
    if bounds is None:
        return (0.0, 0.0, 0.0)
    minimum, maximum = bounds
    return tuple(float(maximum[axis] - minimum[axis]) for axis in range(3))


def create_floor_root(context, filename, imported_objects):
    bounds = world_mesh_bounds(imported_objects)
    if bounds is None:
        return None
    minimum, maximum = bounds
    pivot = Vector(((minimum.x + maximum.x) / 2,
                    (minimum.y + maximum.y) / 2,
                    minimum.z))
    root = bpy.data.objects.new("RM_" + Path(filename).stem + "_ROOT", None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.15
    root["ramach_model_root"] = True
    root["ramach_source_filename"] = str(filename)
    context.scene.collection.objects.link(root)
    root.location = pivot
    context.view_layer.update()

    imported_set = set(imported_objects)
    top_objects = [obj for obj in imported_objects if obj.parent not in imported_set]
    for obj in top_objects:
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
    context.view_layer.update()
    # Translating the parent moves every imported object without joining meshes.
    root.location.z -= minimum.z
    context.view_layer.update()
    return root


def import_and_prepare(context, filepath, settings):
    filepath = Path(filepath)
    if filepath.suffix.lower() not in EXTENSIONS:
        raise ValueError("Supported formats: OBJ, FBX, GLB, glTF")
    before = set(bpy.data.objects)
    _import_file(filepath)
    imported = [obj for obj in bpy.data.objects if obj not in before]
    if not imported:
        raise ValueError("Importer did not create any objects")
    merged = clean_imported_meshes(
        imported,
        settings.merge_distance if settings.merge_on_import else None,
        settings.recover_quads,
    )
    context.view_layer.update()
    root = create_floor_root(context, filepath.name, imported) if settings.floor_pivot else None
    bpy.ops.object.select_all(action='DESELECT')
    selected = root or next((obj for obj in imported if obj.type == 'MESH'), imported[0])
    selected.select_set(True)
    context.view_layer.objects.active = selected
    triangles, quads, ngons = mesh_counts(imported)
    return {
        'root': root,
        'imported': imported,
        'merged': merged,
        'triangles': triangles,
        'quads': quads,
        'ngons': ngons,
    }

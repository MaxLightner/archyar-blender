"""Run with Blender 4.3+: blender -b --factory-startup --python tests/smoke.py."""

import io
from pathlib import Path
import sys
import tempfile
import zipfile

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ramach_plugin
from ramach_plugin import importer, updater


def approx(a, b, error=0.0001):
    assert abs(a - b) < error, (a, b)


ramach_plugin.register()
settings = bpy.context.scene.ramach_settings
assert settings.merge_on_import
assert settings.floor_pivot
assert settings.lock_proportions

# Two adjacent boxes, with matching but disconnected boundary vertices.
vertices = []
faces = []
unit_faces = [
    (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
    (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
]
for offset in (0, 1):
    verts = [(offset+0,0,0), (offset+1,0,0), (offset+1,1,0), (offset+0,1,0),
             (offset+0,0,1), (offset+1,0,1), (offset+1,1,1), (offset+0,1,1)]
    start = len(vertices)
    vertices += verts
    faces += [tuple(start+i for i in f) for f in unit_faces]

mesh = bpy.data.meshes.new("weld_test")
mesh.from_pydata(vertices, [], faces)
mesh.update()
model = bpy.data.objects.new("weld_test", mesh)
bpy.context.scene.collection.objects.link(model)
model.location = (4.0, 3.0, 2.0)
bpy.context.view_layer.update()

assert len(model.data.vertices) == 16
merged = importer.clean_imported_meshes([model], 0.0001, False)
assert merged == 4, f"Expected 4 duplicate vertices to merge, got {merged}"
assert len(model.data.vertices) == 12

root = importer.create_floor_root(bpy.context, "tripo_source.obj", [model])
assert root and root.get("ramach_model_root")
assert model.parent == root
approx(root.location.z, 0)
min_bounds, max_bounds = importer.world_mesh_bounds([model])
approx(min_bounds.z, 0)
approx(root.location.x, 5)
approx(root.location.y, 3.5)

settings.model_root = root
approx(settings.size_x, 2)
approx(settings.size_y, 1)
approx(settings.size_z, 1)
settings.size_x = 4.0
approx(settings.size_x, 4)
approx(settings.size_y, 2)
approx(settings.size_z, 2)
approx(importer.world_mesh_bounds([model])[0].z, 0)

# A valid package ZIP parser rejects unrelated repo contents and accepts owned source.
output = io.BytesIO()
with zipfile.ZipFile(output, 'w') as z:
    z.writestr("commit-root/addons/ramach-plugin/ramach_plugin/__init__.py", "bl_info={}")
    z.writestr("commit-root/archyar_blender/__init__.py", "unrelated")
package = updater._package_files_from_archive(output.getvalue())
assert len(package) == 1 and Path("__init__.py") in package

with tempfile.TemporaryDirectory(prefix="ramach-smoke-") as tempdir:
    bpy.ops.object.select_all(action='DESELECT')
    model.select_set(True)
    bpy.context.view_layer.objects.active = model
    objfile = str(Path(tempdir) / "quad_test.obj")
    bpy.ops.wm.obj_export(filepath=objfile, export_selected_objects=True)
    report = importer.import_and_prepare(bpy.context, Path(objfile), settings)
    assert report['imported'], "OBJ import failed"
    assert report['quads'] > 0, "OBJ quad topology was not preserved"
    assert report['root'], "Floor pivot root was not created on import"
    approx(importer.world_mesh_bounds(report['imported'])[0].z, 0)

    # glTF/GLB stores triangle primitives; a quad cannot survive that encoding.
    bpy.ops.object.select_all(action='DESELECT')
    model.select_set(True)
    bpy.context.view_layer.objects.active = model
    glbfile = str(Path(tempdir) / "triangles.glb")
    bpy.ops.export_scene.gltf(filepath=glbfile, export_format='GLB', use_selection=True)
    glb_report = importer.import_and_prepare(bpy.context, Path(glbfile), settings)
    assert glb_report['triangles'] > 0
    assert glb_report['quads'] == 0, "GLB unexpectedly preserved quad faces"

    # Pairing source triangles into quads is opt-in and only heuristic.
    tri_mesh = bpy.data.meshes.new("two_triangles")
    tri_mesh.from_pydata([(0,0,0), (1,0,0), (1,1,0), (0,1,0)],
                         [], [(0,1,2), (0,2,3)])
    tri_mesh.update()
    tri_obj = bpy.data.objects.new("two_triangles", tri_mesh)
    bpy.context.scene.collection.objects.link(tri_obj)
    importer.clean_imported_meshes([tri_obj], None, True)
    assert len(tri_obj.data.polygons) == 1
    assert len(tri_obj.data.polygons[0].vertices) == 4

ramach_plugin.unregister()
print("RAMACH_SMOKE_OK: merge, pivot, proportional sizes, OBJ quads, GLB triangles, quad recovery, updater parser")

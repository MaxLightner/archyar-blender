"""Ramach Plugin: minimal, non-destructive furniture import foundation."""

bl_info = {
    "name": "Ramach Plugin",
    "author": "Ramach System",
    "version": (0, 1, 0),
    "blender": (4, 3, 0),
    "location": "3D Viewport > Sidebar > Ramach",
    "description": "Import Tripo models, weld doubles, set floor pivot and proportional dimensions",
    "category": "Import-Export",
}

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
    StringProperty,
)

from . import importer, updater


_syncing_dimensions = False


def _model_root(settings):
    root = settings.model_root
    if root is None or not root.get("ramach_model_root"):
        return None
    return root


def sync_dimensions(context, settings):
    global _syncing_dimensions
    if _syncing_dimensions:
        return
    root = _model_root(settings)
    dims = importer.model_dimensions(root) if root else (0.0, 0.0, 0.0)
    _syncing_dimensions = True
    try:
        settings.size_x, settings.size_y, settings.size_z = dims
    finally:
        _syncing_dimensions = False


def _on_root_change(self, context):
    sync_dimensions(context, self)


def _dimension_update(axis):
    def callback(self, context):
        if _syncing_dimensions or context is None:
            return
        root = _model_root(self)
        if not root:
            return
        desired = (self.size_x, self.size_y, self.size_z)[axis]
        current = importer.model_dimensions(root)[axis]
        if desired <= 0 or current <= 0:
            return
        factor = desired / current
        if abs(factor - 1) <= 1e-7:
            return
        if self.lock_proportions:
            for i in range(3):
                root.scale[i] *= factor
        else:
            root.scale[axis] *= factor
        context.view_layer.update()
        sync_dimensions(context, self)
    return callback


class RamachSettings(bpy.types.PropertyGroup):
    mode: EnumProperty(
        name="Mode",
        items=[
            ('LAYOUT', "Layout", "Furniture asset preparation"),
            ('KITCHEN', "Kitchen", "Reserved for future kitchen tools"),
            ('ARCH', "Architecture", "Reserved for future architecture tools"),
            ('MAX', "Max", "Reserved for future modeling tools"),
        ],
        default='LAYOUT',
    )
    merge_on_import: BoolProperty(
        name="Merge by Distance",
        description="Weld near-identical vertices within each imported mesh only",
        default=True,
    )
    merge_distance: FloatProperty(
        name="Merge Distance",
        description="Distance in Blender units (default 0.1 mm when 1 unit = 1 m)",
        default=0.0001,
        min=0.000001,
        max=0.05,
        precision=6,
        subtype='DISTANCE',
    )
    recover_quads: BoolProperty(
        name="Try Recover Quads",
        description="Heuristic triangle pairing; original quad topology cannot be restored exactly from GLB",
        default=False,
    )
    floor_pivot: BoolProperty(
        name="Bottom-Center Pivot + Z=0",
        description="Create a parent Empty at the model's bottom center and place its lowest point on the floor",
        default=True,
    )
    model_root: PointerProperty(name="Model Root", type=bpy.types.Object, update=_on_root_change)
    lock_proportions: BoolProperty(name="Lock Proportions", default=True)
    size_x: FloatProperty(name="Width (X)", subtype='DISTANCE', min=0.000001, precision=4, update=_dimension_update(0))
    size_y: FloatProperty(name="Depth (Y)", subtype='DISTANCE', min=0.000001, precision=4, update=_dimension_update(1))
    size_z: FloatProperty(name="Height (Z)", subtype='DISTANCE', min=0.000001, precision=4, update=_dimension_update(2))
    last_report: StringProperty(name="Import Report", default="No model imported yet")


class RAMACH_OT_import_model(bpy.types.Operator):
    bl_idname = "ramach.import_model"
    bl_label = "Import Tripo Model"
    bl_description = "Import OBJ, FBX, GLB or glTF, optionally weld vertices and set floor pivot"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')
    directory: StringProperty(subtype='DIR_PATH')
    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    filter_glob: StringProperty(default="*.obj;*.fbx;*.glb;*.gltf", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        # Blender FileHandler supplies a filepath on drag/drop. Import directly
        # instead of opening a second file browser for the dropped model.
        if self.filepath or len(self.files):
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from pathlib import Path
        paths = ([Path(self.directory) / item.name for item in self.files]
                 if self.files else [Path(self.filepath)])
        paths = [p for p in paths if p.is_file()]
        if not paths:
            self.report({'ERROR'}, "No valid model file selected")
            return {'CANCELLED'}
        settings = context.scene.ramach_settings
        reports = []
        for path in paths:
            try:
                report = importer.import_and_prepare(context, path, settings)
                reports.append(report)
                if report['root']:
                    settings.model_root = report['root']
            except Exception as exc:
                self.report({'WARNING'}, f"{path.name}: {str(exc)[:150]}")
        if not reports:
            return {'CANCELLED'}
        merged = sum(item['merged'] for item in reports)
        tris = sum(item['triangles'] for item in reports)
        quads = sum(item['quads'] for item in reports)
        settings.last_report = f"{len(reports)} file(s) | merged {merged} verts | {tris} tris / {quads} quads"
        self.report({'INFO'}, settings.last_report)
        return {'FINISHED'}


class RAMACH_FH_models(bpy.types.FileHandler):
    bl_idname = "RAMACH_FH_models"
    bl_label = "Ramach Model Import"
    bl_import_operator = "ramach.import_model"
    bl_file_extensions = ".glb;.gltf;.fbx;.obj"

    @classmethod
    def poll_drop(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'


class RAMACH_OT_sync_size(bpy.types.Operator):
    bl_idname = "ramach.sync_size"
    bl_label = "Read Model Dimensions"
    bl_description = "Refresh the width, depth and height from the selected model root"

    def execute(self, context):
        sync_dimensions(context, context.scene.ramach_settings)
        return {'FINISHED'}


class VIEW3D_PT_ramach(bpy.types.Panel):
    bl_label = "Ramach Plugin"
    bl_idname = "VIEW3D_PT_ramach"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Ramach"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ramach_settings
        layout.prop(settings, "mode", expand=True)
        if settings.mode != 'LAYOUT':
            layout.label(text="Tools will be added in future updates", icon='INFO')
            return
        layout.operator("ramach.import_model", icon='IMPORT', text="Import / Drop Model")
        layout.label(text="Drag OBJ / FBX / GLB into the 3D View", icon='INFO')
        layout.prop(settings, "merge_on_import")
        if settings.merge_on_import:
            layout.prop(settings, "merge_distance")
        layout.prop(settings, "recover_quads")
        layout.prop(settings, "floor_pivot")
        layout.label(text=settings.last_report, icon='MESH_DATA')
        box = layout.box()
        box.label(text="Model Dimensions", icon='DRIVER_DISTANCE')
        box.prop(settings, "model_root")
        box.prop(settings, "lock_proportions", icon='LINKED' if settings.lock_proportions else 'UNLINKED')
        col = box.column(align=True)
        col.enabled = _model_root(settings) is not None
        col.prop(settings, "size_x")
        col.prop(settings, "size_y")
        col.prop(settings, "size_z")
        box.operator("ramach.sync_size", icon='FILE_REFRESH')


class VIEW3D_PT_ramach_updates(bpy.types.Panel):
    bl_label = "Updates"
    bl_idname = "VIEW3D_PT_ramach_updates"
    bl_parent_id = "VIEW3D_PT_ramach"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("ramach.update_from_github", icon='FILE_REFRESH')
        layout.label(text="Restart Blender after updating", icon='INFO')


CLASSES = (
    RamachSettings,
    RAMACH_OT_import_model,
    RAMACH_FH_models,
    RAMACH_OT_sync_size,
    VIEW3D_PT_ramach,
    VIEW3D_PT_ramach_updates,
    updater.RAMACH_OT_update,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ramach_settings = PointerProperty(type=RamachSettings)


def unregister():
    del bpy.types.Scene.ramach_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

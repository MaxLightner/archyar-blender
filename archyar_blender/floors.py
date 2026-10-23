"""Semantic building storeys: named metric levels, visibility and active editing scope.

The add-on retains generated Blender meshes, but only top-level Archyar controllers
own a floor ID.  Children (cutters, opening leaves, furniture parts) inherit their
host's floor and cannot be accidentally placed on another storey.
"""

import uuid

import bpy
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, IntProperty, StringProperty


_updating = False


def roots(scene):
    """Top-level Archyar controllers in the current scene, not mesh children."""
    return [obj for obj in scene.objects if obj.get("archyar_kind") and
            not (obj.parent and obj.parent.get("archyar_kind"))]


def active_floor(scene, create=False):
    entries = getattr(scene, "archyar_floors", None)
    if entries is None:
        return None
    if not entries and create:
        ensure_floors(scene)
    index = getattr(scene, "archyar_floor_index", 0)
    return entries[index] if entries and 0 <= index < len(entries) else None


def tag_root(root, scene=None):
    """Attach only a semantic root to the current storey, preserving existing IDs."""
    if root.parent is not None or root.get("archyar_floor_id"):
        return
    scene = scene or bpy.context.scene
    floor = active_floor(scene, create=True)
    if floor is not None:
        root["archyar_floor_id"] = floor.floor_id
        root["archyar_floor_elevation"] = floor.elevation
        root["archyar_floor_ceiling"] = floor.ceiling


def _walk(root):
    yield root
    for child in root.children:
        yield from _walk(child)


def refresh_visibility(scene):
    floor = active_floor(scene)
    if floor is None:
        return
    entries = {f.floor_id: f for f in scene.archyar_floors}
    solo = scene.archyar_solo_floor
    for root in roots(scene):
        owner = entries.get(root.get("archyar_floor_id"))
        if owner is None:
            continue  # Preserve unrelated / legacy objects.
        hidden = not owner.visible or (solo and owner.floor_id != floor.floor_id)
        for obj in _walk(root):
            try:
                obj.hide_set(hidden)
                if not obj.get("archyar_preview"):
                    obj.hide_select = bool(owner.floor_id != floor.floor_id)
            except RuntimeError:
                pass  # The object is not in the current ViewLayer.
    active = bpy.context.view_layer.objects.active if bpy.context.view_layer else None
    controller = active
    while controller is not None and not controller.get("archyar_floor_id"):
        controller = controller.parent
    if controller is not None and controller.get("archyar_floor_id") != floor.floor_id:
        active.select_set(False)


def _active_changed(scene, _context):
    global _updating
    if _updating:
        return
    floor = active_floor(scene)
    if floor is None:
        return
    _updating = True
    try:
        scene.archyar_level_elevation = floor.elevation
        scene.archyar_height = floor.ceiling
    finally:
        _updating = False
    refresh_visibility(scene)


def _floor_changed(self, context):
    global _updating
    if _updating or context is None:
        return
    scene = context.scene
    _updating = True
    try:
        for root in roots(scene):
            if root.get("archyar_floor_id") != self.floor_id:
                continue
            previous = float(root.get("archyar_floor_elevation", self.elevation))
            delta = self.elevation - previous
            if root.get("archyar_kind") == "WALL":
                props = root.archyar_wall
                was_full_height = abs(props.height - float(root.get("archyar_floor_ceiling", self.ceiling))) < .001
                if abs(delta) > 1e-6:
                    props.elevation = self.elevation
                if was_full_height and abs(props.height - self.ceiling) > .001:
                    props.height = self.ceiling
            elif abs(delta) > 1e-6:
                root.location.z += delta
            root["archyar_floor_elevation"] = self.elevation
            root["archyar_floor_ceiling"] = self.ceiling
        if active_floor(scene) is not None and active_floor(scene).floor_id == self.floor_id:
            scene.archyar_level_elevation = self.elevation
            scene.archyar_height = self.ceiling
    finally:
        _updating = False
    refresh_visibility(scene)


def _visibility_changed(_self, context):
    if context is not None:
        refresh_visibility(context.scene)


class ArchyarFloor(bpy.types.PropertyGroup):
    floor_id: StringProperty(name="Floor ID")
    name: StringProperty(name="Name", default="Ground Floor")
    elevation: FloatProperty(name="Floor Elevation", default=0, min=-100, max=500,
                             unit='LENGTH', update=_floor_changed)
    ceiling: FloatProperty(name="Storey Height", default=3, min=.3, max=15,
                           unit='LENGTH', update=_floor_changed)
    visible: BoolProperty(name="Visible", default=True, update=_visibility_changed)


class ARCHYAR_UL_floors(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name or ("Floor %d" % (index+1)), icon='OUTLINER_COLLECTION')
        row.label(text="%.2f m" % item.elevation)
        row.prop(item, "visible", text="", emboss=False,
                 icon='HIDE_OFF' if item.visible else 'HIDE_ON')


def ensure_floors(scene):
    """Upgrade older .blend scenes without relocating or deleting any geometry."""
    if scene.archyar_floors:
        return
    global _updating
    _updating = True
    try:
        elevations = sorted({round(float(root.archyar_wall.elevation), 4)
                             for root in roots(scene) if root.get("archyar_kind") == "WALL"})
        if not elevations:
            elevations = [round(scene.archyar_level_elevation, 4)]
        for index, elevation in enumerate(elevations):
            floor = scene.archyar_floors.add()
            floor.floor_id = str(uuid.uuid4())
            floor.name = "Ground Floor" if index == 0 else "Level %d" % index
            floor.elevation = elevation
            floor.ceiling = 3.0
        for root in roots(scene):
            old_elevation = (root.archyar_wall.elevation if root.get("archyar_kind") == "WALL"
                             else root.location.z)
            floor = min(scene.archyar_floors, key=lambda item: abs(item.elevation-old_elevation))
            root["archyar_floor_id"] = floor.floor_id
            root["archyar_floor_elevation"] = floor.elevation
            root["archyar_floor_ceiling"] = floor.ceiling
        scene.archyar_floor_index = 0
    finally:
        _updating = False
    _active_changed(scene, None)


class ARCHYAR_OT_add_floor(bpy.types.Operator):
    bl_idname = "archyar.add_floor"
    bl_label = "Add Building Floor"
    bl_description = "Create a distinct storey above the active level"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        ensure_floors(scene)
        if len(scene.archyar_floors) >= 64:
            self.report({'ERROR'}, "Maximum 64 storeys")
            return {'CANCELLED'}
        base = active_floor(scene)
        new_elevation = base.elevation + base.ceiling
        new_floor = scene.archyar_floors.add()
        new_floor.floor_id = str(uuid.uuid4())
        new_floor.name = "Level %d" % (len(scene.archyar_floors)-1)
        new_floor.elevation = new_elevation
        new_floor.ceiling = base.ceiling
        scene.archyar_floor_index = len(scene.archyar_floors) - 1
        refresh_visibility(scene)
        return {'FINISHED'}


class ARCHYAR_OT_remove_floor(bpy.types.Operator):
    bl_idname = "archyar.remove_floor"
    bl_label = "Remove Empty Floor"
    bl_description = "Only removes a floor when it contains no Archyar elements"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        floor = active_floor(scene)
        if floor is None or len(scene.archyar_floors) == 1:
            self.report({'WARNING'}, "At least one floor must remain")
            return {'CANCELLED'}
        if any(root.get("archyar_floor_id") == floor.floor_id for root in roots(scene)):
            self.report({'WARNING'}, "Floor contains elements; move/remove them first")
            return {'CANCELLED'}
        scene.archyar_floors.remove(scene.archyar_floor_index)
        scene.archyar_floor_index = max(0, min(scene.archyar_floor_index,
                                              len(scene.archyar_floors)-1))
        return {'FINISHED'}


class VIEW3D_PT_archyar_floors(bpy.types.Panel):
    bl_label = "Building Floors"
    bl_idname = "VIEW3D_PT_archyar_floors"
    bl_parent_id = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        if not scene.archyar_floors:
            layout.operator("archyar.initialize_floors", text="Initialize Building Floors",
                            icon='ADD')
            return
        row = layout.row()
        row.template_list("ARCHYAR_UL_floors", "", scene, "archyar_floors",
                          scene, "archyar_floor_index", rows=3)
        buttons = row.column(align=True)
        buttons.operator("archyar.add_floor", text="", icon='ADD')
        buttons.operator("archyar.remove_floor", text="", icon='REMOVE')
        floor = active_floor(scene)
        if floor is not None:
            layout.prop(floor, "name")
            layout.prop(floor, "elevation")
            layout.prop(floor, "ceiling")
        layout.prop(scene, "archyar_solo_floor", text="Show Active Floor Only")
        layout.label(text="Other floors remain visible by default")


class ARCHYAR_OT_initialize_floors(bpy.types.Operator):
    bl_idname = "archyar.initialize_floors"
    bl_label = "Initialize Building Floors"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_floors(context.scene)
        return {'FINISHED'}


CLASSES = (ArchyarFloor, ARCHYAR_UL_floors, ARCHYAR_OT_initialize_floors,
           ARCHYAR_OT_add_floor, ARCHYAR_OT_remove_floor, VIEW3D_PT_archyar_floors)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.archyar_floors = CollectionProperty(type=ArchyarFloor)
    bpy.types.Scene.archyar_floor_index = IntProperty(name="Active Floor", default=0,
                                                        min=0, update=_active_changed)
    bpy.types.Scene.archyar_solo_floor = BoolProperty(name="Solo Floor", default=False,
                                                       update=_visibility_changed)


def unregister():
    for name in ("archyar_solo_floor", "archyar_floor_index", "archyar_floors"):
        delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

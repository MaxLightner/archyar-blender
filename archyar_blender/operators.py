"""Viewport-driven Archyar wall, opening and object placement."""

import math

import bpy
import gpu
from bpy.props import (BoolProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from . import geometry
from .catalog import (BUILD_PARTS, CATEGORY_NAMES, FURNITURE, OPENINGS,
                      WALL_PRESETS, furniture)
from .furniture import make_furniture


def _on_wall_change(self, context):
    if self.id_data is not None:
        geometry.refresh_wall(self.id_data)


class ArchyarWallSettings(bpy.types.PropertyGroup):
    start: FloatVectorProperty(name="Start XY", size=2, subtype='NONE', unit='LENGTH', update=_on_wall_change)
    end: FloatVectorProperty(name="End XY", size=2, subtype='NONE', unit='LENGTH', update=_on_wall_change)
    thickness: FloatProperty(name="Thickness", default=.15, min=.04, max=1.0, unit='LENGTH', update=_on_wall_change)
    height: FloatProperty(name="Height", default=3.0, min=.3, max=12.0, unit='LENGTH', update=_on_wall_change)
    show_length: BoolProperty(name="Always show length", default=True)


def _preset_change(self, context):
    self.archyar_thickness = WALL_PRESETS[self.archyar_wall_preset][1]


def _metres_ok(context):
    if abs(context.scene.unit_settings.scale_length - 1.0) > 1e-6:
        raise ValueError("Set Scene > Units > Unit Scale to 1.0 (one Blender unit = one metre)")


def _window_region(context):
    if context.area is None or context.area.type != 'VIEW_3D':
        raise ValueError("Run this tool from the 3D Viewport's Archyar sidebar")
    return next((r for r in context.area.regions if r.type == 'WINDOW'), None)


def ground_point(context, event):
    region = _window_region(context)
    if region is None:
        return None
    x = event.mouse_x - region.x
    y = event.mouse_y - region.y
    if x < 0 or y < 0 or x >= region.width or y >= region.height:
        return None
    rv3d = context.space_data.region_3d
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, (x, y))
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, (x, y))
    hit = intersect_line_plane(origin, origin + direction * 10000,
                               Vector((0, 0, 0)), Vector((0, 0, 1)), False)
    return hit


def snap_point(point, threshold=.12):
    best = Vector((point.x, point.y))
    dist = threshold
    for wall in bpy.data.objects:
        if wall.get("archyar_kind") != "WALL":
            continue
        for end in (wall.archyar_wall.start, wall.archyar_wall.end):
            value = Vector((end[0], end[1]))
            gap = (value - best).length
            if gap < dist:
                dist = gap
                best = value
    return tuple(best)


def nearest_wall(point, max_distance=.65):
    best, distance = None, max_distance
    p = Vector((point.x, point.y))
    for wall in bpy.data.objects:
        if wall.get("archyar_kind") != "WALL":
            continue
        a, b = (Vector(wall.archyar_wall.start), Vector(wall.archyar_wall.end))
        delta = b - a
        if delta.length_squared < 1e-9:
            continue
        t = max(0, min(1, (p-a).dot(delta) / delta.length_squared))
        gap = (p - a - delta*t).length
        if gap < distance:
            best, distance = wall, gap
    return best


def wall_fraction(wall, point):
    a, b = Vector(wall.archyar_wall.start), Vector(wall.archyar_wall.end)
    delta = b - a
    if delta.length_squared < 1e-9:
        raise ValueError("Invalid wall length")
    return max(0, min(1, (Vector((point.x, point.y)) - a).dot(delta) / delta.length_squared))


class _ViewportPlacement:
    _start = None
    _current = None
    _handler = None
    _created = 0

    def _init_modal(self, context, message):
        _metres_ok(context)
        if _window_region(context) is None:
            raise ValueError("3D Viewport window region was not found")
        self._start, self._current, self._created = None, None, 0
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_preview, (), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(message)
        return {'RUNNING_MODAL'}

    def _cleanup(self, context):
        if self._handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            self._handler = None
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def _draw_preview(self):
        if self._start is None or self._current is None:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {
            "pos": [(self._start[0], self._start[1], .03),
                    (self._current[0], self._current[1], .03)]})
        shader.bind()
        shader.uniform_float('color', (1.0, .60, .24, 1.0))
        gpu.state.line_width_set(3.0)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)


class ARCHYAR_OT_draw_wall(_ViewportPlacement, bpy.types.Operator):
    bl_idname = "archyar.draw_wall"
    bl_label = "Draw Archyar Wall"
    bl_description = "Click start and end points; continue drawing connected walls; Enter to finish"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        try:
            return self._init_modal(context, "Archyar wall: left-click start/end, Enter to finish, Esc to cancel")
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._cleanup(context)
            return {'FINISHED'} if self._created else {'CANCELLED'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'RUNNING_MODAL'}
        value = snap_point(point)
        if event.ctrl:
            value = tuple(round(v * 10) / 10 for v in value)
        self._current = value
        context.area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._start is None:
                self._start = value
            else:
                if geometry.length(self._start, value) < .10:
                    self.report({'WARNING'}, "Minimum wall length is 10 cm")
                    return {'RUNNING_MODAL'}
                try:
                    geometry.create_wall(self._start, value,
                        context.scene.archyar_thickness, context.scene.archyar_height,
                        context.scene.archyar_wall_preset)
                except ValueError as exc:
                    self.report({'ERROR'}, str(exc))
                    return {'RUNNING_MODAL'}
                self._created += 1
                self._start = value
        return {'RUNNING_MODAL'}


class ARCHYAR_OT_place_opening(_ViewportPlacement, bpy.types.Operator):
    bl_idname = "archyar.place_opening"
    bl_label = "Place Archyar Opening"
    bl_description = "Select a wall then click the opening's position in the viewport"
    bl_options = {'REGISTER', 'UNDO'}
    style: StringProperty(default="fixed")

    def invoke(self, context, event):
        self._wall = context.active_object if context.active_object and context.active_object.get("archyar_kind") == "WALL" else None
        try:
            return self._init_modal(context, "Archyar opening: click on an Archyar wall; Esc to cancel")
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and event.value == 'PRESS'):
            self._cleanup(context)
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'RUNNING_MODAL'}
        wall = self._wall or nearest_wall(point)
        if wall is None:
            self.report({'WARNING'}, "Select a wall or click within 65 cm of one")
            return {'RUNNING_MODAL'}
        try:
            geometry.create_opening(wall, wall_fraction(wall, point), self.style,
                context.scene.archyar_open_width, context.scene.archyar_open_height,
                0 if self.style in ('door', 'sliding-door') else context.scene.archyar_sill)
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'RUNNING_MODAL'}
        self._cleanup(context)
        return {'FINISHED'}


class ARCHYAR_OT_place_furniture(_ViewportPlacement, bpy.types.Operator):
    bl_idname = "archyar.place_furniture"
    bl_label = "Place Archyar Furniture"
    bl_description = "Choose an item and click on the floor; paintings attach to a wall"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty(min=0, max=21)

    def invoke(self, context, event):
        self._wall = context.active_object if context.active_object and context.active_object.get("archyar_kind") == "WALL" else None
        try:
            return self._init_modal(context, "Archyar furniture: click to place; Esc to cancel")
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and event.value == 'PRESS'):
            self._cleanup(context)
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'RUNNING_MODAL'}
        asset = furniture(self.index)
        if asset.wall_mounted:
            wall = self._wall or nearest_wall(point)
            if wall is None:
                self.report({'WARNING'}, "Choose a wall for wall-mounted artwork")
                return {'RUNNING_MODAL'}
            t = wall_fraction(wall, point)
            root = make_furniture(self.index, parent=wall)
            span = geometry.length(wall.archyar_wall.start, wall.archyar_wall.end)
            root.location = ((t-.5)*span, wall.archyar_wall.thickness/2+asset.depth/2+.035,
                             1.25-wall.archyar_wall.height/2)
            root["archyar_host_id"] = wall["archyar_id"]
            root["archyar_host_t"] = t
        else:
            make_furniture(self.index, (point.x, point.y, 0))
        self._cleanup(context)
        return {'FINISHED'}


class ARCHYAR_OT_place_structure(_ViewportPlacement, bpy.types.Operator):
    bl_idname = "archyar.place_structure"
    bl_label = "Place Archyar Structure"
    bl_description = "Create a simple parametric-category primitive at a clicked location"
    bl_options = {'REGISTER', 'UNDO'}
    kind: StringProperty(default="column")

    def invoke(self, context, event):
        if self.kind not in BUILD_PARTS:
            self.report({'ERROR'}, "Unknown structural tool")
            return {'CANCELLED'}
        try:
            return self._init_modal(context, "Archyar structure: click on ground plane")
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and event.value == 'PRESS'):
            self._cleanup(context)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'RUNNING_MODAL'}
        geometry.add_structure(self.kind, (point.x, point.y, 0))
        self._cleanup(context)
        return {'FINISHED'}


class VIEW3D_PT_archyar(bpy.types.Panel):
    bl_label = "Archyar"
    bl_idname = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Archyar"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        if abs(scene.unit_settings.scale_length - 1) > 1e-6:
            layout.label(text="Set scene unit scale to 1.0", icon='ERROR')
        layout.prop(scene, "archyar_section", expand=True)
        if scene.archyar_section == 'BUILD':
            layout.prop(scene, "archyar_wall_preset", text="Wall Type")
            layout.prop(scene, "archyar_thickness")
            layout.prop(scene, "archyar_height")
            layout.operator("archyar.draw_wall", text="Draw Wall (click points)", icon='MESH_CUBE')
            box_ui = layout.box()
            box_ui.label(text="Other architectural elements")
            for key, name in BUILD_PARTS.items():
                action = box_ui.operator("archyar.place_structure", text=name)
                action.kind = key
        elif scene.archyar_section == 'OPEN':
            layout.prop(scene, "archyar_open_width")
            layout.prop(scene, "archyar_open_height")
            layout.prop(scene, "archyar_sill")
            layout.label(text="Select wall, then choose opening:")
            for key, name in OPENINGS.items():
                action = layout.operator("archyar.place_opening", text=name)
                action.style = key
        elif scene.archyar_section == 'FURN':
            layout.prop(scene, "archyar_furn_category", text="Category")
            visible = [a for a in FURNITURE if a.category == scene.archyar_furn_category]
            for asset in visible:
                item = layout.operator("archyar.place_furniture", text=asset.name, icon='OUTLINER_OB_EMPTY')
                item.index = asset.index
            layout.label(text="Click in the viewport to place")
        else:
            layout.label(text="MEP modeling in a later phase", icon='INFO')


class VIEW3D_PT_archyar_edit(bpy.types.Panel):
    bl_label = "Selected Wall"
    bl_idname = "VIEW3D_PT_archyar_edit"
    bl_parent_id = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.get("archyar_kind") != "WALL":
            layout.label(text="Select an Archyar wall")
            return
        props = obj.archyar_wall
        layout.prop(props, "start")
        layout.prop(props, "end")
        layout.prop(props, "thickness")
        layout.prop(props, "height")
        layout.prop(props, "show_length")
        layout.label(text="Length: %.3f m" % geometry.length(props.start, props.end))


CLASSES = (ArchyarWallSettings, ARCHYAR_OT_draw_wall,
           ARCHYAR_OT_place_opening, ARCHYAR_OT_place_furniture,
           ARCHYAR_OT_place_structure, VIEW3D_PT_archyar, VIEW3D_PT_archyar_edit)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.archyar_wall = PointerProperty(type=ArchyarWallSettings)
    bpy.types.Scene.archyar_section = EnumProperty(name="Group", items=[
        ('BUILD', "Build", "Walls and architectural parts"),
        ('OPEN', "Openings", "Doors and windows"),
        ('FURN', "Furniture", "Chido catalog"),
        ('MEP', "Services", "Reserved for a future phase")])
    bpy.types.Scene.archyar_wall_preset = EnumProperty(name="Wall Type", items=[
        (key, label, label) for key, (label, _) in WALL_PRESETS.items()], update=_preset_change)
    bpy.types.Scene.archyar_thickness = FloatProperty(name="Wall Thickness", default=.15, min=.04, max=1, unit='LENGTH')
    bpy.types.Scene.archyar_height = FloatProperty(name="Wall Height", default=3.0, min=.3, max=12, unit='LENGTH')
    bpy.types.Scene.archyar_open_width = FloatProperty(name="Width", default=1.2, min=.3, max=6, unit='LENGTH')
    bpy.types.Scene.archyar_open_height = FloatProperty(name="Height", default=1.4, min=.3, max=6, unit='LENGTH')
    bpy.types.Scene.archyar_sill = FloatProperty(name="Sill Height", default=.9, min=0, max=6, unit='LENGTH')
    bpy.types.Scene.archyar_furn_category = EnumProperty(name="Furniture Category", items=[
        (key, label, label) for key, label in CATEGORY_NAMES.items()])


def unregister():
    for name in ("archyar_furn_category", "archyar_sill", "archyar_open_height",
                 "archyar_open_width", "archyar_height", "archyar_thickness",
                 "archyar_wall_preset", "archyar_section"):
        delattr(bpy.types.Scene, name)
    del bpy.types.Object.archyar_wall
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

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
from .constraints import require_stair

_ACTIVE_PLACEMENT = None


def _on_wall_change(self, context):
    if self.id_data is not None:
        geometry.refresh_wall(self.id_data)


class ArchyarWallSettings(bpy.types.PropertyGroup):
    start: FloatVectorProperty(name="Start XY", size=2, subtype='NONE', unit='LENGTH', update=_on_wall_change)
    end: FloatVectorProperty(name="End XY", size=2, subtype='NONE', unit='LENGTH', update=_on_wall_change)
    thickness: FloatProperty(name="Thickness", default=.15, min=.04, max=1.0, unit='LENGTH', update=_on_wall_change)
    height: FloatProperty(name="Height", default=3.0, min=.3, max=12.0, unit='LENGTH', update=_on_wall_change)
    elevation: FloatProperty(name="Base Elevation", default=0.0, min=-100, max=100, unit='LENGTH', update=_on_wall_change)
    show_length: BoolProperty(name="Always show length", default=True)


def _on_stair_change(self, context):
    root = self.id_data
    if root is not None and root.get("archyar_kind") == "STAIRS":
        try:
            geometry.rebuild_stair(root)
        except ValueError:
            # Retain the last valid geometry during multi-field edits.
            pass


class ArchyarStairSettings(bpy.types.PropertyGroup):
    run: FloatProperty(name="Total Run", default=3.0, min=.5, unit='LENGTH', update=_on_stair_change)
    width: FloatProperty(name="Stair Width", default=1.1, min=.5, max=5, unit='LENGTH', update=_on_stair_change)
    rise: FloatProperty(name="Total Rise", default=1.8, min=.15, max=9, unit='LENGTH', update=_on_stair_change)
    count: IntProperty(name="Steps", default=10, min=1, max=50, update=_on_stair_change)
    filled: BoolProperty(name="Filled Underside", default=False, update=_on_stair_change)


class ArchyarOpeningSettings(bpy.types.PropertyGroup):
    style: EnumProperty(name="Type", items=[(key, name, name) for key, name in OPENINGS.items()])
    width: FloatProperty(name="Width", default=1.2, min=.3, max=6, unit='LENGTH')
    height: FloatProperty(name="Height", default=1.4, min=.3, max=6, unit='LENGTH')
    sill: FloatProperty(name="Sill Height", default=.9, min=0, max=6, unit='LENGTH')
    offset: FloatProperty(name="Along Wall", default=0, min=0, max=100, unit='LENGTH')
    arch_rise: FloatProperty(name="Arch Rise", default=.25, min=0, max=4, unit='LENGTH')
    mirrored: BoolProperty(name="Mirrored", default=False)
    open_fraction: FloatProperty(name="Open Amount", default=0, min=0, max=1, subtype='FACTOR')


def load_opening_settings(root):
    """Copy authoritative object metadata into the non-destructive editing form."""
    if root.get("archyar_kind") != "OPENING":
        return
    props = root.archyar_opening
    wall = root.parent
    props.style = root["archyar_style"]
    props.width = root["width"]
    props.height = root["height"]
    props.sill = root["sill"]
    props.offset = root["archyar_t"] * geometry.length(wall.archyar_wall.start, wall.archyar_wall.end)
    props.arch_rise = root.get("archyar_arch_rise", min(.25, float(root["height"])*.35))
    props.mirrored = bool(root.get("archyar_mirrored", False))
    props.open_fraction = root.get("archyar_open_fraction", 0)


class ARCHYAR_OT_edit_opening(bpy.types.Operator):
    bl_idname = "archyar.edit_opening"
    bl_label = "Apply Opening Changes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = context.active_object
        if root is None or root.get("archyar_kind") != "OPENING":
            self.report({'ERROR'}, "Select an Archyar door or window")
            return {'CANCELLED'}
        p = root.archyar_opening
        wall = root.parent
        span = geometry.length(wall.archyar_wall.start, wall.archyar_wall.end)
        try:
            geometry.apply_opening(root, p.style, p.width, p.height, p.sill,
                                   p.offset / span, p.arch_rise if p.style == 'arched' else 0,
                                   p.mirrored, p.open_fraction)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        load_opening_settings(root)
        self.report({'INFO'}, "Opening updated")
        return {'FINISHED'}


class ARCHYAR_OT_load_opening(bpy.types.Operator):
    bl_idname = "archyar.load_opening"
    bl_label = "Reload Opening Values"
    def execute(self, context):
        load_opening_settings(context.active_object)
        return {'FINISHED'}


def _preset_change(self, context):
    self.archyar_thickness = WALL_PRESETS[self.archyar_wall_preset][1]


def _metres_ok(context):
    if abs(context.scene.unit_settings.scale_length - 1.0) > 1e-6:
        raise ValueError("Set Scene > Units > Unit Scale to 1.0 (one Blender unit = one metre)")


def _window_region(context):
    if context.area is None or context.area.type != 'VIEW_3D':
        raise ValueError("Run this tool from the 3D Viewport's Archyar sidebar")
    return next((r for r in context.area.regions if r.type == 'WINDOW'), None)


def ground_point(context, event, elevation=None):
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
    level = context.scene.archyar_level_elevation if elevation is None else elevation
    hit = intersect_line_plane(origin, origin + direction * 10000,
                               Vector((0, 0, level)),
                               Vector((0, 0, 1)), False)
    return hit


def snap_point(point, scene, threshold=.12, excluded=None):
    best = Vector((point.x, point.y))
    dist = threshold
    if scene.archyar_snap_points:
        for wall in bpy.data.objects:
            if (excluded and wall.name in excluded) or wall.get("archyar_kind") != "WALL" or abs(
                    wall.archyar_wall.elevation - scene.archyar_level_elevation) > .001:
                continue
            for end in (wall.archyar_wall.start, wall.archyar_wall.end):
                value = Vector((end[0], end[1]))
                gap = (value - Vector((point.x, point.y))).length
                if gap < dist:
                    dist = gap
                    best = value
    if dist == threshold and scene.archyar_snap_grid:
        step = scene.archyar_grid_step
        best = Vector((round(point.x / step) * step, round(point.y / step) * step))
    return tuple(best)


def nearest_wall(point, max_distance=.65, elevation=None):
    best, distance = None, max_distance
    p = Vector((point.x, point.y))
    for wall in bpy.data.objects:
        if wall.get("archyar_kind") != "WALL":
            continue
        if elevation is not None and abs(wall.archyar_wall.elevation-elevation)>.001:
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


def wall_connection_changes(wall, new_start, new_end):
    """Plan an atomic edit of this wall and any coincident connected endpoints."""
    old_start, old_end = tuple(wall.archyar_wall.start), tuple(wall.archyar_wall.end)
    if geometry.length(new_start, new_end) < .10:
        raise ValueError("Wall must be at least 10 cm long")
    changes = []
    for other in bpy.data.objects:
        if other.get("archyar_kind") != "WALL":
            continue
        if abs(other.archyar_wall.elevation - wall.archyar_wall.elevation) > .001:
            continue  # Same XY position on a different storey is not the same joint.
        props = other.archyar_wall
        before_a, before_b = tuple(props.start), tuple(props.end)
        after = []
        for before in (before_a, before_b):
            if geometry.length(before, old_start) < .001:
                after.append(tuple(new_start))
            elif geometry.length(before, old_end) < .001:
                after.append(tuple(new_end))
            else:
                after.append(before)
        if after[0] == before_a and after[1] == before_b:
            continue
        span = geometry.length(*after)
        if span < .10:
            raise ValueError("An attached wall would become shorter than 10 cm")
        # Openings keep their normalized position; reject edits that leave no margins.
        hosted = [child for child in other.children if child.get("archyar_kind") == "OPENING"]
        for opening in hosted:
            t, width = float(opening['archyar_t']), float(opening['width'])
            if (t * span - width / 2 < .099 or
                    t * span + width / 2 > span - .099):
                raise ValueError("A hosted opening would extend outside its wall")
        for i, left in enumerate(hosted):
            for right in hosted[i + 1:]:
                if abs(float(left['archyar_t']) - float(right['archyar_t'])) * span < (
                        float(left['width']) + float(right['width'])) / 2 + .05:
                    raise ValueError("Openings would overlap after the wall edit")
        changes.append((other, before_a, before_b, after[0], after[1]))
    return changes


def apply_wall_connection_changes(changes, reverse=False):
    for obj, before_a, before_b, after_a, after_b in changes:
        obj.archyar_wall.start = before_a if reverse else after_a
        obj.archyar_wall.end = before_b if reverse else after_b


class ARCHYAR_OT_set_wall_length(bpy.types.Operator):
    bl_idname = "archyar.set_wall_length"
    bl_label = "Set Exact Wall Length"
    bl_options = {'REGISTER', 'UNDO'}
    new_length: FloatProperty(name="Length", min=.1, max=1000, unit='LENGTH')
    fixed_end: EnumProperty(name="Keep Fixed", items=[
        ('START', "Start", "Keep the starting point fixed"),
        ('END', "End", "Keep the ending point fixed")])

    def invoke(self, context, event):
        wall = context.active_object
        if wall is None or wall.get("archyar_kind") != "WALL":
            return {'CANCELLED'}
        self.new_length = geometry.length(wall.archyar_wall.start, wall.archyar_wall.end)
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        wall = context.active_object
        if wall is None or wall.get("archyar_kind") != "WALL":
            return {'CANCELLED'}
        a, b = Vector(wall.archyar_wall.start), Vector(wall.archyar_wall.end)
        direction = (b - a).normalized()
        new_a, new_b = ((tuple(a), tuple(a + direction * self.new_length))
                        if self.fixed_end == 'START' else
                        (tuple(b - direction * self.new_length), tuple(b)))
        try:
            apply_wall_connection_changes(wall_connection_changes(wall, new_a, new_b))
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class ARCHYAR_OT_edit_wall_handles(bpy.types.Operator):
    bl_idname = "archyar.edit_wall_handles"
    bl_label = "Edit Wall Handles"
    bl_description = "Drag blue start/end handles or the orange centre handle; Enter finishes, Esc restores"
    bl_options = {'REGISTER', 'UNDO'}

    def _handle_points(self, context):
        wall = self._wall.archyar_wall
        a, b = Vector(wall.start), Vector(wall.end)
        z = wall.elevation + min(wall.height, 1.2)
        region = _window_region(context)
        rv3d = context.space_data.region_3d
        return [view3d_utils.location_3d_to_region_2d(region, rv3d,
                    Vector((p.x, p.y, z))) for p in (a, b, (a + b) / 2)]

    def _draw(self):
        context = bpy.context
        try:
            points = self._handle_points(context)
        except (AttributeError, ValueError):
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        for index, screen in enumerate(points):
            if screen is None:
                continue
            radius = 11 if index == 2 else 9
            center = (screen.x, screen.y, 0)
            verts = [center]
            for n in range(25):
                angle = n * math.tau / 24
                verts.append((screen.x + math.cos(angle) * radius,
                              screen.y + math.sin(angle) * radius, 0))
            faces = [(0, n, n + 1) for n in range(1, 25)]
            flat = [verts[i] for tri in faces for i in tri]
            batch = batch_for_shader(shader, 'TRIS', {"pos": flat})
            shader.bind()
            shader.uniform_float('color', (.99, .67, .22, 1) if index == 2 else (.15, .65, .99, 1))
            batch.draw(shader)

    def invoke(self, context, event):
        self._wall = context.active_object
        if self._wall is None or self._wall.get("archyar_kind") != "WALL":
            self.report({'WARNING'}, "Select an Archyar wall first")
            return {'CANCELLED'}
        self._baseline = [(obj, tuple(obj.archyar_wall.start), tuple(obj.archyar_wall.end))
                          for obj in bpy.data.objects if obj.get("archyar_kind") == "WALL"]
        self._drag = -1
        self._handler = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Drag blue endpoints or orange centre; Enter finish / Esc cancel")
        return {'RUNNING_MODAL'}

    def _close(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'RET', 'NUMPAD_ENTER', 'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                for obj, start, end in self._baseline:
                    obj.archyar_wall.start, obj.archyar_wall.end = start, end
            self._close(context)
            return {'CANCELLED'} if event.type in {'ESC', 'RIGHTMOUSE'} else {'FINISHED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = _window_region(context)
            if region is None:
                return {'PASS_THROUGH'}
            click = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
            for i, screen in enumerate(self._handle_points(context)):
                if screen is not None and (click - screen).length < 19:
                    self._drag = i
                    self._cursor_start = ground_point(context, event,
                                                     self._wall.archyar_wall.elevation)
                    return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self._drag >= 0:
                self._drag = -1
                return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE' and self._drag >= 0:
            point = ground_point(context, event, self._wall.archyar_wall.elevation)
            if point is None or self._cursor_start is None:
                return {'RUNNING_MODAL'}
            start = next((Vector(a) for obj, a, _ in self._baseline if obj == self._wall), None)
            end = next((Vector(b) for obj, _, b in self._baseline if obj == self._wall), None)
            if start is None or end is None:
                return {'CANCELLED'}
            ignored = {self._wall.name}
            value = Vector(snap_point(point, context.scene, excluded=ignored))
            if self._drag == 0:
                start = value
            elif self._drag == 1:
                end = value
            else:
                shift = value - Vector((self._cursor_start.x, self._cursor_start.y))
                start += shift
                end += shift
            try:
                # Validate each move against the original connected graph.
                for obj, a, b in self._baseline:
                    obj.archyar_wall.start, obj.archyar_wall.end = a, b
                apply_wall_connection_changes(wall_connection_changes(self._wall, start, end))
            except ValueError:
                pass
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


class _ViewportPlacement:
    _start = None
    _current = None
    _handler = None
    _created = 0
    _ghost = None

    def _init_modal(self, context, message, tool_label):
        global _ACTIVE_PLACEMENT
        _metres_ok(context)
        if _window_region(context) is None:
            raise ValueError("3D Viewport window region was not found")
        if _ACTIVE_PLACEMENT is not None and _ACTIVE_PLACEMENT is not self:
            _ACTIVE_PLACEMENT._cleanup(context)
        self._start, self._current, self._created, self._ghost = None, None, 0, None
        self._stopped = False
        _ACTIVE_PLACEMENT = self
        context.scene.archyar_active_tool = tool_label
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_preview, (), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(message)
        return {'RUNNING_MODAL'}

    def _cleanup(self, context):
        global _ACTIVE_PLACEMENT
        if self._stopped:
            return
        self._stopped = True
        if self._ghost is not None:
            geometry.remove_tree(self._ghost)
            self._ghost = None
        if self._handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            self._handler = None
        context.workspace.status_text_set(None)
        if _ACTIVE_PLACEMENT is self:
            _ACTIVE_PLACEMENT = None
            context.scene.archyar_active_tool = ""
        context.area.tag_redraw()

    def _draw_preview(self):
        if self._start is None or self._current is None:
            return
        thickness = bpy.context.scene.archyar_thickness
        height = bpy.context.scene.archyar_height
        dx = self._current[0] - self._start[0]
        dy = self._current[1] - self._start[1]
        span = math.hypot(dx, dy)
        if span < 1e-4:
            return
        nx, ny = -dy * thickness / (2 * span), dx * thickness / (2 * span)
        a, b = self._start, self._current
        level = bpy.context.scene.archyar_level_elevation
        bottom = [(a[0]+nx,a[1]+ny,level),(b[0]+nx,b[1]+ny,level),
                  (b[0]-nx,b[1]-ny,level),(a[0]-nx,a[1]-ny,level)]
        top = [(x,y,height+level) for x,y,_ in bottom]
        edges = []
        for k in range(4):
            j = (k+1)%4
            edges.extend((bottom[k],bottom[j],top[k],top[j],bottom[k],top[k]))
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINES', {"pos": edges})
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
            return self._init_modal(context, "Archyar wall: left-click start/end, Enter to finish, Esc to cancel", "Wall")
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if self._stopped:
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._cleanup(context)
            return {'FINISHED'} if self._created else {'CANCELLED'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'PASS_THROUGH'}
        value = snap_point(point, context.scene)
        if event.ctrl and not context.scene.archyar_snap_grid:
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
                        context.scene.archyar_wall_preset,
                        context.scene.archyar_level_elevation)
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

    def _dimensions(self, context):
        width = context.scene.archyar_open_width
        height = context.scene.archyar_open_height
        # Mobile's standard door is 0.90 × 2.10 m; only substitute when the
        # untouched 1.20 × 1.40 m default for windows is still selected.
        if self.style in ('door', 'sliding-door') and abs(width-1.2)<1e-6 and abs(height-1.4)<1e-6:
            return .9, 2.1
        return width, height

    def invoke(self, context, event):
        self._wall = context.active_object if context.active_object and context.active_object.get("archyar_kind") == "WALL" else None
        try:
            return self._init_modal(context, "Archyar opening: click repeatedly on walls; Esc to finish", OPENINGS[self.style])
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if self._stopped:
            return {'CANCELLED'}
        if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and event.value == 'PRESS'):
            self._cleanup(context)
            return {'FINISHED'} if self._created else {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'PASS_THROUGH'}
        wall = self._wall or nearest_wall(point, elevation=context.scene.archyar_level_elevation)
        if wall is None:
            if self._ghost is not None:
                geometry.remove_tree(self._ghost)
                self._ghost = None
            if event.type == 'LEFTMOUSE':
                self.report({'WARNING'}, "Select a wall or click within 65 cm of one")
            return {'RUNNING_MODAL'}
        width, height = self._dimensions(context)
        sill = 0 if self.style in ('door', 'sliding-door') else context.scene.archyar_sill
        if self._ghost is not None and self._ghost.parent != wall:
            geometry.remove_tree(self._ghost)
            self._ghost = None
        if self._ghost is None:
            self._ghost = geometry.preview_opening(wall, self.style, width, height, sill)
        fraction = wall_fraction(wall, point)
        span = geometry.length(wall.archyar_wall.start, wall.archyar_wall.end)
        if span >= width + .20:
            margin = (width/2+.10)/span
            fraction = max(margin, min(1-margin, fraction))
        self._ghost['archyar_t'] = fraction
        geometry.reposition_opening(self._ghost, wall)
        context.area.tag_redraw()
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        try:
            root = geometry.create_opening(wall, wall_fraction(wall, point), self.style,
                                           width, height, sill)
            load_opening_settings(root)
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'RUNNING_MODAL'}
        geometry.remove_tree(self._ghost)
        self._ghost = None
        self._created += 1
        return {'RUNNING_MODAL'}


class ARCHYAR_OT_place_furniture(_ViewportPlacement, bpy.types.Operator):
    bl_idname = "archyar.place_furniture"
    bl_label = "Place Archyar Furniture"
    bl_description = "Choose an item and click on the floor; paintings attach to a wall"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty(min=0, max=21)

    def invoke(self, context, event):
        self._wall = context.active_object if context.active_object and context.active_object.get("archyar_kind") == "WALL" else None
        try:
            return self._init_modal(context, "Archyar furniture: click repeatedly to place; Esc to finish", furniture(self.index).name)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if self._stopped:
            return {'CANCELLED'}
        if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and event.value == 'PRESS'):
            self._cleanup(context)
            return {'FINISHED'} if self._created else {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'PASS_THROUGH'}
        asset = furniture(self.index)
        if asset.wall_mounted:
            wall = self._wall or nearest_wall(point, elevation=context.scene.archyar_level_elevation)
            if wall is None:
                if event.type == 'LEFTMOUSE':
                    self.report({'WARNING'}, "Choose a wall for wall-mounted artwork")
                return {'RUNNING_MODAL'}
            t = wall_fraction(wall, point)
            if self._ghost is not None and self._ghost.parent != wall:
                geometry.remove_tree(self._ghost)
                self._ghost = None
            if self._ghost is None:
                self._ghost = make_furniture(self.index, parent=wall, preview=True)
            root = self._ghost
            span = geometry.length(wall.archyar_wall.start, wall.archyar_wall.end)
            root.location = ((t-.5)*span, wall.archyar_wall.thickness/2+asset.depth/2+.035,
                             1.25-wall.archyar_wall.height/2)
            root["archyar_host_id"] = wall["archyar_id"]
            root["archyar_host_t"] = t
        else:
            if self._ghost is None:
                self._ghost = make_furniture(self.index, preview=True)
            root = self._ghost
            root.location = (point.x, point.y, context.scene.archyar_level_elevation)
        context.area.tag_redraw()
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        geometry.mark_preview(root, False)
        self._ghost = None
        geometry.select(root)
        self._created += 1
        return {'RUNNING_MODAL'}


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
            return self._init_modal(context, "Archyar structure: click repeatedly to place; Esc to finish", BUILD_PARTS[self.kind])
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if self._stopped:
            return {'CANCELLED'}
        if event.type == 'ESC' or (event.type == 'RIGHTMOUSE' and event.value == 'PRESS'):
            self._cleanup(context)
            return {'FINISHED'} if self._created else {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        point = ground_point(context, event)
        if point is None:
            return {'PASS_THROUGH'}
        if self._ghost is None:
            self._ghost = geometry.add_structure(self.kind,
                (point.x, point.y, context.scene.archyar_level_elevation), preview=True)
            if self.kind == 'stairs':
                stair = self._ghost.archyar_stair
                scene = context.scene
                stair.run = scene.archyar_stair_run
                stair.width = scene.archyar_stair_width
                stair.rise = scene.archyar_stair_rise
                stair.count = scene.archyar_stair_count
                stair.filled = scene.archyar_stair_filled
        root = self._ghost
        root.location = (point.x, point.y, context.scene.archyar_level_elevation)
        context.area.tag_redraw()
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if self.kind == 'stairs':
            stair = root.archyar_stair
            try:
                require_stair(stair.run, stair.width, stair.rise, stair.count)
            except ValueError as exc:
                self.report({'ERROR'}, str(exc))
                return {'RUNNING_MODAL'}
        geometry.mark_preview(root, False)
        self._ghost = None
        geometry.select(root)
        self._created += 1
        return {'RUNNING_MODAL'}


class VIEW3D_PT_archyar(bpy.types.Panel):
    bl_label = "Archyar"
    bl_idname = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Archyar"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        if scene.archyar_active_tool:
            layout.label(text="ACTIVE: " + scene.archyar_active_tool, icon='RADIOBUT_ON')
            layout.label(text="Click to place more; Esc ends tool")
        if abs(scene.unit_settings.scale_length - 1) > 1e-6:
            layout.label(text="Set scene unit scale to 1.0", icon='ERROR')
        layout.prop(scene, "archyar_section", expand=True)
        if scene.archyar_section == 'BUILD':
            layout.prop(scene, "archyar_level_elevation")
            grid_box = layout.box()
            grid_box.label(text="Construction Grid")
            grid_box.prop(scene, "archyar_show_grid", text="Show Grid")
            grid_box.prop(scene, "archyar_snap_grid", text="Snap to Grid")
            grid_box.prop(scene, "archyar_snap_points", text="Snap to Wall Endpoints")
            grid_box.prop(scene, "archyar_grid_step", text="Grid Interval")
            layout.prop(scene, "archyar_wall_preset", text="Wall Type")
            layout.prop(scene, "archyar_thickness")
            layout.prop(scene, "archyar_height")
            layout.operator("archyar.draw_wall", text="Draw Wall (click points)", icon='MESH_CUBE')
            layout.label(text="Walls snap to the active level grid")
            stairs_box = layout.box()
            stairs_box.label(text="Parametric Stairs")
            for field in ('archyar_stair_run', 'archyar_stair_width', 'archyar_stair_rise',
                          'archyar_stair_count', 'archyar_stair_filled'):
                stairs_box.prop(scene, field)
            stairs_tool = stairs_box.operator("archyar.place_structure", text="Preview & Place Stairs", icon='MOD_ARRAY')
            stairs_tool.kind = 'stairs'
            box_ui = layout.box()
            box_ui.label(text="Other architectural elements")
            for key, name in BUILD_PARTS.items():
                if key == 'stairs':
                    continue
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
    bl_label = "Selected Archyar Element"
    bl_idname = "VIEW3D_PT_archyar_edit"
    bl_parent_id = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None:
            layout.label(text="Select an Archyar element")
            return
        if obj.get("archyar_kind") == "WALL":
            props = obj.archyar_wall
            for field in ("start", "end", "thickness", "height", "elevation", "show_length"):
                layout.prop(props, field)
            layout.label(text="Length: %.3f m" % geometry.length(props.start, props.end))
            layout.operator("archyar.set_wall_length", text="Set Exact Length")
            layout.operator("archyar.edit_wall_handles", text="Drag Wall Handles")
        elif obj.get("archyar_kind") == "STAIRS":
            props = obj.archyar_stair
            for field in ('run', 'width', 'rise', 'count', 'filled'):
                layout.prop(props, field)
            if props.count:
                layout.label(text="Riser: %.3f m | Tread: %.3f m" %
                             (props.rise / props.count, props.run / props.count))
                if props.rise / props.count < .10 or props.rise / props.count > .22 or props.run / props.count < .20:
                    layout.label(text="Invalid stair dimensions", icon='ERROR')
        elif obj.get("archyar_kind") == "OPENING":
            layout.operator('archyar.load_opening', text="Load Selected Values", icon='FILE_REFRESH')
            props = obj.archyar_opening
            for field in ('style', 'width', 'height', 'sill', 'offset'):
                layout.prop(props, field)
            if props.style == 'arched':
                layout.prop(props, 'arch_rise')
            if props.style in ('door', 'sliding-door', 'hinged', 'sliding'):
                layout.prop(props, 'mirrored')
                layout.prop(props, 'open_fraction')
            layout.operator('archyar.edit_opening', icon='CHECKMARK')
        else:
            layout.label(text="Select a wall, stair, door or window")


CLASSES = (ArchyarWallSettings, ArchyarStairSettings, ArchyarOpeningSettings,
           ARCHYAR_OT_edit_opening, ARCHYAR_OT_load_opening,
           ARCHYAR_OT_set_wall_length, ARCHYAR_OT_edit_wall_handles, ARCHYAR_OT_draw_wall,
           ARCHYAR_OT_place_opening, ARCHYAR_OT_place_furniture,
           ARCHYAR_OT_place_structure, VIEW3D_PT_archyar, VIEW3D_PT_archyar_edit)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.archyar_wall = PointerProperty(type=ArchyarWallSettings)
    bpy.types.Object.archyar_stair = PointerProperty(type=ArchyarStairSettings)
    bpy.types.Object.archyar_opening = PointerProperty(type=ArchyarOpeningSettings)
    bpy.types.Scene.archyar_section = EnumProperty(name="Group", items=[
        ('BUILD', "Build", "Walls and architectural parts"),
        ('OPEN', "Openings", "Doors and windows"),
        ('FURN', "Furniture", "Chido catalog"),
        ('MEP', "Services", "Reserved for a future phase")])
    bpy.types.Scene.archyar_wall_preset = EnumProperty(name="Wall Type", items=[
        (key, label, label) for key, (label, _) in WALL_PRESETS.items()], update=_preset_change)
    bpy.types.Scene.archyar_thickness = FloatProperty(name="Wall Thickness", default=.15, min=.04, max=1, unit='LENGTH')
    bpy.types.Scene.archyar_active_tool = StringProperty(name="Active Archyar Tool", default="")
    bpy.types.Scene.archyar_level_elevation = FloatProperty(name="Active Level (Z)", default=0, min=-100, max=100, unit='LENGTH')
    bpy.types.Scene.archyar_show_grid = BoolProperty(name="Show Grid", default=True)
    bpy.types.Scene.archyar_snap_grid = BoolProperty(name="Snap to Grid", default=True)
    bpy.types.Scene.archyar_snap_points = BoolProperty(name="Snap to Wall Endpoints", default=True)
    bpy.types.Scene.archyar_grid_step = FloatProperty(name="Grid Interval", default=.10, min=.05, max=1.0, unit='LENGTH')
    bpy.types.Scene.archyar_height = FloatProperty(name="Wall Height", default=3.0, min=.3, max=12, unit='LENGTH')
    bpy.types.Scene.archyar_open_width = FloatProperty(name="Width", default=1.2, min=.3, max=6, unit='LENGTH')
    bpy.types.Scene.archyar_open_height = FloatProperty(name="Height", default=1.4, min=.3, max=6, unit='LENGTH')
    bpy.types.Scene.archyar_sill = FloatProperty(name="Sill Height", default=.9, min=0, max=6, unit='LENGTH')
    bpy.types.Scene.archyar_stair_run = FloatProperty(name="Total Run", default=3.0, min=.5, unit='LENGTH')
    bpy.types.Scene.archyar_stair_width = FloatProperty(name="Stair Width", default=1.1, min=.5, max=5, unit='LENGTH')
    bpy.types.Scene.archyar_stair_rise = FloatProperty(name="Total Rise", default=1.8, min=.15, max=9, unit='LENGTH')
    bpy.types.Scene.archyar_stair_count = IntProperty(name="Step Count", default=10, min=1, max=50)
    bpy.types.Scene.archyar_stair_filled = BoolProperty(name="Filled Underside", default=False)
    bpy.types.Scene.archyar_furn_category = EnumProperty(name="Furniture Category", items=[
        (key, label, label) for key, label in CATEGORY_NAMES.items()])


def unregister():
    for name in ("archyar_stair_filled", "archyar_stair_count", "archyar_stair_rise",
                 "archyar_stair_width", "archyar_stair_run", "archyar_furn_category", "archyar_sill", "archyar_open_height",
                  "archyar_open_width", "archyar_height", "archyar_thickness", "archyar_active_tool",
                  "archyar_level_elevation", "archyar_show_grid", "archyar_snap_grid",
                  "archyar_snap_points", "archyar_grid_step",
                 "archyar_wall_preset", "archyar_section"):
        delattr(bpy.types.Scene, name)
    del bpy.types.Object.archyar_wall
    del bpy.types.Object.archyar_stair
    del bpy.types.Object.archyar_opening
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

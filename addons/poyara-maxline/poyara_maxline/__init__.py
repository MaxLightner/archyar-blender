"""POYARA MaxLine: Max-inspired spline/mesh command panels for Blender."""

bl_info = {
    "name": "POYARA MaxLine | Edit Spline + Edit Poly",
    "author": "POYARA",
    "version": (0, 1, 0),
    "blender": (4, 3, 0),
    "location": "3D View > Sidebar (N) > POYARA",
    "description": "3ds Max-like Edit Spline and Edit Poly panels with interactive line editing",
    "category": "3D View",
}

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector, geometry
from bpy_extras import view3d_utils

from .topology import break_vertices, delete_segments, dissolve_vertices


def _is_curve(obj):
    return obj is not None and obj.type == 'CURVE'


def _supported_curve(obj):
    return _is_curve(obj) and all(s.type in {'BEZIER', 'POLY'} for s in obj.data.splines)


def _knots(spline):
    return spline.bezier_points if spline.type == 'BEZIER' else spline.points


def _xyz(point, spline):
    return point.co.copy().to_3d() if spline.type == 'POLY' else point.co.copy()


def _read_point(point, kind):
    result = {
        'co': tuple(point.co),
        'radius': point.radius,
        'tilt': point.tilt,
    }
    if kind == 'BEZIER':
        result.update({
            'left': tuple(point.handle_left),
            'right': tuple(point.handle_right),
            'left_type': point.handle_left_type,
            'right_type': point.handle_right_type,
        })
    else:
        result['weight'] = point.weight_softbody
    return result


def _serialize_curve(curve):
    specs = []
    for spline in curve.splines:
        if spline.type not in {'BEZIER', 'POLY'}:
            raise TypeError('MaxLine editing supports Bezier and Poly splines only')
        specs.append({
            'type': spline.type,
            'cyclic': bool(spline.use_cyclic_u),
            'material': spline.material_index,
            'resolution': spline.resolution_u,
            'points': [_read_point(p, spline.type) for p in _knots(spline)],
        })
    return specs


def _rebuild_curve(curve, specs):
    curve.splines.clear()
    for spec in specs:
        if len(spec['points']) < 2:
            continue
        spline = curve.splines.new(spec['type'])
        knots = _knots(spline)
        knots.add(len(spec['points']) - 1)
        for point, values in zip(knots, spec['points']):
            point.co = values['co']
            point.radius = values.get('radius', 1.0)
            point.tilt = values.get('tilt', 0.0)
            if spec['type'] == 'BEZIER':
                # Set explicit handles first; then restore their handle types.
                point.handle_left_type = 'FREE'
                point.handle_right_type = 'FREE'
                point.handle_left = values['left']
                point.handle_right = values['right']
                point.handle_left_type = values.get('left_type', 'VECTOR')
                point.handle_right_type = values.get('right_type', 'VECTOR')
            else:
                point.weight_softbody = values.get('weight', 0.0)
        spline.use_cyclic_u = spec['cyclic']
        spline.material_index = spec.get('material', 0)
        spline.resolution_u = spec.get('resolution', 12)
    curve.update_tag()


def _project(context, world):
    return view3d_utils.location_3d_to_region_2d(
        context.region, context.space_data.region_3d, world
    )


def _world_from_mouse(context, x, y, plane_point, normal):
    coords = (x, y)
    region = context.region
    rv3d = context.space_data.region_3d
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coords)
    ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, coords)
    return geometry.intersect_line_plane(origin, origin + ray, plane_point, normal, False)


def _view_normal(context):
    return (context.space_data.region_3d.view_rotation @ Vector((0, 0, 1))).normalized()


def _screen_distance(point, a, b):
    ab = b - a
    length_sq = ab.length_squared
    t = max(0.0, min(1.0, (point - a).dot(ab) / length_sq)) if length_sq else 0.0
    return (point - (a + t * ab)).length


def _segment_world_points(obj, spline, index, steps=12):
    knots = _knots(spline)
    j = (index + 1) % len(knots)
    if spline.type == 'BEZIER':
        a, b = knots[index], knots[j]
        samples = geometry.interpolate_bezier(
            a.co, a.handle_right, b.handle_left, b.co, steps
        )
        return [obj.matrix_world @ item for item in samples]
    return [obj.matrix_world @ _xyz(knots[index], spline), obj.matrix_world @ _xyz(knots[j], spline)]


def _edges_in_spline(spline):
    count = len(_knots(spline))
    return range(count if spline.use_cyclic_u else max(0, count - 1))


def _draw_overlay(operator, context, preview=None):
    """Draw the point/segment selection overlay inside the original viewport."""
    try:
        import gpu
        from gpu_extras.batch import batch_for_shader

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')

        def colored(primitive, vertices, rgba, width=1.0, size=6):
            if not vertices:
                return
            gpu.state.line_width_set(width)
            gpu.state.point_size_set(size)
            shader.bind()
            shader.uniform_float('color', rgba)
            batch_for_shader(shader, primitive, {'pos': vertices}).draw(shader)

        if operator._draw_mode:
            points = [_project(context, p) for p in operator._points]
            points = [p for p in points if p is not None]
            edges = []
            for i in range(len(points) - 1):
                edges.extend((points[i], points[i + 1]))
            if operator._hover is not None and points:
                end = _project(context, operator._hover)
                if end is not None:
                    edges.extend((points[-1], end))
            if operator._close_preview and len(points) >= 3:
                edges.extend((points[-1], points[0]))
            colored('LINES', edges, (0.2, 0.72, 1, 1), width=2.0)
            colored('POINTS', points, (1, 0.68, 0.16, 1), size=8)
        else:
            obj = operator._obj
            for si, spline in enumerate(obj.data.splines):
                for edge in _edges_in_spline(spline):
                    sampled = [_project(context, p) for p in _segment_world_points(obj, spline, edge)]
                    verts = []
                    for a, b in zip(sampled, sampled[1:]):
                        if a is not None and b is not None:
                            verts.extend((a, b))
                    active = (si, edge) in operator._selected_segments or si in operator._selected_splines
                    colored('LINES', verts, (1, 0.59, 0.15, 1) if active else (0.2, 0.7, 0.95, 0.86),
                            width=3.0 if active else 2.0)
                base, selected = [], []
                for vi, knot in enumerate(_knots(spline)):
                    screen = _project(context, obj.matrix_world @ _xyz(knot, spline))
                    if screen is None:
                        continue
                    (selected if (si, vi) in operator._selected_vertices else base).append(screen)
                colored('POINTS', base, (0.85, 0.89, 0.98, 1), size=7)
                colored('POINTS', selected, (1, 0.52, 0.12, 1), size=10)
        gpu.state.blend_set('NONE')
    except (ReferenceError, RuntimeError, ValueError):
        # Viewport may be closed during an active modal session.
        pass


class POYARA_PG_settings(PropertyGroup):
    tab: EnumProperty(
        name='Mode',
        items=[('EDIT_POLY', 'Edit Poly', 'Mesh tools'),
               ('EDIT_SPLINE', 'Edit Line', 'Spline tools'),
               ('EXTRAS', 'Extras', 'Creation and object tools')],
        default='EDIT_SPLINE',
    )
    selection_mode: EnumProperty(
        name='Sub-Object',
        items=[('VERTEX', 'Vertex', 'Pick spline knots'),
               ('SEGMENT', 'Segment', 'Pick spline segments'),
               ('SPLINE', 'Spline', 'Pick full spline paths')],
        default='VERTEX',
    )
    snap_step: FloatProperty(name='Ctrl Snap (m)', default=0.01, min=0.001, max=10.0, precision=3)


class POYARA_OT_draw_line(Operator):
    bl_idname = 'poyara.draw_line'
    bl_label = 'Create Line (Max-style)'
    bl_description = 'Click to add knots; Backspace undo last; C close; Right Click or Enter finish'
    bl_options = {'REGISTER', 'UNDO'}

    _draw_mode = True
    _close_preview = False

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        obj = context.active_object
        if obj is not None and obj.type == 'CURVE' and not _supported_curve(obj):
            self.report({'ERROR'}, 'Convert NURBS splines before using MaxLine')
            return {'CANCELLED'}
        self._obj = obj if _is_curve(obj) else None
        self._points = []
        self._hover = None
        self._normal = _view_normal(context)
        self._plane = context.scene.cursor.location.copy()
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (self, context), 'WINDOW', 'POST_PIXEL'
        )
        context.workspace.status_text_set('MAX LINE: Left Click add | Backspace undo | C close | Enter/Right Click finish | Esc cancel')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context, save, closed=False):
        bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        if not save or len(self._points) < 2:
            return {'CANCELLED'}
        if closed and len(self._points) < 3:
            closed = False
        obj = self._obj
        if obj is None:
            curve = bpy.data.curves.new('MaxLine', 'CURVE')
            curve.dimensions = '3D'
            curve.resolution_u = 16
            obj = bpy.data.objects.new('MaxLine', curve)
            context.collection.objects.link(obj)
            obj.location = self._plane
        curve = obj.data
        curve.dimensions = '3D'
        spline = curve.splines.new('BEZIER')
        spline.bezier_points.add(len(self._points) - 1)
        inverse = obj.matrix_world.inverted_safe()
        for point, world in zip(spline.bezier_points, self._points):
            point.co = inverse @ world
            point.handle_left_type = 'VECTOR'
            point.handle_right_type = 'VECTOR'
        spline.use_cyclic_u = closed
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        curve.update_tag()
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            self._hover = _world_from_mouse(context, event.mouse_region_x, event.mouse_region_y,
                                            self._plane, self._normal)
            if event.ctrl and self._hover is not None:
                step = context.scene.poyara_maxline.snap_step
                self._hover = Vector(tuple(round(v / step) * step for v in self._hover))
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type == 'LEFTMOUSE':
            world = _world_from_mouse(context, event.mouse_region_x, event.mouse_region_y,
                                      self._plane, self._normal)
            if world is not None:
                if event.ctrl:
                    step = context.scene.poyara_maxline.snap_step
                    world = Vector(tuple(round(v / step) * step for v in world))
                self._points.append(world.copy())
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type == 'BACK_SPACE':
            if self._points:
                self._points.pop()
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type == 'C':
            return self._finish(context, True, closed=True)
        if event.value == 'PRESS' and event.type in {'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE'}:
            return self._finish(context, True)
        if event.value == 'PRESS' and event.type == 'ESC':
            return self._finish(context, False)
        return {'PASS_THROUGH'}


class POYARA_OT_edit_spline(Operator):
    bl_idname = 'poyara.edit_spline'
    bl_label = 'Edit Spline (Max-style)'
    bl_description = 'Edit knots, edges and full splines by selection level, like 3ds Max'
    bl_options = {'REGISTER', 'UNDO'}

    _draw_mode = False

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and _supported_curve(context.active_object)

    def invoke(self, context, event):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        self._obj = context.active_object
        self._before = _serialize_curve(self._obj.data)
        self._selected_vertices = set()
        self._selected_segments = set()
        self._selected_splines = set()
        self._dragging = False
        self._drag_base = None
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (self, context), 'WINDOW', 'POST_PIXEL'
        )
        self._set_status(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _set_status(self, context):
        mode = context.scene.poyara_maxline.selection_mode
        context.workspace.status_text_set(
            f'MAX EDIT ({mode}): 1/2/3 select level | Drag move | X delete + break | Shift+X dissolve | '
            'S smooth / H corner | Enter/Right Click save | Esc cancel'
        )

    def _hit(self, context, event):
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        mode = context.scene.poyara_maxline.selection_mode
        obj = self._obj
        best = None
        distance = 12.0
        for si, spline in enumerate(obj.data.splines):
            if mode == 'VERTEX':
                for vi, p in enumerate(_knots(spline)):
                    xy = _project(context, obj.matrix_world @ _xyz(p, spline))
                    if xy is not None and (xy - mouse).length < distance:
                        best, distance = (si, vi), (xy - mouse).length
            else:
                for ei in _edges_in_spline(spline):
                    coords = [_project(context, p) for p in _segment_world_points(obj, spline, ei)]
                    for a, b in zip(coords, coords[1:]):
                        if a is None or b is None:
                            continue
                        d = _screen_distance(mouse, a, b)
                        if d < distance:
                            best, distance = ((si, ei) if mode == 'SEGMENT' else si), d
        return best

    def _selection(self, context):
        mode = context.scene.poyara_maxline.selection_mode
        if mode == 'VERTEX':
            return self._selected_vertices
        if mode == 'SEGMENT':
            return self._selected_segments
        return self._selected_splines

    def _affected_knots(self, context):
        mode = context.scene.poyara_maxline.selection_mode
        obj = self._obj
        if mode == 'VERTEX':
            return set(self._selected_vertices)
        if mode == 'SEGMENT':
            return {(si, vi) for si, edge in self._selected_segments
                    for vi in (edge, (edge + 1) % len(_knots(obj.data.splines[si])))}
        return {(si, vi) for si in self._selected_splines
                for vi in range(len(_knots(obj.data.splines[si])))}

    def _start_drag(self, context, event):
        affected = self._affected_knots(context)
        if not affected:
            return
        positions = []
        self._drag_base = {}
        for si, vi in affected:
            spline = self._obj.data.splines[si]
            knot = _knots(spline)[vi]
            spec = _read_point(knot, spline.type)
            self._drag_base[(si, vi)] = spec
            positions.append(self._obj.matrix_world @ _xyz(knot, spline))
        self._drag_plane = sum(positions, Vector()) / len(positions)
        self._drag_normal = _view_normal(context)
        self._drag_start = _world_from_mouse(context, event.mouse_region_x, event.mouse_region_y,
                                             self._drag_plane, self._drag_normal)
        self._dragging = self._drag_start is not None

    def _move(self, context, event):
        if not self._dragging:
            return
        here = _world_from_mouse(context, event.mouse_region_x, event.mouse_region_y,
                                 self._drag_plane, self._drag_normal)
        if here is None:
            return
        delta = here - self._drag_start
        delta = self._obj.matrix_world.inverted_safe().to_3x3() @ delta
        for (si, vi), base in self._drag_base.items():
            spline = self._obj.data.splines[si]
            knot = _knots(spline)[vi]
            if spline.type == 'BEZIER':
                knot.co = Vector(base['co']) + delta
                if base['left_type'] in {'FREE', 'ALIGNED'}:
                    knot.handle_left = Vector(base['left']) + delta
                if base['right_type'] in {'FREE', 'ALIGNED'}:
                    knot.handle_right = Vector(base['right']) + delta
            else:
                pos = Vector(base['co'])
                knot.co = (pos.xyz + delta).to_4d()
                knot.co.w = pos.w
        self._obj.data.update_tag()
        context.area.tag_redraw()

    def _delete(self, context, dissolve=False):
        mode = context.scene.poyara_maxline.selection_mode
        specs = _serialize_curve(self._obj.data)
        updated = []
        for si, spec in enumerate(specs):
            points = spec['points']
            if mode == 'SPLINE':
                chunks = [] if si in self._selected_splines else [(points, spec['cyclic'])]
            elif mode == 'SEGMENT':
                ids = [edge for s, edge in self._selected_segments if s == si]
                chunks = delete_segments(points, ids, spec['cyclic'])
            else:
                ids = [vertex for s, vertex in self._selected_vertices if s == si]
                fn = dissolve_vertices if dissolve else break_vertices
                chunks = fn(points, ids, spec['cyclic'])
            for chunk, cyclic in chunks:
                updated.append({**spec, 'points': chunk, 'cyclic': cyclic})
        _rebuild_curve(self._obj.data, updated)
        self._selected_vertices.clear()
        self._selected_segments.clear()
        self._selected_splines.clear()
        if 'poyara_last_vertex' in self._obj:
            del self._obj['poyara_last_vertex']
        context.area.tag_redraw()

    def _set_handle_type(self, context, kind):
        if context.scene.poyara_maxline.selection_mode != 'VERTEX':
            return
        for si, vi in self._selected_vertices:
            sp = self._obj.data.splines[si]
            if sp.type == 'BEZIER':
                knot = sp.bezier_points[vi]
                knot.handle_left_type = kind
                knot.handle_right_type = kind
        self._obj.data.update_tag()
        context.area.tag_redraw()

    def _finish(self, context, commit):
        self._dragging = False
        bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
        context.workspace.status_text_set(None)
        if not commit:
            _rebuild_curve(self._obj.data, self._before)
        context.area.tag_redraw()
        return {'FINISHED'} if commit else {'CANCELLED'}

    def modal(self, context, event):
        if not self._obj or self._obj.name not in bpy.data.objects:
            return self._finish(context, False)
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            self._move(context, event)
            return {'RUNNING_MODAL'} if self._dragging else {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            hit = self._hit(context, event)
            selected = self._selection(context)
            if not event.shift:
                selected.clear()
            if hit is not None:
                if event.shift and hit in selected:
                    selected.remove(hit)
                else:
                    selected.add(hit)
                if context.scene.poyara_maxline.selection_mode == 'VERTEX':
                    self._obj['poyara_last_vertex'] = f'{hit[0]}:{hit[1]}'
                self._start_drag(context, event)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._dragging = False
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS':
            mode_map = {'ONE': 'VERTEX', 'TWO': 'SEGMENT', 'THREE': 'SPLINE'}
            if event.type in mode_map:
                context.scene.poyara_maxline.selection_mode = mode_map[event.type]
                self._dragging = False
                self._set_status(context)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type in {'X', 'DEL'}:
                self._delete(context, dissolve=event.shift)
                return {'RUNNING_MODAL'}
            if event.type == 'S':
                self._set_handle_type(context, 'AUTO')
                return {'RUNNING_MODAL'}
            if event.type == 'H':
                self._set_handle_type(context, 'VECTOR')
                return {'RUNNING_MODAL'}
            if event.type in {'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE'}:
                return self._finish(context, True)
            if event.type == 'ESC':
                return self._finish(context, False)
        return {'PASS_THROUGH'}


class POYARA_OT_set_vertex_xyz(Operator):
    bl_idname = 'poyara.set_vertex_xyz'
    bl_label = 'Vertex Coordinates'
    bl_description = 'Set world-space XYZ of last picked spline vertex'
    bl_options = {'REGISTER', 'UNDO'}

    x: FloatProperty(name='X', unit='LENGTH')
    y: FloatProperty(name='Y', unit='LENGTH')
    z: FloatProperty(name='Z', unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return _supported_curve(context.active_object) and 'poyara_last_vertex' in context.active_object

    def _lookup(self, context):
        obj = context.active_object
        si, vi = (int(v) for v in obj['poyara_last_vertex'].split(':'))
        return obj, obj.data.splines[si], vi

    def invoke(self, context, event):
        try:
            obj, spline, vi = self._lookup(context)
            world = obj.matrix_world @ _xyz(_knots(spline)[vi], spline)
        except (ValueError, IndexError, KeyError):
            self.report({'ERROR'}, 'Pick a vertex again in Edit Spline')
            return {'CANCELLED'}
        self.x, self.y, self.z = world
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        try:
            obj, spline, vi = self._lookup(context)
            point = _knots(spline)[vi]
            target = obj.matrix_world.inverted_safe() @ Vector((self.x, self.y, self.z))
            delta = target - _xyz(point, spline)
            if spline.type == 'BEZIER':
                if point.handle_left_type in {'FREE', 'ALIGNED'}:
                    point.handle_left += delta
                if point.handle_right_type in {'FREE', 'ALIGNED'}:
                    point.handle_right += delta
                point.co = target
            else:
                old_w = point.co.w
                point.co = (target.x, target.y, target.z, old_w)
            obj.data.update_tag()
            return {'FINISHED'}
        except (ValueError, IndexError, KeyError):
            self.report({'ERROR'}, 'The picked vertex no longer exists; select it again')
            return {'CANCELLED'}


class POYARA_OT_mesh_level(Operator):
    bl_idname = 'poyara.mesh_level'
    bl_label = 'Sub-Object Level'
    bl_description = 'Switch to Blender native vertex/edge/face selection'
    bl_options = {'REGISTER'}

    level: EnumProperty(items=[('VERT', 'Vertex', ''), ('EDGE', 'Edge', ''),
                               ('BORDER', 'Border', ''), ('FACE', 'Polygon', ''),
                               ('ELEMENT', 'Element', '')])

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
        kind = {'VERT': 'VERT', 'EDGE': 'EDGE', 'BORDER': 'EDGE',
                'FACE': 'FACE', 'ELEMENT': 'FACE'}[self.level]
        bpy.ops.mesh.select_mode(type=kind)
        if self.level == 'BORDER':
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.mesh.select_non_manifold(extend=False, use_wire=False, use_boundary=True,
                                            use_multi_face=False, use_non_contiguous=False,
                                            use_verts=False)
        elif self.level == 'ELEMENT':
            bpy.ops.mesh.select_linked()
        return {'FINISHED'}


class POYARA_OT_mode_toggle(Operator):
    bl_idname = 'poyara.toggle_edit'
    bl_label = 'Toggle Edit Mode'
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type not in {'MESH', 'CURVE'}:
            return {'CANCELLED'}
        bpy.ops.object.mode_set(mode='OBJECT' if obj.mode == 'EDIT' else 'EDIT')
        return {'FINISHED'}


class POYARA_PT_command_panel(Panel):
    bl_label = 'POYARA | Modify'
    bl_idname = 'POYARA_PT_command_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'POYARA'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.poyara_maxline, 'tab', expand=True)
        obj = context.active_object
        layout.label(text='MAX-STYLE COMMAND PANEL', icon='MODIFIER')
        if context.scene.poyara_maxline.tab == 'EDIT_SPLINE':
            layout.operator('poyara.draw_line', text='Create Line', icon='CURVE_PATH')
        if obj is None or obj.type not in {'MESH', 'CURVE'}:
            layout.label(text='Select a Curve or Mesh to modify')
            return
        layout.label(text=f'{obj.name}   |   {"Edit Poly" if obj.type == "MESH" else "Edit Spline"}')
        layout.operator('poyara.toggle_edit', text='Exit Native Edit' if obj.mode == 'EDIT' else 'Native Edit (Tab)',
                        icon='EDITMODE_HLT')


class POYARA_PT_spline(Panel):
    bl_label = 'Edit Spline'
    bl_parent_id = 'POYARA_PT_command_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    @classmethod
    def poll(cls, context):
        return context.scene.poyara_maxline.tab == 'EDIT_SPLINE' and _is_curve(context.active_object)

    def draw(self, context):
        layout = self.layout
        settings = context.scene.poyara_maxline
        col = layout.box().column(align=True)
        col.label(text='Selection', icon='RESTRICT_SELECT_OFF')
        col.prop(settings, 'selection_mode', expand=True)
        col.operator('poyara.edit_spline', text='Edit Spline | Select + Move', icon='CURVE_BEZCURVE')
        col.label(text='1 / 2 / 3 = Vertex / Segment / Spline')
        row = col.row(align=True)
        row.operator('poyara.set_vertex_xyz', text='Vertex XYZ...', icon='EVENT_X')
        col.prop(settings, 'snap_step')
        col = layout.box().column(align=True)
        col.label(text='Geometry', icon='CURVE_PATH')
        col.operator('poyara.draw_line', text='Create / Add Line', icon='ADD')
        col.label(text='In Max Edit: X Break | Shift+X Dissolve')
        col.label(text='S Smooth | H Corner')
        row = col.row(align=True)
        row.operator('poyara.curve_corner', text='Fillet...').kind = 'FILLET'
        row.operator('poyara.curve_corner', text='Chamfer...').kind = 'CHAMFER'
        col = layout.box().column(align=True)
        col.label(text='Edit Vertices / Segments / Splines')
        native = col.column(align=True)
        native.enabled = context.mode == 'EDIT_CURVE'
        native.operator_context = 'INVOKE_DEFAULT'
        row = native.row(align=True)
        row.operator('curve.subdivide', text='Refine')
        row.operator('curve.make_segment', text='Connect')
        row = native.row(align=True)
        row.operator('curve.dissolve_verts', text='Remove')
        row.operator('curve.delete', text='Delete').type = 'VERT'
        row = native.row(align=True)
        row.operator('curve.handle_type_set', text='Corner').type = 'VECTOR'
        row.operator('curve.handle_type_set', text='Smooth').type = 'AUTO'
        row = native.row(align=True)
        row.operator('curve.cyclic_toggle', text='Close / Open')
        row.operator('curve.switch_direction', text='Reverse')
        row = native.row(align=True)
        row.operator('curve.separate', text='Detach')
        row.operator('curve.spline_type_set', text='Bezier').type = 'BEZIER'
        col.label(text='Native tools: click Native Edit first')


class POYARA_PT_poly(Panel):
    bl_label = 'Edit Poly'
    bl_parent_id = 'POYARA_PT_command_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    @classmethod
    def poll(cls, context):
        return (context.scene.poyara_maxline.tab == 'EDIT_POLY' and
                context.active_object is not None and context.active_object.type == 'MESH')

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text='Selection', icon='RESTRICT_SELECT_OFF')
        row = box.row(align=True)
        for level, name in [('VERT', 'Vertex'), ('EDGE', 'Edge'), ('BORDER', 'Border')]:
            row.operator('poyara.mesh_level', text=name).level = level
        row = box.row(align=True)
        for level, name in [('FACE', 'Polygon'), ('ELEMENT', 'Element')]:
            row.operator('poyara.mesh_level', text=name).level = level
        box = layout.box()
        box.label(text='Edit Vertices / Edges', icon='EDITMODE_HLT')
        col = box.column(align=True)
        col.enabled = context.mode == 'EDIT_MESH'
        col.operator_context = 'INVOKE_DEFAULT'
        row = col.row(align=True)
        row.operator('poyara.connect_edges', text='Connect...')
        row.operator('mesh.merge', text='Weld / Merge')
        row = col.row(align=True)
        row.operator('mesh.dissolve_verts', text='Remove Vertex')
        row.operator('mesh.delete', text='Delete').type = 'VERT'
        row = col.row(align=True)
        row.operator('poyara.bevel', text='Chamfer...').kind = 'CHAMFER'
        row.operator('poyara.bevel', text='Fillet...').kind = 'FILLET'
        row = col.row(align=True)
        row.operator('mesh.subdivide', text='Subdivide')
        row.operator('mesh.bridge_edge_loops', text='Bridge')
        box = layout.box()
        box.label(text='Edit Polygons', icon='FACESEL')
        col = box.column(align=True)
        col.enabled = context.mode == 'EDIT_MESH'
        col.operator_context = 'INVOKE_DEFAULT'
        row = col.row(align=True)
        row.operator('poyara.extrude', text='Extrude Parameters...')
        row.operator('mesh.inset', text='Inset')
        row = col.row(align=True)
        row.operator('mesh.extrude_manifold', text='Extrude Manifold')
        row.operator('mesh.poke', text='Tessellate (Poke)')
        box = layout.box()
        box.label(text='Edit Geometry')
        col = box.column(align=True)
        col.enabled = context.mode == 'EDIT_MESH'
        col.operator_context = 'INVOKE_DEFAULT'
        row = col.row(align=True)
        row.operator('mesh.remove_doubles', text='Weld by Distance')
        row.operator('mesh.fill', text='Cap / Fill')
        row = col.row(align=True)
        row.operator('mesh.flip_normals', text='Flip Normals')
        row.operator('mesh.quads_convert_to_tris', text='Triangulate')
        col.label(text='F9: last operation parameters')


_CLASSES = (
    POYARA_PG_settings,
    POYARA_OT_draw_line,
    POYARA_OT_edit_spline,
    POYARA_OT_set_vertex_xyz,
    POYARA_OT_mesh_level,
    POYARA_OT_mode_toggle,
    POYARA_PT_command_panel,
    POYARA_PT_spline,
    POYARA_PT_poly,
)

from .extras import EXTRA_CLASSES
_CLASSES += EXTRA_CLASSES


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.poyara_maxline = PointerProperty(type=POYARA_PG_settings)


def unregister():
    del bpy.types.Scene.poyara_maxline
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()

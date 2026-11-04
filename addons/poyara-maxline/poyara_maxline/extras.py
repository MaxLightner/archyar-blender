"""Practical 3ds Max-inspired creation, mesh and utility operators."""

import math

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator, Panel
from mathutils import Euler, Matrix, Vector, geometry

from . import _knots, _project, _read_point, _rebuild_curve, _serialize_curve, _world_from_mouse


def _snap(p, context, use_snap):
    if not use_snap or p is None:
        return p
    step = context.scene.poyara_maxline.snap_step
    return Vector(tuple(round(x / step) * step for x in p))


def _snap_in_plane(point, origin, basis, context, use_snap):
    if point is None or not use_snap:
        return point
    step = context.scene.poyara_maxline.snap_step
    local = basis.transposed() @ (point - origin)
    local.x = round(local.x / step) * step
    local.y = round(local.y / step) * step
    local.z = 0.0
    return origin + basis @ local


def _box_points(first, second, height, basis):
    """Create corners on the first picked construction plane, not world XY."""
    local = basis.transposed() @ (second - first)
    x0, x1 = sorted((0.0, local.x))
    y0, y1 = sorted((0.0, local.y))
    z0, z1 = sorted((0.0, height))
    return [first + basis @ Vector(p) for p in [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]]


def _pick_surface_frame(context, event):
    """AutoGrid frame from evaluated scene raycast, fallback to cursor XY."""
    from bpy_extras import view3d_utils
    region, rv3d = context.region, context.space_data.region_3d
    mouse = (event.mouse_region_x, event.mouse_region_y)
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    if context.scene.poyara_maxline.surface_snap:
        hit, location, normal, _, hit_obj, _ = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origin, ray, distance=10000.0
        )
        if hit and hit_obj is not None:
            normal = normal.normalized()
            tangent = Vector((1, 0, 0)) - normal * normal.x
            if tangent.length_squared < 0.01:
                tangent = Vector((0, 1, 0)) - normal * normal.y
            tangent.normalize()
            bitangent = normal.cross(tangent).normalized()
            basis = Matrix((tangent, bitangent, normal)).transposed()
            return location, normal, basis
    origin = context.scene.cursor.location.copy()
    normal = Vector((0, 0, 1))
    basis = Matrix.Identity(3)
    return origin, normal, basis


_BOX_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0),
              (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)]
_BOX_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _draw_box(operator, context):
    if operator._first is None:
        return
    try:
        import gpu
        from gpu_extras.batch import batch_for_shader

        target = operator._second or operator._hover
        if target is None:
            return
        h = operator._height if operator._stage == 2 else 0.0
        corners = _box_points(operator._first, target, h, operator._basis)
        coords = [_project(context, p) for p in corners]
        verts = []
        for a, b in _BOX_EDGES:
            if coords[a] is not None and coords[b] is not None:
                verts.extend((coords[a], coords[b]))
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float('color', (0.22, 0.76, 1.0, 1.0))
        gpu.state.line_width_set(2.0)
        batch_for_shader(shader, 'LINES', {'pos': verts}).draw(shader)
    except (ReferenceError, RuntimeError, ValueError):
        pass


class POYARA_OT_box_3point(Operator):
    bl_idname = 'poyara.box_3point'
    bl_label = 'Box | 3-Point Creation'
    bl_description = 'Click first base corner, opposite base corner, then height'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        self._stage = 0
        self._first = None
        self._second = None
        self._hover = None
        self._height = 0.0
        self._plane = context.scene.cursor.location.copy()
        self._normal = Vector((0, 0, 1))
        self._basis = Matrix.Identity(3)
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_box, (self, context), 'WINDOW', 'POST_PIXEL'
        )
        context.workspace.status_text_set('MAX BOX AutoGrid: click surface/base corner / opposite corner / height | Ctrl snap | Esc cancel')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _get_height(self, context, event):
        base = (self._first + self._second) / 2
        region, rv3d = context.region, context.space_data.region_3d
        from bpy_extras import view3d_utils
        coords = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coords)
        ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, coords)
        candidates = geometry.intersect_line_line(origin, origin + ray * 1000.0,
                                                   base, base + self._normal)
        if candidates is not None and abs(ray.dot(self._normal)) < 0.98:
            return (candidates[1] - base).dot(self._normal)
        # In top/near-top views the height axis is parallel to the view ray.
        factor = max(0.001, rv3d.view_distance * 1.6 / max(region.height, 1))
        return (event.mouse_region_y - self._height_start_y) * factor

    def _stop(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            if self._stage < 2:
                self._hover = _snap_in_plane(_world_from_mouse(
                    context, event.mouse_region_x, event.mouse_region_y, self._plane, self._normal
                ), self._plane, self._basis, context, event.ctrl)
            else:
                self._height = self._get_height(context, event)
                if event.ctrl:
                    step = context.scene.poyara_maxline.snap_step
                    self._height = round(self._height / step) * step
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'ESC' and event.value == 'PRESS':
            self._stop(context)
            return {'CANCELLED'}
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        if self._stage < 2:
            if self._stage == 0:
                self._plane, self._normal, self._basis = _pick_surface_frame(context, event)
            p = _snap_in_plane(_world_from_mouse(
                context, event.mouse_region_x, event.mouse_region_y, self._plane, self._normal
            ), self._plane, self._basis, context, event.ctrl)
            if p is None:
                return {'RUNNING_MODAL'}
            if self._stage == 0:
                self._first = p
                self._stage = 1
            else:
                local = self._basis.transposed() @ (p - self._first)
                if abs(local.x) < 0.0001 or abs(local.y) < 0.0001:
                    self.report({'WARNING'}, 'Base must have non-zero width and depth')
                    return {'RUNNING_MODAL'}
                self._second = p
                self._height_start_y = event.mouse_region_y
                self._stage = 2
            return {'RUNNING_MODAL'}
        self._height = self._get_height(context, event)
        if event.ctrl:
            step = context.scene.poyara_maxline.snap_step
            self._height = round(self._height / step) * step
        if abs(self._height) < 0.0001:
            self.report({'WARNING'}, 'Move cursor to give the box some height')
            return {'RUNNING_MODAL'}
        corners = _box_points(self._first, self._second, self._height, self._basis)
        origin = corners[0]
        verts = [tuple(self._basis.transposed() @ (p - origin)) for p in corners]
        mesh = bpy.data.meshes.new('MaxBox')
        mesh.from_pydata(verts, _BOX_EDGES, _BOX_FACES)
        mesh.update()
        obj = bpy.data.objects.new('MaxBox', mesh)
        context.collection.objects.link(obj)
        obj.matrix_world = self._basis.to_4x4()
        obj.matrix_world.translation = origin
        obj['poyara_maxbox'] = True
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self._stop(context)
        return {'FINISHED'}


class POYARA_OT_box_size(Operator):
    bl_idname = 'poyara.box_size'
    bl_label = 'Box Parameters'
    bl_options = {'REGISTER', 'UNDO'}

    width: FloatProperty(name='Width (X)', unit='LENGTH', min=0.001)
    length: FloatProperty(name='Length (Y)', unit='LENGTH', min=0.001)
    height: FloatProperty(name='Height (Z)', unit='LENGTH', min=0.001)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.get('poyara_maxbox', False)

    def invoke(self, context, event):
        self.width, self.length, self.height = context.active_object.dimensions
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        context.active_object.dimensions = (self.width, self.length, self.height)
        return {'FINISHED'}


class POYARA_OT_connect_edges(Operator):
    bl_idname = 'poyara.connect_edges'
    bl_label = 'Connect Edges (Max-style)'
    bl_description = 'Select two opposite edges of one quad, then choose Segments / Pinch / Slide'
    bl_options = {'REGISTER', 'UNDO'}

    segments: IntProperty(name='Segments', default=1, min=1, max=30)
    pinch: FloatProperty(name='Pinch', default=0, min=-90, max=90)
    slide: FloatProperty(name='Slide', default=0, min=-100, max=100)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=290)

    def execute(self, context):
        mesh = context.edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        selected = [edge for edge in bm.edges if edge.select]
        if len(selected) != 2:
            self.report({'ERROR'}, 'Select exactly TWO opposite edges of one quad')
            return {'CANCELLED'}
        face = next((face for face in bm.faces if len(face.verts) == 4 and
                     all(edge in face.edges for edge in selected)), None)
        if face is None:
            self.report({'ERROR'}, 'The two edges must belong to the same quad')
            return {'CANCELLED'}
        winding = list(face.verts)
        boundaries = list(face.edges)
        a_index, b_index = (boundaries.index(edge) for edge in selected)
        if (a_index - b_index) % 4 != 2:
            self.report({'ERROR'}, 'Select two opposite (not adjacent) quad edges')
            return {'CANCELLED'}

        a0, a1 = winding[a_index].co.copy(), winding[(a_index + 1) % 4].co.copy()
        b0, b1 = winding[(b_index + 1) % 4].co.copy(), winding[b_index].co.copy()
        # IMPORTANT: never feed freshly split verts back into connect_verts.
        # That path can create invalid BMesh topology and has caused a hard
        # Blender crash. Delegate the topology change to Blender's tested
        # native edge-ring operator, then adjust *coordinates only*.
        existing_coords = {tuple(round(x, 5) for x in v.co) for v in bm.verts}
        try:
            outcome = bpy.ops.mesh.subdivide_edgering(
                number_cuts=self.segments, interpolation='LINEAR', smoothness=0.0
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, f'Native Connect failed: {exc}')
            return {'CANCELLED'}
        if 'FINISHED' not in outcome:
            self.report({'ERROR'}, 'Blender could not subdivide this edge ring')
            return {'CANCELLED'}
        # The common 1-segment/zero-offset case stays 100% native: do not
        # inspect or touch edit BMesh after the topology operator runs.
        if abs(self.pinch) < 1e-7 and abs(self.slide) < 1e-7:
            return {'FINISHED'}
        bm = bmesh.from_edit_mesh(mesh)
        # Mesh topology is now already valid. New knots are identified by
        # geometry, never by stale BMesh references from before the operator.
        added = [v for v in bm.verts
                 if tuple(round(x, 5) for x in v.co) not in existing_coords]

        def along(v, start, end):
            direction = end - start
            denom = direction.length_squared
            t = (v.co - start).dot(direction) / denom if denom else 0.0
            error = (v.co - (start + t * direction)).length
            return t, error

        a_vertices = [v for v in added if along(v, a0, a1)[1] < 1e-4]
        b_vertices = [v for v in added if along(v, b0, b1)[1] < 1e-4]
        a_vertices.sort(key=lambda v: along(v, a0, a1)[0])
        b_vertices.sort(key=lambda v: along(v, b0, b1)[0])
        if len(a_vertices) != self.segments or len(b_vertices) != self.segments:
            self.report({'WARNING'}, 'Connect created; Pinch/Slide skipped for this topology')
            return {'FINISHED'}

        fractions = [(i + 1) / (self.segments + 1) for i in range(self.segments)]
        spread = 1.0 + self.pinch / 100.0
        fractions = [max(0.001, min(0.999, 0.5 + (t - 0.5) * spread)) for t in fractions]
        # Translate the whole cut group while keeping all cuts inside the face.
        max_left = min(fractions)
        max_right = 1.0 - max(fractions)
        slide_amount = (self.slide / 100.0) * (max_right if self.slide >= 0 else max_left)
        fractions = [t + slide_amount for t in fractions]
        for av, bv, t in zip(a_vertices, b_vertices, fractions):
            av.co = a0.lerp(a1, t)
            bv.co = b0.lerp(b1, t)
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        return {'FINISHED'}


class POYARA_OT_select_by_angle(Operator):
    bl_idname = 'poyara.select_by_angle'
    bl_label = 'Select Adjacent Polygons by Angle'
    bl_description = 'Grow only across connected faces whose normals differ by at most Angle'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        mesh = context.edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.normal_update()
        seeds = [face for face in bm.faces if face.select and not face.hide]
        if not seeds:
            self.report({'ERROR'}, 'Select at least one polygon before Select by Angle')
            return {'CANCELLED'}
        angle = math.radians(context.scene.poyara_maxline.angle_threshold)
        visited = set(seeds)
        stack = list(seeds)
        while stack:
            current = stack.pop()
            for edge in current.edges:
                for adjacent in edge.link_faces:
                    if adjacent in visited or adjacent.hide:
                        continue
                    if current.normal.angle(adjacent.normal, math.pi) <= angle + 1e-6:
                        visited.add(adjacent)
                        stack.append(adjacent)
        for face in visited:
            face.select_set(True)
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        self.report({'INFO'}, f'Selected {len(visited)} adjacent polygons')
        return {'FINISHED'}


class POYARA_OT_extrude(Operator):
    bl_idname = 'poyara.extrude'
    bl_label = 'Extrude | Parameters'
    bl_description = 'Extrude selected polygons with numeric height and optional outline'
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name='Mode', items=[('REGION', 'Region', 'One connected extrusion'),
                                           ('INDIVIDUAL', 'By Polygon', 'Extrude each face independently')])
    height: FloatProperty(name='Height', default=0.2, unit='LENGTH')
    outline: FloatProperty(name='Outline', default=0.0, unit='LENGTH')

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=280)

    def execute(self, context):
        mesh = context.edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        faces = [face for face in bm.faces if face.select]
        if not faces:
            self.report({'ERROR'}, 'Select one or more polygons first')
            return {'CANCELLED'}
        if self.mode == 'REGION':
            normal = sum((f.normal * f.calc_area() for f in faces), Vector())
            if normal.length_squared < 1e-10:
                self.report({'ERROR'}, 'Face normals cancel; use By Polygon mode')
                return {'CANCELLED'}
            normal.normalize()
            result = bmesh.ops.extrude_face_region(bm, geom=faces)
            vertices = [g for g in result['geom'] if isinstance(g, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, verts=vertices, vec=normal * self.height)
            if self.outline and vertices:
                center = sum((v.co for v in vertices), Vector()) / len(vertices)
                radius = max(((v.co - center).length for v in vertices), default=1.0)
                factor = max(0.05, 1 + self.outline / max(radius, 0.001))
                for v in vertices:
                    direction = v.co - center
                    lateral = direction - normal * direction.dot(normal)
                    v.co += lateral * (factor - 1)
        else:
            result = bmesh.ops.extrude_discrete_faces(bm, faces=faces)
            for face in result['faces']:
                normal = face.normal.copy()
                center = face.calc_center_median()
                for v in face.verts:
                    v.co += normal * self.height
                    if self.outline:
                        tangent = (v.co - center)
                        tangent -= normal * tangent.dot(normal)
                        radius = max(0.001, tangent.length)
                        v.co += tangent.normalized() * min(abs(self.outline), radius * 0.9) * (1 if self.outline > 0 else -1)
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=True)
        return {'FINISHED'}


class POYARA_OT_bevel(Operator):
    bl_idname = 'poyara.bevel'
    bl_label = 'Mesh Fillet / Chamfer'
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(name='Type', items=[('CHAMFER', 'Chamfer', ''), ('FILLET', 'Fillet', '')])
    width: FloatProperty(name='Amount', default=0.02, min=0.00001, unit='LENGTH')
    segments: IntProperty(name='Segments', default=5, min=1, max=64)
    vertices: BoolProperty(name='Vertex Only', default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        if self.kind == 'CHAMFER':
            self.segments = 1
        return context.window_manager.invoke_props_dialog(self, width=280)

    def execute(self, context):
        bpy.ops.mesh.bevel('EXEC_DEFAULT', offset=self.width,
                           segments=1 if self.kind == 'CHAMFER' else self.segments,
                           affect='VERTICES' if self.vertices else 'EDGES')
        return {'FINISHED'}


class POYARA_OT_curve_corner(Operator):
    bl_idname = 'poyara.curve_corner'
    bl_label = 'Spline Fillet / Chamfer'
    bl_description = 'Select interior Bezier control points in native Curve Edit Mode'
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(name='Type', items=[('CHAMFER', 'Chamfer', ''), ('FILLET', 'Fillet', '')])
    distance: FloatProperty(name='Distance', default=0.1, min=0.00001, unit='LENGTH')
    segments: IntProperty(name='Fillet Steps', default=8, min=3, max=32)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_CURVE' and context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=280)

    def execute(self, context):
        obj = context.active_object
        chosen = {}
        for si, spline in enumerate(obj.data.splines):
            if spline.type == 'BEZIER':
                chosen[si] = {vi for vi, p in enumerate(spline.bezier_points) if p.select_control_point}
        if not any(chosen.values()):
            self.report({'ERROR'}, 'Select Bezier spline control points first')
            return {'CANCELLED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        specs = _serialize_curve(obj.data)
        changed = 0
        for si, spec in enumerate(specs):
            if spec['type'] != 'BEZIER':
                continue
            points = spec['points']
            result = []
            cyclic = spec['cyclic']
            for vi, point in enumerate(points):
                if vi not in chosen.get(si, set()) or (not cyclic and (vi == 0 or vi == len(points) - 1)):
                    result.append(point)
                    continue
                pivot = Vector(point['co'])
                prev = Vector(points[(vi - 1) % len(points)]['co'])
                following = Vector(points[(vi + 1) % len(points)]['co'])
                left, right = prev - pivot, following - pivot
                if left.length < 1e-5 or right.length < 1e-5:
                    result.append(point)
                    continue
                dist = min(self.distance, left.length * 0.49, right.length * 0.49)
                a = pivot + left.normalized() * dist
                b = pivot + right.normalized() * dist
                count = 1 if self.kind == 'CHAMFER' else self.segments
                for step in range(count + 1):
                    t = step / count
                    co = a.lerp(b, t) if count == 1 else ((1 - t) ** 2 * a +
                                                       2 * (1 - t) * t * pivot + t ** 2 * b)
                    new = {**point, 'co': tuple(co), 'left': tuple(co), 'right': tuple(co),
                           'left_type': 'VECTOR', 'right_type': 'VECTOR'}
                    result.append(new)
                changed += 1
            spec['points'] = result
        _rebuild_curve(obj.data, specs)
        bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, f'Updated {changed} spline corners')
        return {'FINISHED'}


class POYARA_OT_boolean(Operator):
    bl_idname = 'poyara.boolean'
    bl_label = 'Quick Boolean'
    bl_description = 'Active mesh = target; other selected mesh = cutter. Keeps an editable Boolean modifier'
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(items=[('DIFFERENCE', 'Subtract', ''),
                                   ('UNION', 'Union', ''), ('INTERSECT', 'Intersect', '')])

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        target = context.active_object
        others = [o for o in context.selected_objects if o is not target and o.type == 'MESH']
        if len(others) != 1:
            self.report({'ERROR'}, 'Select exactly two meshes; active mesh is the target')
            return {'CANCELLED'}
        cutter = others[0]
        modifier = target.modifiers.new(f'POYARA Boolean | {self.operation.title()}', 'BOOLEAN')
        modifier.operation = self.operation
        modifier.solver = 'EXACT'
        modifier.object = cutter
        cutter.display_type = 'WIRE'
        self.report({'INFO'}, f'Boolean added; adjust it from the POYARA Extras panel')
        return {'FINISHED'}


class POYARA_OT_boolean_apply(Operator):
    bl_idname = 'poyara.boolean_apply'
    bl_label = 'Apply Boolean'
    bl_description = 'Apply this Boolean; the cutter object is kept'
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: bpy.props.StringProperty()

    def execute(self, context):
        if context.mode != 'OBJECT' or context.active_object is None:
            return {'CANCELLED'}
        bpy.ops.object.modifier_apply(modifier=self.modifier_name)
        return {'FINISHED'}


class POYARA_OT_array(Operator):
    bl_idname = 'poyara.array'
    bl_label = 'Array (Max-style)'
    bl_description = 'Grid array of copies or linked instances, including incremental rotation'
    bl_options = {'REGISTER', 'UNDO'}

    count_x: IntProperty(name='Count X', default=3, min=1, max=100)
    count_y: IntProperty(name='Count Y', default=1, min=1, max=100)
    count_z: IntProperty(name='Count Z', default=1, min=1, max=100)
    offset_x: FloatProperty(name='X Spacing', default=1.0, unit='LENGTH')
    offset_y: FloatProperty(name='Y Spacing', default=1.0, unit='LENGTH')
    offset_z: FloatProperty(name='Z Spacing', default=1.0, unit='LENGTH')
    rot_x: FloatProperty(name='Rotation X', default=0, subtype='ANGLE')
    rot_y: FloatProperty(name='Rotation Y', default=0, subtype='ANGLE')
    rot_z: FloatProperty(name='Rotation Z', default=0, subtype='ANGLE')
    instance: BoolProperty(name='Instance (shared mesh)', default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        total = self.count_x * self.count_y * self.count_z
        if total > 300:
            self.report({'ERROR'}, 'Max 300 instances per operation for responsiveness')
            return {'CANCELLED'}
        src = context.active_object
        for i in range(self.count_x):
            for j in range(self.count_y):
                for k in range(self.count_z):
                    if i == j == k == 0:
                        continue
                    obj = src.copy()
                    if not self.instance and src.data is not None:
                        obj.data = src.data.copy()
                    for collection in src.users_collection:
                        collection.objects.link(obj)
                    turn = i + j + k
                    transform = (Matrix.Translation((i * self.offset_x, j * self.offset_y,
                                                     k * self.offset_z)) @
                                 Euler((turn * self.rot_x, turn * self.rot_y,
                                        turn * self.rot_z)).to_matrix().to_4x4())
                    obj.matrix_world = src.matrix_world @ transform
        return {'FINISHED'}


class POYARA_OT_align(Operator):
    bl_idname = 'poyara.align'
    bl_label = 'Align (Max-style)'
    bl_description = 'Select two objects: active = target, other = object to move'
    bl_options = {'REGISTER', 'UNDO'}

    x: BoolProperty(name='X', default=True)
    y: BoolProperty(name='Y', default=True)
    z: BoolProperty(name='Z', default=True)
    from_point: EnumProperty(name='Current Object', items=[('MIN', 'Minimum', ''),
                                                          ('CENTER', 'Center', ''), ('MAX', 'Maximum', '')],
                             default='CENTER')
    to_point: EnumProperty(name='Target Object', items=[('MIN', 'Minimum', ''),
                                                        ('CENTER', 'Center', ''), ('MAX', 'Maximum', '')],
                           default='CENTER')
    match_rotation: BoolProperty(name='Match Rotation', default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=290)

    def execute(self, context):
        target = context.active_object
        others = [obj for obj in context.selected_objects if obj is not target]
        if len(others) != 1:
            self.report({'ERROR'}, 'Select exactly two objects; active object is target')
            return {'CANCELLED'}
        source = others[0]

        def bounds(obj):
            points = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
            low = Vector((min(p[i] for p in points) for i in range(3)))
            high = Vector((max(p[i] for p in points) for i in range(3)))
            return {'MIN': low, 'CENTER': (low + high) / 2, 'MAX': high}

        if self.match_rotation:
            location = source.matrix_world.translation.copy()
            scale = source.matrix_world.to_scale()
            source.matrix_world = (Matrix.Translation(location) @
                                   target.matrix_world.to_quaternion().to_matrix().to_4x4() @
                                   Matrix.Diagonal((scale.x, scale.y, scale.z, 1.0)))
        source_pos, target_pos = bounds(source)[self.from_point], bounds(target)[self.to_point]
        delta = target_pos - source_pos
        for axis, enabled in enumerate((self.x, self.y, self.z)):
            if not enabled:
                delta[axis] = 0
        source.matrix_world.translation += delta
        return {'FINISHED'}


class POYARA_PT_extras(Panel):
    bl_label = 'Create + Modifiers + Utilities'
    bl_parent_id = 'POYARA_PT_command_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    @classmethod
    def poll(cls, context):
        return context.scene.poyara_maxline.tab == 'EXTRAS'

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text='Standard Primitives', icon='MESH_CUBE')
        box.operator('poyara.box_3point', text='Box | 3 Clicks')
        box.prop(context.scene.poyara_maxline, 'surface_snap', text='AutoGrid / Surface Snap')
        box.operator('poyara.box_size', text='Box Parameters')
        box.operator('poyara.plane', text='Plane...')
        row = box.row(align=True)
        row.operator('poyara.circle', text='Circle...')
        row.operator('poyara.rectangle', text='Rectangle...')
        box.operator('poyara.spiral', text='Spiral...')
        arch = layout.box()
        arch.label(text='Architecture (Archyar)', icon='HOME')
        arch.operator('poyara.arch_wall', text='Draw Wall')
        settings = context.scene.poyara_arch
        col = arch.column(align=True)
        col.prop(settings, 'wall_thickness')
        col.prop(settings, 'wall_height')
        col.prop(settings, 'elevation')
        row = arch.row(align=True)
        row.operator('poyara.arch_opening', text='Door').style = 'door'
        row.operator('poyara.arch_opening', text='Sliding Door').style = 'sliding-door'
        row = arch.row(align=True)
        row.operator('poyara.arch_opening', text='Window').style = 'fixed'
        row.operator('poyara.arch_opening', text='Sliding Window').style = 'sliding'
        col = arch.column(align=True)
        col.prop(settings, 'door_width')
        col.prop(settings, 'door_height')
        col.prop(settings, 'window_width')
        col.prop(settings, 'window_height')
        col.prop(settings, 'window_sill')
        box = layout.box()
        box.label(text='Boolean', icon='MOD_BOOLEAN')
        row = box.row(align=True)
        for action, name in [('DIFFERENCE', 'Subtract'), ('UNION', 'Union'), ('INTERSECT', 'Intersect')]:
            row.operator('poyara.boolean', text=name).operation = action
        obj = context.active_object
        if obj and obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'BOOLEAN' and mod.name.startswith('POYARA Boolean'):
                    sub = box.box()
                    sub.label(text=mod.name)
                    sub.prop(mod, 'operation', expand=True)
                    sub.prop(mod, 'object', text='Cutter')
                    sub.operator('poyara.boolean_apply', text='Apply (keep cutter)').modifier_name = mod.name
        box = layout.box()
        box.label(text='Transform', icon='ORIENTATION_GLOBAL')
        row = box.row(align=True)
        row.operator('poyara.array', text='Array...')
        row.operator('poyara.align', text='Align...')
        box.operator('poyara.live_array', text='Live Array Modifier')
        if obj and obj.type in {'MESH', 'CURVE'}:
            draw_live_array_controls(box, obj)
        box.label(text='Future: Stairs / Railings')


EXTRA_CLASSES = (
    POYARA_OT_box_3point,
    POYARA_OT_box_size,
    POYARA_OT_connect_edges,
    POYARA_OT_select_by_angle,
    POYARA_OT_extrude,
    POYARA_OT_bevel,
    POYARA_OT_curve_corner,
    POYARA_OT_boolean,
    POYARA_OT_boolean_apply,
    POYARA_OT_array,
    POYARA_OT_align,
    POYARA_PT_extras,
)

from .primitives import PRIMITIVE_CLASSES
from .architecture import ARCH_CLASSES
from .live_tools import (LIVE_CLASSES, draw_live_array_controls,
                         draw_live_mesh_controls, draw_live_curve_controls)

EXTRA_CLASSES += PRIMITIVE_CLASSES + ARCH_CLASSES + LIVE_CLASSES

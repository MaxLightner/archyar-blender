"""Max-inspired primitive creation with exact, editable numeric dimensions."""

import math

import bpy
from bpy.props import FloatProperty, IntProperty
from bpy.types import Operator
from mathutils import Vector


def _activate(context, obj):
    for other in context.selected_objects:
        other.select_set(False)
    context.view_layer.objects.active = obj
    obj.select_set(True)


def _curve_object(context, name, points, cyclic, bezier=False):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 24
    if bezier:
        spline = curve.splines.new('BEZIER')
        spline.bezier_points.add(len(points) - 1)
        for knot, coord in zip(spline.bezier_points, points):
            knot.co = coord
            knot.handle_left_type = 'VECTOR'
            knot.handle_right_type = 'VECTOR'
    else:
        spline = curve.splines.new('POLY')
        spline.points.add(len(points) - 1)
        for knot, coord in zip(spline.points, points):
            knot.co = (*coord, 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    context.collection.objects.link(obj)
    obj.location = context.scene.cursor.location
    _activate(context, obj)
    return obj


class _CreatePrimitive(Operator):
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=290)


class POYARA_OT_plane(_CreatePrimitive):
    bl_idname = 'poyara.plane'
    bl_label = 'Plane (Max-style)'
    width: FloatProperty(name='Width', default=2.0, min=.001, unit='LENGTH')
    length: FloatProperty(name='Length', default=2.0, min=.001, unit='LENGTH')
    width_segments: IntProperty(name='Width Segs', default=1, min=1, max=200)
    length_segments: IntProperty(name='Length Segs', default=1, min=1, max=200)

    def execute(self, context):
        nx, ny = self.width_segments, self.length_segments
        verts = [(-self.width / 2 + self.width * i / nx,
                  -self.length / 2 + self.length * j / ny, 0)
                 for j in range(ny + 1) for i in range(nx + 1)]
        faces = []
        for j in range(ny):
            for i in range(nx):
                a = j * (nx + 1) + i
                faces.append((a, a + 1, a + nx + 2, a + nx + 1))
        mesh = bpy.data.meshes.new('MaxPlane')
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new('MaxPlane', mesh)
        obj.location = context.scene.cursor.location
        context.collection.objects.link(obj)
        _activate(context, obj)
        return {'FINISHED'}


class POYARA_OT_circle(_CreatePrimitive):
    bl_idname = 'poyara.circle'
    bl_label = 'Circle (Max Spline)'
    radius: FloatProperty(name='Radius', default=1.0, min=.001, unit='LENGTH')

    def execute(self, context):
        radius = self.radius
        obj = _curve_object(context, 'MaxCircle', [(radius, 0, 0), (0, radius, 0),
                                                  (-radius, 0, 0), (0, -radius, 0)], True, True)
        # Four cubic Bezier arcs with the classic exact-circle approximation.
        kappa = .5522847498307936 * radius
        pts = obj.data.splines[0].bezier_points
        tangents = [(0, 1, 0), (-1, 0, 0), (0, -1, 0), (1, 0, 0)]
        for knot, tangent in zip(pts, tangents):
            v = Vector(tangent) * kappa
            knot.handle_left_type = 'FREE'
            knot.handle_right_type = 'FREE'
            knot.handle_left = knot.co - v
            knot.handle_right = knot.co + v
        return {'FINISHED'}


class POYARA_OT_rectangle(_CreatePrimitive):
    bl_idname = 'poyara.rectangle'
    bl_label = 'Rectangle (Max Spline)'
    width: FloatProperty(name='Width', default=2.0, min=.001, unit='LENGTH')
    length: FloatProperty(name='Length', default=1.0, min=.001, unit='LENGTH')
    corner_radius: FloatProperty(name='Corner Radius', default=0.0, min=0, unit='LENGTH')
    corner_steps: IntProperty(name='Corner Steps', default=6, min=1, max=32)

    def execute(self, context):
        w, h = self.width / 2, self.length / 2
        r = min(self.corner_radius, w, h)
        if r <= 1e-6:
            points = [(-w, -h, 0), (w, -h, 0), (w, h, 0), (-w, h, 0)]
        else:
            points = []
            for cx, cy, start in [(w-r, -h+r, -90), (w-r, h-r, 0),
                                  (-w+r, h-r, 90), (-w+r, -h+r, 180)]:
                for j in range(self.corner_steps + 1):
                    a = math.radians(start + 90 * j / self.corner_steps)
                    points.append((cx + r * math.cos(a), cy + r * math.sin(a), 0))
        _curve_object(context, 'MaxRectangle', points, True)
        return {'FINISHED'}


class POYARA_OT_spiral(_CreatePrimitive):
    bl_idname = 'poyara.spiral'
    bl_label = 'Spiral (Max Spline)'
    radius_start: FloatProperty(name='Start Radius', default=.25, min=0, unit='LENGTH')
    radius_end: FloatProperty(name='End Radius', default=1.5, min=0, unit='LENGTH')
    turns: FloatProperty(name='Turns', default=3.0, min=.1, max=100)
    height: FloatProperty(name='Height', default=0.0, unit='LENGTH')
    steps_per_turn: IntProperty(name='Steps / Turn', default=32, min=8, max=128)

    def execute(self, context):
        steps = max(2, math.ceil(self.turns * self.steps_per_turn))
        points = []
        for i in range(steps + 1):
            t = i / steps
            angle = 2 * math.pi * self.turns * t
            radius = (1 - t) * self.radius_start + t * self.radius_end
            points.append((radius * math.cos(angle), radius * math.sin(angle), self.height * t))
        _curve_object(context, 'MaxSpiral', points, False)
        return {'FINISHED'}


PRIMITIVE_CLASSES = (
    POYARA_OT_plane,
    POYARA_OT_circle,
    POYARA_OT_rectangle,
    POYARA_OT_spiral,
)

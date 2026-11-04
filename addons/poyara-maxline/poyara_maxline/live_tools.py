"""Non-destructive live modifier controls shown in POYARA's own panels."""

import math

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator


class POYARA_OT_live_array(Operator):
    bl_idname = 'poyara.live_array'
    bl_label = 'Live Array'
    bl_description = 'Create an adjustable Array modifier with live count and spacing'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type in {'MESH', 'CURVE'}

    def execute(self, context):
        mod = context.active_object.modifiers.new('POYARA Live Array', 'ARRAY')
        mod.count = 3
        mod.use_relative_offset = False
        mod.use_constant_offset = True
        mod.constant_offset_displace = (1.0, 0.0, 0.0)
        mod.show_in_editmode = True
        return {'FINISHED'}


class POYARA_OT_live_mesh_bevel(Operator):
    bl_idname = 'poyara.live_mesh_bevel'
    bl_label = 'Live Mesh Fillet / Chamfer'
    bl_description = 'Create a Bevel modifier; Width, Segments and Limit update visibly in real time'
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=[('CHAMFER', 'Chamfer', ''), ('FILLET', 'Fillet', '')])

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mod = obj.modifiers.new('POYARA Live ' + self.kind.title(), 'BEVEL')
        mod.width = .02
        mod.segments = 1 if self.kind == 'CHAMFER' else 6
        mod.limit_method = 'ANGLE'
        mod.angle_limit = math.radians(30)
        mod.affect = 'EDGES'
        mod.show_in_editmode = True
        return {'FINISHED'}


class POYARA_OT_live_curve_corner(Operator):
    bl_idname = 'poyara.live_curve_corner'
    bl_label = 'Live Spline Fillet / Chamfer'
    bl_description = 'Geometry Nodes corner rounding with live radius/count; applies to all knots of the Curve'
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=[('CHAMFER', 'Chamfer', ''), ('FILLET', 'Fillet', '')])

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'CURVE'

    def execute(self, context):
        obj = context.active_object
        group = bpy.data.node_groups.new('POYARA Live Curve ' + self.kind.title(), 'GeometryNodeTree')
        group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
        group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
        start = group.nodes.new('NodeGroupInput')
        start.location = (-420, 0)
        spline_type = group.nodes.new('GeometryNodeCurveSplineType')
        spline_type.spline_type = 'POLY'
        spline_type.location = (-160, 0)
        fillet = group.nodes.new('GeometryNodeFilletCurve')
        fillet.mode = 'POLY'
        fillet.inputs['Radius'].default_value = .1
        fillet.inputs['Count'].default_value = 1 if self.kind == 'CHAMFER' else 8
        fillet.location = (80, 0)
        end = group.nodes.new('NodeGroupOutput')
        end.location = (340, 0)
        group.links.new(start.outputs['Geometry'], spline_type.inputs['Curve'])
        group.links.new(spline_type.outputs['Curve'], fillet.inputs['Curve'])
        group.links.new(fillet.outputs['Curve'], end.inputs['Geometry'])
        mod = obj.modifiers.new('POYARA Live Spline ' + self.kind.title(), 'NODES')
        mod.node_group = group
        return {'FINISHED'}


def draw_live_mesh_controls(layout, obj):
    for mod in obj.modifiers:
        if mod.type == 'BEVEL' and mod.name.startswith('POYARA Live'):
            sub = layout.box()
            sub.label(text=mod.name)
            sub.prop(mod, 'width', text='Amount', slider=True)
            sub.prop(mod, 'segments', text='Segments')
            sub.prop(mod, 'affect', text='Affect')
            sub.prop(mod, 'limit_method', text='Limit')
            if mod.limit_method == 'ANGLE':
                sub.prop(mod, 'angle_limit', text='Angle')


def draw_live_curve_controls(layout, obj):
    for mod in obj.modifiers:
        if mod.type != 'NODES' or not mod.name.startswith('POYARA Live Spline') or not mod.node_group:
            continue
        fillet = next((n for n in mod.node_group.nodes if n.bl_idname == 'GeometryNodeFilletCurve'), None)
        if fillet:
            sub = layout.box()
            sub.label(text=mod.name)
            sub.prop(fillet.inputs['Radius'], 'default_value', text='Radius', slider=True)
            sub.prop(fillet.inputs['Count'], 'default_value', text='Segments')


def draw_live_array_controls(layout, obj):
    for mod in obj.modifiers:
        if mod.type == 'ARRAY' and mod.name.startswith('POYARA Live Array'):
            sub = layout.box()
            sub.label(text=mod.name)
            sub.prop(mod, 'count', text='Count')
            sub.prop(mod, 'constant_offset_displace', text='Step XYZ')
            sub.prop(mod, 'use_merge_vertices', text='Weld')


LIVE_CLASSES = (POYARA_OT_live_array, POYARA_OT_live_mesh_bevel,
                POYARA_OT_live_curve_corner)

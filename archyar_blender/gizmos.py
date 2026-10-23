"""Native Blender handles that appear automatically on Archyar wall selection.

Unlike the older explicit edit operator, the gizmo group is discoverable via a
normal click: select the wall's semantic Empty, then drag either blue endpoint
or the orange midpoint in either a top plan or perspective viewport.
"""

import bpy
from mathutils import Vector

from . import geometry
from .operators import (apply_wall_connection_changes, snap_point,
                        wall_connection_changes)


def selected_wall():
    context = bpy.context
    obj = context.view_layer.objects.active if context.view_layer else None
    if obj is not None and obj.get("archyar_kind") == "WALL":
        return obj
    return None


def handle_position(index):
    wall = selected_wall()
    if wall is None:
        return (0.0, 0.0, 0.0)
    props = wall.archyar_wall
    a, b = Vector(props.start), Vector(props.end)
    point = a if index == 0 else b if index == 1 else (a + b) / 2
    return (point.x, point.y, props.elevation + .015)


def move_handle(index, value):
    wall = selected_wall()
    if wall is None or len(value) < 2:
        return
    props = wall.archyar_wall
    a, b = Vector(props.start), Vector(props.end)
    raw = Vector((value[0], value[1], props.elevation))
    scene = bpy.context.scene
    snapped = Vector(snap_point(raw, scene, excluded={wall.name}))
    if index == 0:
        new_a, new_b = snapped, b
    elif index == 1:
        new_a, new_b = a, snapped
    else:
        delta = snapped - (a + b) / 2
        new_a, new_b = a + delta, b + delta
    if (new_a-a).length < .0005 and (new_b-b).length < .0005:
        return
    try:
        changes = wall_connection_changes(wall, new_a, new_b)
    except ValueError:
        # An opening, a short connected wall or a locked joint forbids this move.
        return
    apply_wall_connection_changes(changes)


class VIEW3D_GGT_archyar_wall_handles(bpy.types.GizmoGroup):
    bl_idname = "VIEW3D_GGT_archyar_wall_handles"
    bl_label = "Archyar Wall Handles"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active if context.view_layer else None
        return bool(context.mode == 'OBJECT' and
                    getattr(context.scene, "archyar_show_wall_handles", False) and
                    obj and obj.get("archyar_kind") == "WALL")

    def setup(self, context):
        self.handles = []
        for index in range(3):
            gizmo = self.gizmos.new("GIZMO_GT_move_3d")
            gizmo.target_set_handler(
                "offset",
                get=lambda i=index: handle_position(i),
                set=lambda value, i=index: move_handle(i, value))
            gizmo.color = (.18, .68, 1.0) if index != 2 else (1.0, .58, .12)
            gizmo.alpha = .85
            gizmo.color_highlight = (1.0, 1.0, 1.0)
            gizmo.alpha_highlight = 1.0
            gizmo.scale_basis = .17 if index != 2 else .20
            gizmo.use_draw_value = False
            gizmo.use_undo = True
            self.handles.append(gizmo)

    def draw_prepare(self, context):
        for gizmo in self.handles:
            gizmo.matrix_basis.identity()


def selected_opening():
    obj = bpy.context.view_layer.objects.active if bpy.context.view_layer else None
    return obj if obj is not None and obj.get('archyar_kind') == 'OPENING' else None


def opening_handle_position(index):
    root = selected_opening()
    if root is None or root.parent is None:
        return (0.0, 0.0, 0.0)
    wall = root.parent.archyar_wall
    a, b = Vector(wall.start), Vector(wall.end)
    segment = b - a
    length = segment.length
    if length < .1:
        return (0.0, 0.0, 0.0)
    direction = segment / length
    t = float(root['archyar_t'])
    width = float(root['width'])
    dist = length * t + (-width / 2 if index == 0 else width / 2 if index == 1 else 0)
    normal = Vector((-direction.y, direction.x)) * (wall.thickness / 2 + .07)
    pt = a + direction * dist + normal
    sill = float(root['sill'])
    height = float(root['height'])
    z = (wall.elevation + sill if index == 4 else
         wall.elevation + sill + height if index == 3 else
         wall.elevation + sill + height / 2)
    return (pt.x, pt.y, z)


def move_opening_handle(index, value):
    root = selected_opening()
    if root is None or root.parent is None or len(value) < 3:
        return
    wall = root.parent.archyar_wall
    a, b = Vector(wall.start), Vector(wall.end)
    direction = b - a
    length = direction.length
    if length < .1:
        return
    direction.normalize()
    position = (Vector((value[0], value[1])) - a).dot(direction)
    style = root['archyar_style']
    t = float(root['archyar_t'])
    width = float(root['width'])
    height = float(root['height'])
    sill = float(root['sill'])
    if index == 0:
        right = t * length + width / 2
        width = right - position
        t = (right + position) / (2 * length)
    elif index == 1:
        left = t * length - width / 2
        width = position - left
        t = (left + position) / (2 * length)
    elif index == 2:
        t = position / length
    elif index == 3:
        height = value[2] - wall.elevation - sill
    else:
        sill = value[2] - wall.elevation
    try:
        geometry.apply_opening(root, style, width, height, sill, t,
                               float(root.get('archyar_arch_rise', 0)),
                               bool(root.get('archyar_mirrored', False)),
                               float(root.get('archyar_open_fraction', 0)))
    except (ValueError, KeyError):
        return  # The host never releases an invalid / out-of-bounds opening.


class VIEW3D_GGT_archyar_opening_handles(bpy.types.GizmoGroup):
    bl_idname = 'VIEW3D_GGT_archyar_opening_handles'
    bl_label = 'Archyar Door / Window Handles'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        active = context.view_layer.objects.active if context.view_layer else None
        return bool(context.mode == 'OBJECT' and
                    getattr(context.scene, 'archyar_show_wall_handles', False) and
                    active and active.get('archyar_kind') == 'OPENING')

    def setup(self, context):
        self.handles = []
        for index in range(5):
            gizmo = self.gizmos.new('GIZMO_GT_move_3d')
            gizmo.target_set_handler('offset',
                get=lambda i=index: opening_handle_position(i),
                set=lambda value, i=index: move_opening_handle(i, value))
            gizmo.color = ((.18, .68, 1.0) if index in (0, 1) else
                           (1., .58, .12) if index == 2 else (.3, .95, .58))
            gizmo.alpha = .9
            gizmo.color_highlight = (1., 1., 1.)
            gizmo.scale_basis = .14
            gizmo.use_undo = True
            self.handles.append(gizmo)

    def draw_prepare(self, context):
        for gizmo in self.handles:
            gizmo.matrix_basis.identity()


CLASSES = (VIEW3D_GGT_archyar_wall_handles,
           VIEW3D_GGT_archyar_opening_handles)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

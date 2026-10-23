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
    return (point.x, point.y, props.elevation + min(props.height, 1.2))


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


CLASSES = (VIEW3D_GGT_archyar_wall_handles,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

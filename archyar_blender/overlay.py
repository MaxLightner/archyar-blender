"""Persistent metric wall-length labels in Blender's 3D viewport."""

import bpy
import blf
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from .geometry import length


_handler = None


def _draw_labels():
    context = bpy.context
    region = context.region
    area = context.area
    if region is None or area is None or area.type != 'VIEW_3D':
        return
    rv3d = context.space_data.region_3d
    font = 0
    blf.size(font, 15)
    blf.enable(font, blf.SHADOW)
    blf.shadow(font, 3, 0, 0, 0, 0.95)
    blf.color(font, 1.0, .78, .32, 1.0)
    for obj in context.visible_objects:
        if obj.get("archyar_kind") != "WALL":
            continue
        data = obj.archyar_wall
        if not data.show_length:
            continue
        a, b = data.start, data.end
        span = length(a, b)
        if span < .1:
            continue
        pos = Vector(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, data.height + .12))
        screen = location_3d_to_region_2d(region, rv3d, pos)
        if screen is None:
            continue
        text = "%.2f m" % span
        text_width, _ = blf.dimensions(font, text)
        blf.position(font, screen.x - text_width / 2, screen.y, 0)
        blf.draw(font, text)
    blf.disable(font, blf.SHADOW)


def register():
    global _handler
    if not bpy.app.background and _handler is None:
        _handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_labels, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handler
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
        _handler = None

"""Persistent wall labels and an Archyar construction grid in the viewport."""

import bpy
import blf
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from .geometry import length


_handler = None
_grid_handler = None


def _draw_construction_grid():
    scene = bpy.context.scene
    if scene is None or not getattr(scene, 'archyar_show_grid', False):
        return
    import math
    import gpu
    from gpu_extras.batch import batch_for_shader

    space = bpy.context.space_data
    if space is None or space.type != 'VIEW_3D':
        return
    center = space.region_3d.view_location
    elevation = scene.archyar_level_elevation
    step = scene.archyar_grid_step
    # Cover the camera target instead of clipping the grid at a fixed world origin.
    extent = min(35.0, max(12.0, space.region_3d.view_distance * 2.5))
    min_x = math.floor((center.x - extent) / step)
    max_x = math.ceil((center.x + extent) / step)
    min_y = math.floor((center.y - extent) / step)
    max_y = math.ceil((center.y + extent) / step)
    if (max_x - min_x) + (max_y - min_y) > 1200:
        return

    minor, major = [], []
    for i in range(min_x, max_x + 1):
        points = major if abs(i * step / 1.0 - round(i * step / 1.0)) < 1e-5 else minor
        xx = i * step
        points.extend(((xx, min_y * step, elevation), (xx, max_y * step, elevation)))
    for i in range(min_y, max_y + 1):
        points = major if abs(i * step / 1.0 - round(i * step / 1.0)) < 1e-5 else minor
        yy = i * step
        points.extend(((min_x * step, yy, elevation), (max_x * step, yy, elevation)))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.0)
    for verts, color in ((minor, (.40, .67, .80, .14)),
                         (major, (.40, .75, .88, .35))):
        if verts:
            batch = batch_for_shader(shader, 'LINES', {"pos": verts})
            shader.bind()
            shader.uniform_float('color', color)
            batch.draw(shader)
    gpu.state.blend_set('NONE')


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
        pos = Vector(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2,
                      data.elevation + data.height + .12))
        screen = location_3d_to_region_2d(region, rv3d, pos)
        if screen is None:
            continue
        text = "%.2f m" % span
        text_width, _ = blf.dimensions(font, text)
        blf.position(font, screen.x - text_width / 2, screen.y, 0)
        blf.draw(font, text)
    blf.disable(font, blf.SHADOW)


def register():
    global _handler, _grid_handler
    if not bpy.app.background and _handler is None:
        _handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_labels, (), 'WINDOW', 'POST_PIXEL')
    if not bpy.app.background and _grid_handler is None:
        _grid_handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_construction_grid, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _handler, _grid_handler
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
        _handler = None
    if _grid_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_grid_handler, 'WINDOW')
        _grid_handler = None

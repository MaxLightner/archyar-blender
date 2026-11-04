"""Architectural tools adapted from the MaxLightner/archyar-blender geometry.

The genuine Archyar draw_wall/place_opening operators are preferred whenever
the Archyar add-on is installed. A self-contained native mesh fallback is kept
so POYARA MaxLine also works when installed by itself.
"""

import math

import bpy
from bpy.props import EnumProperty, FloatProperty, PointerProperty
from bpy.types import Operator, PropertyGroup
from mathutils import Matrix, Vector

from . import _world_from_mouse


OPENINGS = {
    'fixed': 'Fixed Window',
    'sliding': 'Sliding Window',
    'hinged': 'Hinged Window',
    'arched': 'Arched Window',
    'door': 'Hinged Door',
    'sliding-door': 'Sliding Door',
}

_BOX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def _box_vertices(w, d, h):
    x, y, z = w / 2, d / 2, h / 2
    return [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
            (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]


def _material(name, rgb, alpha=1.0):
    mat = bpy.data.materials.get('POYARA Arch | ' + name)
    if mat is None:
        mat = bpy.data.materials.new('POYARA Arch | ' + name)
    mat.diffuse_color = (*rgb, alpha)
    return mat


def _box(context, name, parent, pos, dims, mat=None):
    mesh = bpy.data.meshes.new(name + ' Mesh')
    mesh.from_pydata(_box_vertices(*dims), [], _BOX_FACES)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
        obj['poyara_generated_part'] = True
    obj.location = pos
    if mat:
        mesh.materials.append(mat)
    return obj


def _select(context, obj):
    for other in context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _preview_lines(vertices, edges, color=(1.0, .60, .24, 1.0)):
    import gpu
    from gpu_extras.batch import batch_for_shader
    points = []
    for a, b in edges:
        points.extend((vertices[a], vertices[b]))
    if not points:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', color)
    gpu.state.line_width_set(2.5)
    batch_for_shader(shader, 'LINES', {'pos': points}).draw(shader)
    gpu.state.line_width_set(1.0)


_PREVIEW_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0),
                  (4, 5), (5, 6), (6, 7), (7, 4),
                  (0, 4), (1, 5), (2, 6), (3, 7))


def _wall_preview(operator, context):
    if operator._start is None or operator._current is None:
        return
    settings = context.scene.poyara_arch
    a, b = operator._start, operator._current
    dx, dy = b.x - a.x, b.y - a.y
    span = math.hypot(dx, dy)
    if span < .01:
        return
    nx = -dy * settings.wall_thickness / (2 * span)
    ny = dx * settings.wall_thickness / (2 * span)
    z = settings.elevation
    base = [(a.x+nx, a.y+ny, z), (b.x+nx, b.y+ny, z),
            (b.x-nx, b.y-ny, z), (a.x-nx, a.y-ny, z)]
    upper = [(x, y, z+settings.wall_height) for x, y, _ in base]
    _preview_lines(base+upper, _PREVIEW_EDGES)


def _opening_preview(operator, context):
    if operator._preview_x is None:
        return
    wall = operator._wall
    settings = context.scene.poyara_arch
    door = operator.style in {'door', 'sliding-door'}
    width = settings.door_width if door else settings.window_width
    height = settings.door_height if door else settings.window_height
    sill = 0 if door else settings.window_sill
    center_local = Vector((operator._preview_x, 0,
                           -wall['poyara_wall_height']/2 + sill + height/2))
    depth = wall['poyara_wall_thickness'] + .12
    box_vertices = _box_vertices(width, depth, height)
    world = [wall.matrix_world @ (center_local + Vector(v)) for v in box_vertices]
    _preview_lines(world, _PREVIEW_EDGES, color=(.20, .75, 1.0, 1.0))


def _create_wall(context, a, b, thickness, height, elevation):
    delta = Vector((b.x-a.x, b.y-a.y))
    length = delta.length
    if length < .1:
        raise ValueError('Wall length must be at least 10 cm')
    visual = _box(context, 'POYARA | Wall', None,
                  ((a.x+b.x)/2, (a.y+b.y)/2, elevation + height/2),
                  (length, thickness, height), _material('Plaster', (.77, .78, .75)))
    visual.rotation_euler.z = math.atan2(delta.y, delta.x)
    visual['poyara_kind'] = 'WALL'
    visual['poyara_wall_start'] = (a.x, a.y)
    visual['poyara_wall_end'] = (b.x, b.y)
    visual['poyara_wall_height'] = height
    visual['poyara_wall_thickness'] = thickness
    visual['poyara_wall_elevation'] = elevation
    _select(context, visual)
    return visual


def _opening_world_position(wall, x, sill, height):
    return wall.matrix_world @ Vector((x, 0, -wall['poyara_wall_height']/2 + sill + height/2))


def _make_opening(context, wall, x, style, width, height, sill):
    total = (Vector(wall['poyara_wall_end']) - Vector(wall['poyara_wall_start'])).length
    half = width / 2
    if total < width + .2 or abs(x) > total/2 - half - .1:
        raise ValueError('Opening does not fit: keep 10 cm from both wall ends')
    if sill < 0 or height + sill > wall['poyara_wall_height']:
        raise ValueError('Opening height exceeds the wall')
    cutter = _box(context, 'POYARA | Opening Cutter', wall,
                  (x, 0, -wall['poyara_wall_height']/2 + sill + height/2),
                  (width, wall['poyara_wall_thickness'] + .12, height))
    cutter['poyara_kind'] = 'OPENING_CUTTER'
    cutter['poyara_style'] = style
    cutter['poyara_open_width'] = width
    cutter['poyara_open_height'] = height
    cutter['poyara_open_sill'] = sill
    cutter.display_type = 'WIRE'
    cutter.hide_render = True
    mod = wall.modifiers.new('POYARA | ' + OPENINGS[style], 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    cutter.hide_set(True)

    frame_mat = _material('Frame', (.18, .23, .25))
    glass_mat = _material('Glass', (.35, .67, .74), .6)
    leaf_mat = _material('Door', (.54, .36, .24))
    base_z = -wall['poyara_wall_height']/2 + sill + height/2
    size = .065
    front = wall['poyara_wall_thickness']/2 + .025
    for side in (-1, 1):
        _box(context, 'Frame Jamb', wall,
             (x + side*(width/2 - size/2), front, base_z),
             (size, .065, height), frame_mat)
    _box(context, 'Frame Head', wall, (x, front, base_z+height/2-size/2),
         (width, .065, size), frame_mat)
    _box(context, 'Frame Sill', wall, (x, front, base_z-height/2+size/2),
         (width, .065, size), frame_mat)
    if style in {'door', 'sliding-door'}:
        _box(context, 'Door Leaf', wall, (x, -.025, base_z),
             (width-.12, .045, height-.10), leaf_mat)
    elif style == 'sliding':
        _box(context, 'Sliding Glass L', wall, (x-width/4, -.02, base_z),
             ((width-.14)/2, .014, height-.15), glass_mat)
        _box(context, 'Sliding Glass R', wall, (x+width/4, .02, base_z),
             ((width-.14)/2, .014, height-.15), glass_mat)
    else:
        _box(context, 'Window Glass', wall, (x, 0, base_z),
             (width-.12, .014, height-.13), glass_mat)
    _select(context, wall)
    return cutter


class POYARA_PG_arch_settings(PropertyGroup):
    wall_thickness: FloatProperty(name='Wall Thickness', default=.15, min=.04, max=1, unit='LENGTH')
    wall_height: FloatProperty(name='Wall Height', default=3.0, min=.3, max=12, unit='LENGTH')
    elevation: FloatProperty(name='Elevation', default=0, unit='LENGTH')
    window_width: FloatProperty(name='Window Width', default=1.2, min=.3, max=6, unit='LENGTH')
    window_height: FloatProperty(name='Window Height', default=1.4, min=.3, max=6, unit='LENGTH')
    window_sill: FloatProperty(name='Window Sill', default=.9, min=0, max=6, unit='LENGTH')
    door_width: FloatProperty(name='Door Width', default=.9, min=.4, max=4, unit='LENGTH')
    door_height: FloatProperty(name='Door Height', default=2.1, min=.5, max=6, unit='LENGTH')


def _original_archyar_available(name):
    try:
        return getattr(bpy.ops.archyar, name).poll()
    except (AttributeError, RuntimeError):
        return False


class POYARA_OT_arch_wall(Operator):
    bl_idname = 'poyara.arch_wall'
    bl_label = 'Draw Wall (Archyar)'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        settings = context.scene.poyara_arch
        if _original_archyar_available('draw_wall'):
            context.scene.archyar_thickness = settings.wall_thickness
            context.scene.archyar_height = settings.wall_height
            context.scene.archyar_level_elevation = settings.elevation
            return bpy.ops.archyar.draw_wall('INVOKE_DEFAULT')
        self._start = None
        self._current = None
        self._created = 0
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _wall_preview, (self, context), 'WINDOW', 'POST_VIEW'
        )
        context.workspace.status_text_set('POYARA WALL: click endpoints, repeat | Enter or Right Click finish | Esc cancel')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}
        if event.value == 'PRESS' and event.type in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'}:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            context.workspace.status_text_set(None)
            return {'FINISHED'} if self._created else {'CANCELLED'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'}:
            return {'PASS_THROUGH'}
        settings = context.scene.poyara_arch
        plane = Vector((0, 0, settings.elevation))
        world = _world_from_mouse(context, event.mouse_region_x, event.mouse_region_y,
                                  plane, Vector((0, 0, 1)))
        if world is None:
            return {'RUNNING_MODAL'}
        step = context.scene.poyara_maxline.snap_step
        world.x = round(world.x / step) * step
        world.y = round(world.y / step) * step
        self._current = world.copy()
        context.area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._start is None:
                self._start = world.copy()
            else:
                try:
                    _create_wall(context, self._start, world, settings.wall_thickness,
                                 settings.wall_height, settings.elevation)
                except ValueError as exc:
                    self.report({'WARNING'}, str(exc))
                    return {'RUNNING_MODAL'}
                self._start = world.copy()
                self._created += 1
        return {'RUNNING_MODAL'}


class POYARA_OT_arch_opening(Operator):
    bl_idname = 'poyara.arch_opening'
    bl_label = 'Place Door / Window (Archyar)'
    bl_options = {'REGISTER', 'UNDO'}
    style: EnumProperty(name='Opening', items=[(key, name, name) for key, name in OPENINGS.items()], default='fixed')

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        settings = context.scene.poyara_arch
        if _original_archyar_available('place_opening'):
            door = self.style in {'door', 'sliding-door'}
            context.scene.archyar_open_width = settings.door_width if door else settings.window_width
            context.scene.archyar_open_height = settings.door_height if door else settings.window_height
            context.scene.archyar_sill = 0 if door else settings.window_sill
            return bpy.ops.archyar.place_opening('INVOKE_DEFAULT', style=self.style)
        self._wall = context.active_object
        if self._wall is None or self._wall.get('poyara_kind') != 'WALL':
            self.report({'ERROR'}, 'Select a POYARA Wall first (or install Archyar for automatic wall picking)')
            return {'CANCELLED'}
        self._created = 0
        self._preview_x = None
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            _opening_preview, (self, context), 'WINDOW', 'POST_VIEW'
        )
        context.workspace.status_text_set('POYARA OPENING: click on selected wall to place | Right Click or Esc finish')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NDOF_MOTION'}:
            return {'PASS_THROUGH'}
        if event.value == 'PRESS' and event.type in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'}:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            context.workspace.status_text_set(None)
            return {'FINISHED'} if self._created else {'CANCELLED'}
        if event.type not in {'LEFTMOUSE', 'MOUSEMOVE'}:
            return {'PASS_THROUGH'}
        wall = self._wall
        normal = wall.matrix_world.to_3x3() @ Vector((0, 1, 0))
        hit = _world_from_mouse(context, event.mouse_region_x, event.mouse_region_y,
                                wall.matrix_world.translation, normal)
        if hit is None:
            return {'RUNNING_MODAL'}
        x = (wall.matrix_world.inverted_safe() @ hit).x
        self._preview_x = x
        context.area.tag_redraw()
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        settings = context.scene.poyara_arch
        door = self.style in {'door', 'sliding-door'}
        width = settings.door_width if door else settings.window_width
        height = settings.door_height if door else settings.window_height
        sill = 0 if door else settings.window_sill
        try:
            _make_opening(context, wall, x, self.style, width, height, sill)
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'RUNNING_MODAL'}
        self._created += 1
        return {'RUNNING_MODAL'}


ARCH_CLASSES = (POYARA_PG_arch_settings, POYARA_OT_arch_wall, POYARA_OT_arch_opening)


def register_properties():
    bpy.types.Scene.poyara_arch = PointerProperty(type=POYARA_PG_arch_settings)


def unregister_properties():
    del bpy.types.Scene.poyara_arch

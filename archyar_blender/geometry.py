"""Blender geometry constructors, metres, XY floor plane, Z up.

The Android domain uses X/Z for plan and Y for height; conversion will live in
the later import/export stage. This add-on stores semantic Archyar IDs now.
"""

import math
import uuid

import bpy
from mathutils import Vector

from .catalog import FURNITURE, OPENINGS


def material(name, rgb, alpha=1.0):
    key = "Archyar / " + name
    mat = bpy.data.materials.get(key)
    if mat is None:
        mat = bpy.data.materials.new(key)
    mat.diffuse_color = (*rgb, alpha)
    return mat


def mesh_object(name, vertices, faces, mat=None, parent=None):
    mesh = bpy.data.meshes.new(name + " Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    if mat is not None:
        mesh.materials.append(mat)
    return ob


_BOX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def box_vertices(w, d, h):
    x, y, z = w / 2, d / 2, h / 2
    return [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
            (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]


def box(name, parent, pos, dims, mat):
    obj = mesh_object(name, box_vertices(*dims), _BOX_FACES, mat, parent)
    obj.location = pos
    return obj


def cylinder(name, parent, pos, radius, height, mat, segments=16, top_radius=None):
    rt = radius if top_radius is None else top_radius
    n = max(8, segments)
    vertices = []
    for z, r in ((-height / 2, radius), (height / 2, rt)):
        vertices.extend((math.cos(2 * math.pi * i / n) * r,
                         math.sin(2 * math.pi * i / n) * r, z) for i in range(n))
    faces = [tuple(reversed(range(n))), tuple(range(n, n * 2))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    obj = mesh_object(name, vertices, faces, mat, parent)
    obj.location = pos
    return obj


def empty(name, location=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = .16
    obj.parent = parent
    obj.location = location
    return obj


def select(obj):
    if bpy.context.mode == 'OBJECT':
        for other in bpy.context.selected_objects:
            other.select_set(False)
        obj.hide_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj


def length(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def create_wall(a, b, thickness=.15, height=3.0, preset="wall"):
    if length(a, b) < .10:
        raise ValueError("Wall length must be at least 10 cm")
    obj = mesh_object("Archyar | Wall", box_vertices(1, 1, 1), _BOX_FACES,
                      material("Plaster", (.77, .78, .75)))
    obj["archyar_kind"] = "WALL"
    obj["archyar_preset"] = preset
    obj["archyar_id"] = str(uuid.uuid4())
    wall = obj.archyar_wall
    wall.start = a
    wall.end = b
    wall.thickness = thickness
    wall.height = height
    refresh_wall(obj)
    select(obj)
    return obj


def refresh_wall(obj):
    if obj is None or obj.get("archyar_kind") != "WALL":
        return
    wall = obj.archyar_wall
    a, b = wall.start, wall.end
    span = length(a, b)
    if span < .10:
        return
    mesh = obj.data
    mesh.clear_geometry()
    mesh.from_pydata(box_vertices(span, wall.thickness, wall.height), [], _BOX_FACES)
    mesh.update()
    obj.location = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, wall.height / 2)
    obj.rotation_euler = (0, 0, math.atan2(b[1] - a[1], b[0] - a[0]))
    for child in obj.children:
        if child.get("archyar_kind") != "OPENING":
            continue
        reposition_opening(child, obj)
        for cutter in child.children:
            if cutter.get("archyar_cutter"):
                replace_mesh(cutter, opening_profile(child, wall.thickness + .12))


def replace_mesh(obj, geometry):
    vertices, faces = geometry
    obj.data.clear_geometry()
    obj.data.from_pydata(vertices, [], faces)
    obj.data.update()


def opening_profile(root, depth):
    w, h = float(root["width"]), float(root["height"])
    style = root["archyar_style"]
    if style != "arched":
        return box_vertices(w, depth, h), _BOX_FACES
    rise = min(.25, h * .35)
    # Convex polygon in X/Z, with an approximately semicircular crown.
    n = 12
    profile = [(-w / 2, -h / 2), (w / 2, -h / 2),
               (w / 2, h / 2 - rise)]
    for i in range(1, n + 1):
        x = w / 2 - w * i / n
        crown = rise * math.sqrt(max(0.0, 1 - (2 * x / w) ** 2))
        profile.append((x, h / 2 - rise + crown))
    count = len(profile)
    verts = [(x, -depth / 2, z) for x, z in profile]
    verts += [(x, depth / 2, z) for x, z in profile]
    faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count)
              for i in range(count)]
    return verts, faces


def reposition_opening(root, wall):
    span = length(wall.archyar_wall.start, wall.archyar_wall.end)
    root.location = ((float(root["archyar_t"]) - .5) * span, 0,
                     float(root["sill"]) + float(root["height"]) / 2 - wall.archyar_wall.height / 2)


def create_opening(wall, t, style, width, height, sill):
    if wall is None or wall.get("archyar_kind") != "WALL":
        raise ValueError("Select an Archyar wall first")
    if style not in OPENINGS:
        raise ValueError("Unknown opening type")
    span = length(wall.archyar_wall.start, wall.archyar_wall.end)
    if (width < .3 or height < .3 or sill < 0 or width > span - .2
            or sill + height > wall.archyar_wall.height):
        raise ValueError("Opening dimensions do not fit this wall")
    if style in ("door", "sliding-door") and sill > .01:
        raise ValueError("Doors must start at floor level")
    margin = (width / 2 + .1) / span
    if not margin <= t <= 1 - margin:
        raise ValueError("Leave 10 cm between opening and wall end")
    for other in wall.children:
        if other.get("archyar_kind") == "OPENING":
            if abs((t - float(other["archyar_t"])) * span) < (width + float(other["width"])) / 2 + .05:
                raise ValueError("Openings cannot overlap")
    root = empty("Archyar | " + OPENINGS[style], parent=wall)
    root["archyar_kind"] = "OPENING"
    root["archyar_id"] = str(uuid.uuid4())
    root["archyar_style"] = style
    root["archyar_t"] = float(t)
    root["width"] = float(width)
    root["height"] = float(height)
    root["sill"] = float(sill)
    reposition_opening(root, wall)
    cutter = mesh_object("Archyar | Opening Cutter", *opening_profile(root, wall.archyar_wall.thickness + .12), parent=root)
    cutter["archyar_cutter"] = True
    cutter.display_type = 'WIRE'
    cutter.hide_render = True
    mod = wall.modifiers.new("Archyar | " + OPENINGS[style], 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    cutter.hide_set(True)
    _opening_visual(root, style, width, height, wall.archyar_wall.thickness)
    select(root)
    return root


def _opening_visual(root, style, w, h, depth):
    frame = material("Frame", (.18, .23, .25))
    glass = material("Glass blue", (.35, .67, .74), .5)
    wood = material("Door wood", (.54, .36, .24))
    thickness = .065
    face_y = depth / 2 + .024
    for s in (-1, 1):
        box("Frame jamb", root, (s * (w / 2 - thickness / 2), face_y, 0),
            (thickness, .065, h), frame)
    box("Frame sill", root, (0, face_y, -h / 2 + thickness / 2),
        (w, .065, thickness), frame)
    if style == "arched":
        rise = min(.25, h * .35)
        last = (-w / 2, h / 2 - rise)
        for i in range(1, 17):
            x = -w / 2 + w * i / 16
            z = h / 2 - rise + rise * math.sqrt(max(0, 1 - (2*x/w)**2))
            dx, dz = x - last[0], z - last[1]
            beam = box("Arched frame", root, ((x+last[0])/2, face_y, (z+last[1])/2),
                       (math.hypot(dx, dz) + .014, .075, .065), frame)
            beam.rotation_euler[1] = -math.atan2(dz, dx)
            last = x, z
    else:
        box("Frame lintel", root, (0, face_y, h / 2 - thickness / 2),
            (w, .065, thickness), frame)
    if style in ("door", "sliding-door"):
        box("Door leaf", root, (0, -.018, -.015), (w - .105, .042, h - .08), wood)
        cylinder("Door handle", root, (w * .36, face_y + .045, 0), .028, .025, frame)
    else:
        glass_h = h - (.32 if style == "arched" else .13)
        box("Glass", root, (0, 0, -.045 if style == "arched" else 0),
            (w - .12, .014, glass_h), glass)
        if style in ("sliding", "hinged"):
            box("Middle mullion", root, (0, face_y, 0), (.044, .075, glass_h), frame)


def add_structure(kind, cursor):
    stone = material("Concrete", (.62, .64, .64))
    timber = material("Timber", (.60, .46, .32))
    root = empty("Archyar | " + kind.title(), cursor)
    root["archyar_kind"] = kind.upper()
    root["archyar_id"] = str(uuid.uuid4())
    if kind in ("floor", "ceiling"):
        box(kind.title(), root, (0, 0, -.07 if kind == 'floor' else 3.0),
            (4.0, 4.0, .14), stone)
    elif kind == "column":
        box("Column", root, (0, 0, 1.5), (.4, .4, 3.0), stone)
    elif kind == "stairs":
        for i in range(10):
            box("Step", root, (-1.35 + .30 * i, 0, .09 * (i+1)),
                (.30, 1.0, .18 * (i+1)), stone)
    elif kind == "railing":
        for i in range(7):
            box("Post", root, (-1.5 + .5*i, 0, .45), (.045, .045, .9), timber)
        box("Handrail", root, (0, 0, .9), (3.04, .065, .07), timber)
    select(root)
    return root

"""Blender geometry constructors, metres, XY floor plane, Z up.

The Android domain uses X/Z for plan and Y for height; conversion will live in
the later import/export stage. This add-on stores semantic Archyar IDs now.
"""

import math
import uuid

import bpy
from mathutils import Vector

from .catalog import OPENINGS
from .constraints import (STAIR_FILLED, STAIR_OPEN, STAIR_TREAD_THICKNESS,
                          opening_position, require_stair)


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


def remove_tree(root):
    """Remove only objects owned by a transient or regenerated Archyar root."""
    for child in list(root.children):
        remove_tree(child)
    bpy.data.objects.remove(root, do_unlink=True)


def mark_preview(root, enabled):
    root["archyar_preview"] = enabled
    nested = [root]
    while nested:
        item = nested.pop()
        nested.extend(list(item.children))
        item.hide_select = enabled
        if item.type == 'MESH':
            item.display_type = 'WIRE' if enabled else 'TEXTURED'
            item.hide_render = enabled


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
    rise = float(root.get("archyar_arch_rise", min(.25, h * .35)))
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


def _validated_t(wall, t, style, width, height, sill, arch_rise, excluding=None):
    others = [(float(c["archyar_t"]), float(c["width"]))
              for c in wall.children if c is not excluding and c.get("archyar_kind") == "OPENING"]
    return opening_position(length(wall.archyar_wall.start, wall.archyar_wall.end),
                            wall.archyar_wall.height, width, height, sill,
                            style, arch_rise, t, others)


def create_opening(wall, t, style, width, height, sill, arch_rise=None):
    if wall is None or wall.get("archyar_kind") != "WALL":
        raise ValueError("Select an Archyar wall first")
    if style not in OPENINGS:
        raise ValueError("Unknown opening type")
    rise = min(.25, height * .35) if style == "arched" and arch_rise is None else (arch_rise or 0.0)
    t = _validated_t(wall, t, style, width, height, sill, rise)
    root = empty("Archyar | " + OPENINGS[style], parent=wall)
    root["archyar_kind"] = "OPENING"
    root["archyar_id"] = str(uuid.uuid4())
    root["archyar_style"] = style
    root["archyar_t"] = float(t)
    root["width"] = float(width)
    root["height"] = float(height)
    root["sill"] = float(sill)
    root["archyar_arch_rise"] = float(rise)
    root["archyar_mirrored"] = False
    root["archyar_open_fraction"] = 0.0
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
    _opening_visual(root, style, width, height, wall.archyar_wall.thickness, rise)
    select(root)
    return root


def preview_opening(wall, style, width, height, sill):
    root = empty("Archyar | Opening Preview", parent=wall)
    root["archyar_preview"] = True
    rise = min(.25, height * .35) if style == "arched" else 0
    root["archyar_style"] = style
    root["archyar_arch_rise"] = rise
    root["width"] = width
    root["height"] = height
    root["sill"] = sill
    root["archyar_t"] = .5
    reposition_opening(root, wall)
    _opening_visual(root, style, width, height, wall.archyar_wall.thickness, rise)
    mark_preview(root, True)
    return root


def apply_opening(root, style, width, height, sill, t, arch_rise, mirrored=False, open_fraction=0):
    """Validate all edited properties before mutating any visible model data."""
    wall = root.parent
    if root.get("archyar_kind") != "OPENING" or wall is None or wall.get("archyar_kind") != "WALL":
        raise ValueError("Select an Archyar opening hosted by a wall")
    if style not in OPENINGS or not 0 <= open_fraction <= 1:
        raise ValueError("Invalid opening type or open fraction")
    adjusted = _validated_t(wall, t, style, width, height, sill, arch_rise, root)
    root["archyar_style"] = style
    root["width"] = float(width)
    root["height"] = float(height)
    root["sill"] = float(sill)
    root["archyar_t"] = adjusted
    root["archyar_arch_rise"] = float(arch_rise)
    root["archyar_mirrored"] = bool(mirrored)
    root["archyar_open_fraction"] = float(open_fraction)
    root.name = "Archyar | " + OPENINGS[style]
    reposition_opening(root, wall)
    for child in list(root.children):
        if child.get("archyar_cutter"):
            replace_mesh(child, opening_profile(root, wall.archyar_wall.thickness + .12))
        else:
            remove_tree(child)
    _opening_visual(root, style, width, height, wall.archyar_wall.thickness, arch_rise)
    return root


def _opening_visual(root, style, w, h, depth, arch_rise=0):
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
        rise = arch_rise
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
        mirrored = bool(root.get("archyar_mirrored", False))
        fraction = float(root.get("archyar_open_fraction", 0))
        if style == 'door':
            sign = -1 if mirrored else 1
            pivot = empty("Door hinge", (sign * (-w/2 + .075), 0, 0), root)
            pivot.rotation_euler[2] = math.radians(105) * fraction * sign
            box("Door leaf", pivot, (sign*(w-.105)/2, -.018, -.015),
                (w-.105, .042, h-.08), wood)
            cylinder("Door handle", pivot, (sign*(w-.20), face_y+.045, 0),
                     .028, .025, frame)
        else:
            shift = fraction * (w-.12) * (-1 if mirrored else 1)
            box("Sliding door leaf", root, (shift, -.018, -.015), (w-.105, .042, h-.08), wood)
            cylinder("Door handle", root, (shift+w*.36, face_y+.045, 0), .028, .025, frame)
    else:
        glass_h = h - (.32 if style == "arched" else .13)
        fraction = float(root.get("archyar_open_fraction", 0))
        mirrored = bool(root.get("archyar_mirrored", False))
        if style == 'sliding':
            pane = (w - .14)/2
            displacement = fraction * pane * (-1 if mirrored else 1)
            box("Sliding pane", root, (-pane/2 + displacement, -.015, 0),
                (pane, .014, glass_h), glass)
            box("Fixed pane", root, (pane/2, .015, 0), (pane, .014, glass_h), glass)
            box("Middle mullion", root, (0, face_y, 0), (.044, .075, glass_h), frame)
        elif style == 'hinged':
            sign = -1 if mirrored else 1
            pivot = empty("Window hinge", (sign*(-w/2+.065), 0, 0), root)
            pivot.rotation_euler[2] = math.radians(80)*fraction*sign
            box("Hinged pane", pivot, (sign*(w-.13)/2, 0, 0),
                (w-.13, .014, glass_h), glass)
        else:
            box("Glass", root, (0, 0, -.045 if style == "arched" else 0),
                (w - .12, .014, glass_h), glass)


def rebuild_stair(root):
    """Open underside: 5 cm treads. Filled: solid riser blocks from floor."""
    settings = root.archyar_stair
    require_stair(settings.run, settings.width, settings.rise, settings.count)
    for child in list(root.children):
        if child.get("archyar_stair_piece"):
            remove_tree(child)
    mat = material("Concrete", (.62, .64, .64))
    step_run = settings.run / settings.count
    step_rise = settings.rise / settings.count
    for i in range(settings.count):
        top = (i+1) * step_rise
        if settings.filled:
            height = top
            center = top / 2
        else:
            height = min(STAIR_TREAD_THICKNESS, top)
            center = top - height/2
        step = box("Stair Tread %02d" % (i+1), root,
                   (-settings.run/2 + (i+.5)*step_run, 0, center),
                   (step_run, settings.width, height), mat)
        step["archyar_stair_piece"] = True
    root["archyar_stair_style"] = STAIR_FILLED if settings.filled else STAIR_OPEN
    root["archyar_stair_count"] = settings.count
    if root.get("archyar_preview"):
        mark_preview(root, True)


def add_structure(kind, cursor, preview=False):
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
        root["archyar_preview"] = bool(preview)
        rebuild_stair(root)
    elif kind == "railing":
        for i in range(7):
            box("Post", root, (-1.5 + .5*i, 0, .45), (.045, .045, .9), timber)
        box("Handrail", root, (0, 0, .9), (3.04, .065, .07), timber)
    if preview:
        mark_preview(root, True)
    else:
        select(root)
    return root

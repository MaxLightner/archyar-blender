"""Offline low-poly furniture matching Archyar's 22 catalog IDs and dimensions.

These recreate the procedural recipes of FurnitureMesh.java, NOT GLB copies.
All local object dimensions are metres; base origin sits on the floor.
"""

import math
import uuid

from .catalog import PALETTE, furniture
from .geometry import box, cylinder, empty, mark_preview, material, select


def make_furniture(index, location=(0, 0, 0), parent=None, preview=False):
    asset = furniture(index)
    root = empty("Archyar | " + asset.name, location, parent=parent)
    root["archyar_kind"] = "FURNITURE"
    root["archyar_id"] = str(uuid.uuid4())
    root["archyar_catalog_id"] = "chido-" + str(index)
    root["archyar_catalog_index"] = index
    root["archyar_category"] = asset.category
    root["archyar_width"] = asset.width
    root["archyar_height"] = asset.height
    root["archyar_depth"] = asset.depth
    root["archyar_wall_mounted"] = asset.wall_mounted
    fabric = material("Chido fabric", (.69, .69, .66))
    wood = material("Chido dark wood", (.43, .33, .25))
    light = material("Chido light wood", (.67, .55, .43))
    metal = material("Chido metal", (.32, .36, .39))
    linen = material("Chido linen", (.88, .84, .78))
    accent = material("Chido accent", (.54, .63, .59))
    shade = material("Chido shade", (.82, .72, .60))
    w, h, d = asset.width, asset.height, asset.depth
    template = asset.template

    def part(name, x, y, z, sx, sy, sz, mat):
        # Coordinates follow Blender XY floor, Z-up; XY are width/depth.
        return box(name, root, (x, y, z), (sx, sy, sz), mat)

    if template in ("sofa", "armchair"):
        count = 3 if template == "sofa" else 1
        part("Base", 0, 0, .29, w - .04, d - .04, .18, fabric)
        for side in (-1, 1):
            part("Arm", side * (w - .115) / 2, 0, .44, .115, d, .40, fabric)
        inside = w - .23
        for i in range(count):
            cx = -inside / 2 + (i + .5) * inside / count
            part("Seat cushion", cx, .08, .435, inside/count - .012, d - .185, .13, fabric)
            part("Back cushion", cx, -(d-.16)/2, (h + .48)/2,
                 inside/count - .012, .16, h-.48, fabric)
        for sx in (-1, 1):
            for sy in (-1, 1):
                part("Leg", sx*(w/2-.13), sy*(d/2-.12), .10, .065, .065, .20, wood)
    elif template in ("table", "side-table", "coffee-table", "desk", "dining-table"):
        top = .065
        part("Table top", 0, 0, h - top/2, w, d, top, light)
        for sx in (-1, 1):
            for sy in (-1, 1):
                part("Table leg", sx*(w/2-.11), sy*(d/2-.11), (h-top)/2,
                     .055, .055, h-top, wood)
        if template == "desk":
            part("Desk drawer", 0, -d*.1, h-.14, w*.54, d*.67, .12, shade)
    elif template == "chair":
        part("Seat", 0, 0, .48, w, d, .085, fabric)
        part("Back", 0, -d/2+.035, .71, w, .065, .49, fabric)
        for sx in (-1, 1):
            for sy in (-1, 1):
                part("Chair leg", sx*(w/2-.08), sy*(d/2-.08), .225,
                     .025, .025, .45, wood)
    elif template == "bed":
        part("Bed frame", 0, 0, .24, w, d, .21, light)
        part("Mattress", 0, .03, .47, w-.06, d-.11, .24, linen)
        part("Headboard", 0, -d/2+.06, .61, w, .13, .60, light)
        for side in (-1, 1):
            part("Pillow", side*w*.22, -d/2+.4, .65, w*.3, .36, .10, linen)
    elif template in ("floor-lamp", "desk-lamp", "tripod-lamp"):
        tripod = template == "tripod-lamp"
        shade_h = .24 if template == "desk-lamp" else (.42 if tripod else .39)
        radius = .15 if template == "desk-lamp" else (.24 if tripod else .20)
        cylinder("Lamp shade", root, (0, 0, h-shade_h*.55), radius, shade_h, shade,
                 top_radius=radius*.84)
        cylinder("Lamp stem", root, (0, 0, (h-shade_h)/2), .017, h-shade_h, metal)
        cylinder("Lamp base", root, (0, 0, .019), radius*.73, .038, wood)
        if tripod:
            for i in range(3):
                t = i * 2 * math.pi / 3
                part("Tripod leg", math.cos(t)*.11, math.sin(t)*.11,
                     (h-shade_h)/2, .045, .045, h-shade_h, wood)
    elif template == "rug":
        part("Rug", 0, 0, .008, w, d, .015, shade)
    elif template == "vase":
        for i in range(5):
            y0 = .025 + i*h*.075
            radius = w*.43-i*w*.055 if i < 3 else w*.18
            cylinder("Vase body", root, (0, 0, y0 + h*.04), radius, h*.12,
                     shade, top_radius=radius*.92)
        for i in range(4):
            a = i * math.pi * .58
            cylinder("Plant stem", root, (math.cos(a)*.05, math.sin(a)*.05, h*.75),
                     .006, h*.4, accent, 8, .004)
            # A simple leaf cluster rather than a texture-dependent mesh.
            part("Leaf", math.cos(a)*.1, math.sin(a)*.1, h*.85,
                 .065, .036, .13, accent)
    elif template == "pillow":
        part("Cushion", 0, 0, h*.50, w, d, h, fabric)
    elif template in ("art", "triptych"):
        part("Frame", 0, 0, h/2, w, d, h, wood)
        if template == "triptych":
            for i in (-1, 0, 1):
                part("Artwork", i*w*.32, d/2+.009, h/2,
                     w*.285, .012, h*.88, accent)
        else:
            part("Artwork", 0, d/2+.009, h/2, w*.92, .012, h*.90, accent)
    else:
        raise ValueError("No procedural template for " + template)

    # The source app offers four swatches; preserve them as a semantic ID.
    root["archyar_palette_index"] = 0
    root["archyar_palette_rgb"] = list(PALETTE[0])
    if preview:
        mark_preview(root, True)
    else:
        select(root)
    return root

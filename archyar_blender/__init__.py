"""Archyar for Blender — first installable modeling preview."""

bl_info = {
    "name": "Archyar — Architectural Modeling",
    "author": "POYARA / Archyar",
    "version": (0, 2, 0),
    "blender": (4, 3, 0),
    "location": "3D Viewport > Sidebar (N) > Archyar",
    "description": "Archyar catalog, metric walls, doors, windows, and Chido furniture",
    "category": "3D View",
}

from . import operators, overlay, updater


def register():
    operators.register()
    updater.register()
    overlay.register()


def unregister():
    overlay.unregister()
    updater.unregister()
    operators.unregister()


if __name__ == "__main__":
    register()

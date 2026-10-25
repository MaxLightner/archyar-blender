"""Archyar for Blender — first installable modeling preview."""

bl_info = {
    "name": "Archyar — Architectural Modeling",
    "author": "POYARA / Archyar",
    "version": (0, 9, 0),
    "blender": (4, 3, 0),
    "location": "3D Viewport > Sidebar (N) > Archyar",
    "description": "Archyar metric walls, openings, solid MEP ducts, wall luminaires and Chido furniture",
    "category": "3D View",
}

from . import floors, gizmos, interchange, live, mep, operators, overlay, selection, updater, view_modes


def register():
    operators.register()
    floors.register()
    mep.register()
    view_modes.register()
    updater.register()
    selection.register()
    gizmos.register()
    overlay.register()
    interchange.register()
    live.register()


def unregister():
    live.unregister()
    interchange.unregister()
    overlay.unregister()
    gizmos.unregister()
    selection.unregister()
    updater.unregister()
    view_modes.unregister()
    mep.unregister()
    floors.unregister()
    operators.unregister()


if __name__ == "__main__":
    register()

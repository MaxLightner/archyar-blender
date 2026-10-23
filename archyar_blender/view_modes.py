"""Separate top-orthographic floor-plan window; the 3D viewport stays intact."""

import bpy
from mathutils import Quaternion


_PLAN_AREAS = set()


def is_plan_view(area):
    return area is not None and area.as_pointer() in _PLAN_AREAS


def _find_plan_window():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D' and is_plan_view(area):
                return window, area
    return None, None


def _configure(window, area, level):
    space = area.spaces.active
    view = space.region_3d
    view.view_rotation = Quaternion((1, 0, 0, 0))
    view.view_perspective = 'ORTHO'
    view.view_location.z = level
    space.show_region_ui = False
    _PLAN_AREAS.add(area.as_pointer())
    area.tag_redraw()


class ARCHYAR_OT_plan_view(bpy.types.Operator):
    bl_idname = "archyar.plan_view"
    bl_label = "Open 2D Plan Window"
    bl_description = "Open a live plan in a separate window; preserve the existing 3D view"
    bl_options = {'REGISTER'}

    def execute(self, context):
        window, area = _find_plan_window()
        if window is not None:
            _configure(window, area, context.scene.archyar_level_elevation)
            return {'FINISHED'}
        source = context.area
        if source is None or source.type != 'VIEW_3D':
            return {'CANCELLED'}
        existing = {w.as_pointer() for w in context.window_manager.windows}
        try:
            result = bpy.ops.screen.area_dupli()
            if 'FINISHED' not in result and 'RUNNING_MODAL' not in result:
                return {'CANCELLED'}
        except RuntimeError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        # The window may be created on Blender's next event-loop tick. A short
        # timer resolves it without changing the operator's original viewport.
        level = context.scene.archyar_level_elevation
        attempts = [0]
        def configure_new_window():
            for new_window in bpy.context.window_manager.windows:
                if new_window.as_pointer() not in existing:
                    plan = next((a for a in new_window.screen.areas if a.type == 'VIEW_3D'), None)
                    if plan is not None:
                        _configure(new_window, plan, level)
                        return None
            attempts[0] += 1
            return .1 if attempts[0] < 15 else None
        bpy.app.timers.register(configure_new_window, first_interval=.05)
        return {'FINISHED'}


class ARCHYAR_OT_restore_view(bpy.types.Operator):
    bl_idname = "archyar.restore_view"
    bl_label = "Close 2D Plan Window"
    bl_description = "Close only the independent plan window"
    bl_options = {'REGISTER'}

    def execute(self, context):
        window, area = _find_plan_window()
        if window is None:
            return {'CANCELLED'}
        _PLAN_AREAS.discard(area.as_pointer())
        with context.temp_override(window=window, area=area):
            bpy.ops.wm.window_close()
        return {'FINISHED'}


CLASSES = (ARCHYAR_OT_plan_view, ARCHYAR_OT_restore_view)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    _PLAN_AREAS.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

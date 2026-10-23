"""A dedicated XY floor-plan representation using Blender's top orthographic view.

This toggles only the current 3D editor, so another editor can remain in 3D
for simultaneous work. The original perspective is restored on exit.
"""

import bpy


_SAVED_VIEW = {}


def is_plan_view(area):
    return area is not None and area.as_pointer() in _SAVED_VIEW


class ARCHYAR_OT_plan_view(bpy.types.Operator):
    bl_idname = "archyar.plan_view"
    bl_label = "2D Floor Plan"
    bl_description = "Switch this 3D viewport to a metric top orthographic floor plan"
    bl_options = {'REGISTER'}

    def execute(self, context):
        area = context.area
        if area is None or area.type != 'VIEW_3D':
            return {'CANCELLED'}
        if is_plan_view(area):
            return {'FINISHED'}
        space = context.space_data
        region = next((item for item in area.regions if item.type == 'WINDOW'), None)
        if region is None:
            self.report({'ERROR'}, "3D viewport region unavailable")
            return {'CANCELLED'}
        view = space.region_3d
        _SAVED_VIEW[area.as_pointer()] = (
            view.view_rotation.copy(), view.view_location.copy(),
            view.view_distance, view.view_perspective)
        try:
            with context.temp_override(area=area, region=region):
                bpy.ops.view3d.view_axis(type='TOP', align_active=False, relative=False)
        except RuntimeError as error:
            _SAVED_VIEW.pop(area.as_pointer(), None)
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        view.view_perspective = 'ORTHO'
        view.view_location.z = context.scene.archyar_level_elevation
        area.tag_redraw()
        return {'FINISHED'}


class ARCHYAR_OT_restore_view(bpy.types.Operator):
    bl_idname = "archyar.restore_view"
    bl_label = "Return to 3D"
    bl_description = "Return this viewport to its view before entering the Archyar plan"
    bl_options = {'REGISTER'}

    def execute(self, context):
        area = context.area
        if area is None or area.type != 'VIEW_3D':
            return {'CANCELLED'}
        saved = _SAVED_VIEW.pop(area.as_pointer(), None)
        if saved is None:
            self.report({'INFO'}, "This viewport is already in 3D mode")
            return {'FINISHED'}
        view = context.space_data.region_3d
        view.view_rotation, view.view_location = saved[0], saved[1]
        view.view_distance, view.view_perspective = saved[2], saved[3]
        area.tag_redraw()
        return {'FINISHED'}


CLASSES = (ARCHYAR_OT_plan_view, ARCHYAR_OT_restore_view)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    _SAVED_VIEW.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

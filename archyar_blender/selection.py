"""Promote Blender mesh picks to their semantic Archyar element controllers.

Render meshes remain ordinary Blender mesh datablocks internally, because
Blender needs vertices for display and Boolean cutting. They are *not* the
user-facing edit target: a click on a pane, jamb, tread or wall surface selects
the nearest Archyar controller instead.
"""

import bpy
from bpy.app.handlers import persistent

from . import geometry


_redirecting = False
_last_selected_controller = None


def _queue_popup(controller):
    scene = bpy.context.scene
    if scene is None or not getattr(scene, 'archyar_auto_popup', False):
        return
    if getattr(scene, 'archyar_active_tool', ''):
        return  # Never steal mouse focus from a live placement operator.
    expected = controller.as_pointer()

    def show():
        # Timers and depsgraph callbacks typically have no VIEW_3D context.
        # Find a real visible viewport instead of silently dropping the popup.
        for window in bpy.context.window_manager.windows:
            active = window.view_layer.objects.active
            if active is None or active.as_pointer() != expected:
                continue
            for area in window.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is None:
                    continue
                try:
                    with bpy.context.temp_override(window=window, area=area, region=region):
                        bpy.ops.archyar.element_popup('INVOKE_DEFAULT')
                except RuntimeError:
                    pass
                return None
        return None

    bpy.app.timers.register(show, first_interval=.06)


def semantic_root(obj):
    """Nearest ancestor with Archyar metadata, including the object itself."""
    while obj is not None:
        if obj.get("archyar_kind"):
            return obj
        obj = obj.parent
    return None


@persistent
def _sync_selection():
    global _redirecting, _last_selected_controller
    if _redirecting or bpy.app.background:
        return
    context = bpy.context
    view_layer = context.view_layer
    if view_layer is None or context.mode != 'OBJECT':
        return
    active = view_layer.objects.active
    controller = semantic_root(active)
    if controller is None or controller.hide_get():
        _last_selected_controller = None
        return
    if controller is active:
        if controller.as_pointer() != _last_selected_controller:
            _last_selected_controller = controller.as_pointer()
            if controller.get("archyar_kind") == "OPENING":
                from .operators import load_opening_settings
                load_opening_settings(controller)
            _queue_popup(controller)
        return
    _redirecting = True
    try:
        if active.select_get():
            active.select_set(False)
        controller.select_set(True)
        view_layer.objects.active = controller
        _last_selected_controller = controller.as_pointer()
        if controller.get("archyar_kind") == "OPENING":
            from .operators import load_opening_settings
            load_opening_settings(controller)
        _queue_popup(controller)
    finally:
        _redirecting = False


@persistent
def _promote_active(_scene, _depsgraph):
    _sync_selection()


def _watch_selection():
    # Selection-only events are not guaranteed to dirty Blender's depsgraph.
    # Poll cheaply so clicking a pane is also caught without a geometry update.
    _sync_selection()
    return .12


def _upgrade_after_load():
    try:
        geometry.migrate_legacy_walls()
    except Exception as error:
        print("Archyar: legacy wall migration failed:", error)
    return None


@persistent
def _on_scene_load(_unused):
    # Blender cannot safely create/link objects from within a load handler.
    if not bpy.app.timers.is_registered(_upgrade_after_load):
        bpy.app.timers.register(_upgrade_after_load, first_interval=.15)


def register():
    if _promote_active not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_promote_active)
    if _on_scene_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_scene_load)
    if not bpy.app.background:
        _upgrade_after_load()
        if not bpy.app.timers.is_registered(_watch_selection):
            bpy.app.timers.register(_watch_selection, first_interval=.12)


def unregister():
    if _promote_active in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_promote_active)
    if _on_scene_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_scene_load)
    if bpy.app.timers.is_registered(_upgrade_after_load):
        bpy.app.timers.unregister(_upgrade_after_load)
    if bpy.app.timers.is_registered(_watch_selection):
        bpy.app.timers.unregister(_watch_selection)

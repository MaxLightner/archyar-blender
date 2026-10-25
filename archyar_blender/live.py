"""Explicit opt-in, low-bandwidth Archyar project and viewport publisher.

Uses the Archyar live relay's HTTPS API. Only project JSON and project-frame
camera poses are sent: never the rendered viewport or AR camera video.

Blender API calls happen on its main thread. HTTP traffic is dispatched to a
single worker, with at most one pending model and one pending camera update.
"""
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256

import bpy
from bpy.props import StringProperty

from . import interchange
from .interchange_contract import blender_to_project_position, blender_to_project_quaternion

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Archyar-Live")
_SESSION = None
_CAMERA_PENDING = None
_MODEL_PENDING = None
_LAST_CAMERA_SENT = 0.0
_LAST_MODEL_CHECK = 0.0
_STATUS = "Not connected"


def _url(value):
    parsed = urllib.parse.urlparse(value.rstrip("/"))
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("Enter a valid HTTPS live relay base URL")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("A remote live relay requires HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Do not include credentials or query parameters in the server URL")
    return value.rstrip("/")


def _json_request(url, method, data=None, token=None):
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8") if data is not None else None
    headers = {"Accept": "application/json"}
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=encoded, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read(1_000_000).decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError("Relay HTTP %d: %s" % (err.code, body)) from None


def _fingerprint(project):
    """Ignore volatile update time and exporter metadata during scene hashing."""
    clone = dict(project)
    clone.pop("updatedAt", None)
    clone.pop("metadata", None)
    data = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(data.encode("utf-8")).hexdigest()


def _read_view_camera(scene, state):
    """Convert Blender viewport camera from Z-up into canonical Y-up metres."""
    for area in bpy.context.screen.areas if bpy.context.screen else ():
        if area.type != "VIEW_3D":
            continue
        space = area.spaces.active
        region = space.region_3d
        if region is None:
            continue
        matrix = region.view_matrix.inverted()
        pos = blender_to_project_position(tuple(matrix.translation))
        q = matrix.to_quaternion()
        rotation = blender_to_project_quaternion((q.x, q.y, q.z, q.w))
        state["sequence"] += 1
        width = max(1, area.width)
        height = max(1, area.height)
        return {
            "schemaVersion": 1,
            "projectId": state["projectId"],
            "sessionId": state["sessionId"],
            "floorId": state["floorId"],
            "sequence": state["sequence"],
            "timestampMs": max(0, int((time.monotonic() - state["started"]) * 1000)),
            "source": "blender-viewport",
            "position": pos,
            "rotation": rotation,
            "fovYDegrees": 60.0,
            "aspectRatio": width / height,
            "projectRevision": state["revision"],
        }
    return None


def _tick():
    global _MODEL_PENDING, _CAMERA_PENDING, _LAST_CAMERA_SENT, _LAST_MODEL_CHECK, _SESSION, _STATUS
    state = _SESSION
    if state is None:
        return None
    if bpy.context.scene is None or str(bpy.context.scene.get("archyar_project_id", "")) != state["projectId"]:
        _STATUS = "Project changed. Live publisher stopped."
        _SESSION = None
        return None
    try:
        if _MODEL_PENDING is not None and _MODEL_PENDING.done():
            try:
                answer = _MODEL_PENDING.result()
                state["revision"] = int(answer["revision"])
                state["lastFingerprint"] = state.pop("pendingFingerprint")
                _STATUS = "Model synchronized (r%d)" % state["revision"]
            except Exception as exc:
                _STATUS = "Model sync stopped: " + str(exc)
                _SESSION = None
                return None
            finally:
                _MODEL_PENDING = None
        if _CAMERA_PENDING is not None and _CAMERA_PENDING.done():
            try:
                _CAMERA_PENDING.result()
            except Exception as exc:
                _STATUS = "Camera stream error: " + str(exc)
            _CAMERA_PENDING = None
        now = time.monotonic()
        if now - _LAST_MODEL_CHECK >= 2.0 and _MODEL_PENDING is None:
            _LAST_MODEL_CHECK = now
            project = interchange.export_project(bpy.context.scene)
            fingerprint = _fingerprint(project)
            if fingerprint != state["lastFingerprint"]:
                state["pendingFingerprint"] = fingerprint
                _MODEL_PENDING = _EXECUTOR.submit(
                    _json_request,
                    state["base"] + "/api/sessions/" + state["sessionId"] + "/project",
                    "PUT", {"baseRevision": state["revision"], "project": project},
                    state["ownerToken"],
                )
        if now - _LAST_CAMERA_SENT >= .16 and _CAMERA_PENDING is None:
            pose = _read_view_camera(bpy.context.scene, state)
            if pose is not None:
                _LAST_CAMERA_SENT = now
                _CAMERA_PENDING = _EXECUTOR.submit(
                    _json_request,
                    state["base"] + "/api/sessions/" + state["sessionId"] + "/camera",
                    "POST", pose, state["ownerToken"],
                )
    except Exception as exc:
        _STATUS = "Live publisher stopped: " + str(exc)
        _SESSION = None
        return None
    return .12


class ARCHYAR_OT_live_create(bpy.types.Operator):
    bl_idname = "archyar.live_create"
    bl_label = "Start Live Viewing"
    bl_description = "Create a temporary relay session and share project geometry and Blender viewport pose"

    def execute(self, context):
        global _SESSION, _STATUS, _CAMERA_PENDING, _MODEL_PENDING, _LAST_CAMERA_SENT, _LAST_MODEL_CHECK
        if _SESSION is not None:
            self.report({'WARNING'}, "Stop the current session before starting another")
            return {'CANCELLED'}
        try:
            base = _url(context.scene.archyar_live_endpoint)
            project = interchange.export_project(context.scene)
            result = _json_request(base + "/api/sessions", "POST", {"project": project})
            session_id = result["sessionId"]
            owner_token = result["ownerToken"]
            viewer_url = result["viewerUrl"]
            if not (session_id and owner_token and viewer_url):
                raise ValueError("Relay returned an incomplete session")
            _SESSION = {
                "base": base, "projectId": project["projectId"],
                "floorId": project["originFloorId"],
                "sessionId": session_id,
                "ownerToken": owner_token,
                "viewerUrl": viewer_url,
                "lastFingerprint": _fingerprint(project),
                "revision": int(project["revision"]),
                "sequence": 0,
                "started": time.monotonic(),
            }
            _CAMERA_PENDING = None
            _MODEL_PENDING = None
            _LAST_CAMERA_SENT = 0.0
            _LAST_MODEL_CHECK = 0.0
            _STATUS = "Live session active"
            context.window_manager.clipboard = viewer_url
            if not bpy.app.timers.is_registered(_tick):
                bpy.app.timers.register(_tick, first_interval=.1)
            self.report({'INFO'}, "Viewer link copied to clipboard")
            return {'FINISHED'}
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            _STATUS = "Unable to start: " + str(exc)
            self.report({'ERROR'}, _STATUS)
            return {'CANCELLED'}


class ARCHYAR_OT_live_copy_link(bpy.types.Operator):
    bl_idname = "archyar.live_copy_link"
    bl_label = "Copy Viewer Link"

    def execute(self, context):
        if _SESSION is None:
            self.report({'WARNING'}, "No active live session")
            return {'CANCELLED'}
        context.window_manager.clipboard = _SESSION["viewerUrl"]
        self.report({'INFO'}, "Viewer URL copied")
        return {'FINISHED'}


class ARCHYAR_OT_live_stop(bpy.types.Operator):
    bl_idname = "archyar.live_stop"
    bl_label = "Stop Local Streaming"

    def execute(self, context):
        global _SESSION, _STATUS
        state = _SESSION
        _SESSION = None
        _STATUS = "Local sender stopped (relay session expires automatically)"
        # No token is saved in .blend. Clear module-held bearer session on stop.
        if state:
            _EXECUTOR.submit(
                _json_request,
                state["base"] + "/api/sessions/" + state["sessionId"] + "/project",
                "DELETE", None, state["ownerToken"],
            )
        return {'FINISHED'}


class VIEW3D_PT_archyar_live(bpy.types.Panel):
    bl_label = "Live Project Viewer"
    bl_idname = "VIEW3D_PT_archyar_live"
    bl_parent_id = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Project geometry + viewport camera, no video")
        layout.prop(context.scene, "archyar_live_endpoint", text="Relay")
        if _SESSION is None:
            layout.operator("archyar.live_create", text="Start Live Session", icon='PLAY')
        else:
            layout.operator("archyar.live_copy_link", text="Copy Viewer URL", icon='COPYDOWN')
            layout.operator("archyar.live_stop", text="Stop Streaming", icon='CANCEL')
        layout.label(text=_STATUS[:95])
        layout.label(text="Session tokens exist in memory only")


CLASSES = (ARCHYAR_OT_live_create, ARCHYAR_OT_live_copy_link,
           ARCHYAR_OT_live_stop, VIEW3D_PT_archyar_live)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.archyar_live_endpoint = StringProperty(
        name="Relay server",
        description="HTTPS Archyar live relay endpoint. HTTP only for localhost.",
        default="http://127.0.0.1:8787",
    )


def unregister():
    global _SESSION
    _SESSION = None
    del bpy.types.Scene.archyar_live_endpoint
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

"""File-based JSON import/export for the Archyar v1 shared project contract."""
import json
import uuid
from datetime import datetime, timezone

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Matrix, Quaternion, Vector

from . import floors, geometry, mep
from .catalog import WALL_PRESETS, furniture as get_furniture
from .furniture import make_furniture
from .interchange_contract import (
    blender_to_project_plan,
    blender_to_project_position,
    blender_to_project_quaternion,
    project_to_blender_plan,
    project_to_blender_position,
    project_to_blender_quaternion,
    validate_project,
)


_KIND_TO_CONTRACT = {
    "WALL": "wall",
    "OPENING": "opening",
    "FLOOR": "floor",
    "CEILING": "ceiling",
    "COLUMN": "column",
    "RAILING": "railing",
    "STAIRS": "stair",
    "FURNITURE": "furniture",
    "WALL_LIGHT": "wall_light",
}
_LAYER_BY_KIND = {
    "wall": "Walls",
    "opening": "Doors/Windows",
    "floor": "Floor",
    "ceiling": "Ceiling",
    "column": "Walls",
    "railing": "Walls",
    "stair": "Walls",
    "furniture": "Furniture",
    "pipe": "Plumbing",
    "duct": "HVAC",
    "conduit": "Lights",
    "wall_light": "Lights",
}


def _timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _semantic_objects(scene):
    return [
        obj for obj in scene.objects
        if obj.get("archyar_kind")
        and not obj.get("archyar_preview")
        and not obj.get("archyar_generated_part")
        and not obj.get("archyar_cutter")
    ]


def _find_object(scene, object_id):
    return next((obj for obj in scene.objects
                 if obj.get("archyar_id") == object_id
                 and obj.get("archyar_kind")
                 and not obj.get("archyar_preview")
                 and not obj.get("archyar_generated_part")
                 and not obj.get("archyar_cutter")), None)


def _floor_origin(scene):
    floors.ensure_floors(scene)
    if not scene.archyar_floors:
        raise ValueError("Initialize a building floor before exporting")
    for floor in scene.archyar_floors:
        if not _valid_uuid(floor.floor_id):
            floor.floor_id = str(uuid.uuid4())
    zero = [floor for floor in scene.archyar_floors if abs(float(floor.elevation)) <= 1e-6]
    origin_floor = zero[0] if zero else min(scene.archyar_floors, key=lambda item: item.elevation)
    return origin_floor, float(origin_floor.elevation)


def _nearest_floor(scene, elevation):
    return min(scene.archyar_floors, key=lambda floor: abs(float(floor.elevation) - elevation))


def _floor_id_for_object(root, scene, floors_by_id):
    current = root
    while current is not None:
        floor_id = current.get("archyar_floor_id")
        if floor_id in floors_by_id:
            return floor_id
        current = current.parent
    if root.get("archyar_kind") == "WALL":
        elevation = float(root.archyar_wall.elevation)
    else:
        elevation = float(root.matrix_world.translation.z)
    floor = _nearest_floor(scene, elevation)
    root["archyar_floor_id"] = floor.floor_id
    return floor.floor_id


def _object_transform(root, origin_elevation):
    world = root.matrix_world
    position = blender_to_project_position(tuple(world.translation), origin_elevation)
    world_quaternion = world.to_quaternion()
    rotation = blender_to_project_quaternion((
        world_quaternion.x, world_quaternion.y, world_quaternion.z, world_quaternion.w
    ))
    scale = tuple(world.to_scale())
    mapped_scale = [abs(scale[0]), abs(scale[2]), abs(scale[1])]
    transform = {"position": position, "rotation": rotation}
    if any(value < 1e-8 for value in mapped_scale):
        raise ValueError("Object has a zero scale and cannot be exported: " + root.name)
    if any(abs(value - 1.0) > 1e-6 for value in mapped_scale):
        transform["scale"] = mapped_scale
    return transform


def _export_object(root, scene, floors_by_id, origin_elevation):
    blender_kind = str(root.get("archyar_kind"))
    if blender_kind == "MEP_ROUTE":
        service = str(root.get("archyar_service", "DUCT")).upper()
        kind = {"DUCT": "duct", "PIPE": "pipe", "CONDUIT": "conduit"}.get(service)
        if kind is None:
            raise ValueError("Unsupported MEP service on " + root.name)
    else:
        kind = _KIND_TO_CONTRACT.get(blender_kind)
    if kind is None:
        raise ValueError("Cannot safely export unsupported Archyar object kind: " + blender_kind)

    object_id = str(root.get("archyar_id", ""))
    if not _valid_uuid(object_id):
        object_id = str(uuid.uuid4())
        root["archyar_id"] = object_id
    floor_id = _floor_id_for_object(root, scene, floors_by_id)
    params = {}
    host_id = None

    if kind == "wall":
        wall = root.archyar_wall
        params = {
            "start": blender_to_project_plan(wall.start),
            "end": blender_to_project_plan(wall.end),
            "baseElevation": float(wall.elevation) - origin_elevation,
            "height": float(wall.height),
            "thickness": float(wall.thickness),
            "style": str(root.get("archyar_preset", "wall")),
            "autoHeight": False,
        }
    elif kind == "opening":
        host = root.parent
        if host is None or host.get("archyar_kind") != "WALL":
            raise ValueError("Opening is missing its host wall: " + root.name)
        host_id = str(host.get("archyar_id", ""))
        params = {
            "style": str(root.get("archyar_style", "fixed")),
            "width": float(root["width"]),
            "height": float(root["height"]),
            "sill": float(root["sill"]),
            "hostT": float(root.get("archyar_t", 0.5)),
            "archRise": float(root.get("archyar_arch_rise", 0.0)),
            "openFraction": float(root.get("archyar_open_fraction", 0.0)),
            "mirrored": bool(root.get("archyar_mirrored", False)),
        }
    elif kind == "furniture":
        host = root.parent
        if host is not None and host.get("archyar_kind") == "WALL":
            host_id = str(host.get("archyar_id", ""))
        params = {
            "catalogId": str(root.get("archyar_catalog_id", "")),
            "width": float(root.get("archyar_width", 1.0)),
            "height": float(root.get("archyar_height", 1.0)),
            "depth": float(root.get("archyar_depth", 1.0)),
        }
    elif kind == "stair":
        stair = root.archyar_stair
        params = {
            "run": float(stair.run),
            "width": float(stair.width),
            "rise": float(stair.rise),
            "stairCount": int(stair.count),
            "style": str(root.get("archyar_stair_style", "stair-filled" if stair.filled else "stair-open")),
        }
    elif kind in {"pipe", "duct", "conduit"}:
        points = json.loads(root["archyar_points"])
        params = {
            "route": [blender_to_project_position(point, origin_elevation) for point in points],
            "width": float(root.get("archyar_width", 0.4)),
            "style": str(root.get("archyar_service", kind.upper())),
        }
        if kind == "duct":
            params["height"] = float(root.get("archyar_height", 0.25))
    elif kind == "wall_light":
        host = root.parent
        if host is None or host.get("archyar_kind") != "WALL":
            raise ValueError("Wall light is missing its host wall: " + root.name)
        host_id = str(host.get("archyar_id", ""))
        params = {
            "width": float(root.get("archyar_width", 1.2)),
            "height": float(root.get("archyar_height", 0.075)),
            "mountHeight": float(root.get("archyar_mount_height", 2.15)),
            "hostT": float(root.get("archyar_t", 0.5)),
            "side": -1 if int(root.get("archyar_side", 1)) < 0 else 1,
        }

    transform = None
    if kind not in {"wall", "opening", "pipe", "duct", "conduit", "wall_light"}:
        transform = _object_transform(root, origin_elevation)

    result = {
        "schemaVersion": 1,
        "id": object_id,
        "kind": kind,
        "floorId": floor_id,
        "hostId": host_id,
        "name": str(root.name)[:200],
        "layer": str(root.get("archyar_layer", _LAYER_BY_KIND.get(kind, "Walls"))),
        "locked": bool(root.get("archyar_locked", False)),
        "revision": int(root.get("archyar_revision", 0)),
        "source": "blender",
        "parameters": params,
    }
    if transform is not None:
        result["transform"] = transform
    return result


def export_project(scene):
    origin_floor, origin_elevation = _floor_origin(scene)
    floors_by_id = {floor.floor_id: floor for floor in scene.archyar_floors}
    floor_records = [
        {
            "id": floor.floor_id,
            "name": str(floor.name or "Floor"),
            "elevation": float(floor.elevation) - origin_elevation,
            "ceilingHeight": float(floor.ceiling),
            "visible": bool(floor.visible),
        }
        for floor in scene.archyar_floors
    ]
    project_id = str(scene.get("archyar_project_id", ""))
    if not _valid_uuid(project_id):
        project_id = str(uuid.uuid4())
        scene["archyar_project_id"] = project_id
    semantic_roots = _semantic_objects(scene)
    # Assign identities before serializing host references, independent of scene order.
    for root in semantic_roots:
        if not _valid_uuid(root.get("archyar_id")):
            root["archyar_id"] = str(uuid.uuid4())
    objects = [_export_object(root, scene, floors_by_id, origin_elevation)
               for root in semantic_roots]
    project = {
        "schemaVersion": 1,
        "projectId": project_id,
        "name": str(scene.get("archyar_project_name", scene.name or "Archyar Project"))[:200],
        "coordinateSystem": {
            "id": "archyar-project-v1",
            "units": "m",
            "handedness": "right",
            "upAxis": "Y",
            "groundPlane": "XZ",
            "origin": [0, 0, 0],
            "headingReference": "confirmed-floor-heading",
        },
        "originFloorId": origin_floor.floor_id,
        "revision": max(0, int(scene.get("archyar_project_revision", 0))),
        "floors": floor_records,
        "objects": objects,
        "metadata": {"exporter": "archyar-blender", "addonVersion": "0.8.0"},
        "updatedAt": _timestamp(),
    }
    validate_project(project)
    return project


def _delete_tree(root):
    if root.get("archyar_kind") == "OPENING" and root.parent is not None:
        host = root.parent
        visual = geometry.wall_visual(host)
        cutters = set()
        pending = list(root.children)
        while pending:
            child = pending.pop()
            pending.extend(list(child.children))
            if child.get("archyar_cutter"):
                cutters.add(child)
        if visual is not None:
            for modifier in list(visual.modifiers):
                if modifier.type == "BOOLEAN" and modifier.object in cutters:
                    visual.modifiers.remove(modifier)
    geometry.remove_tree(root)


def _delete_all_archyar(scene):
    roots = [
        obj for obj in list(scene.objects)
        if obj.get("archyar_kind")
        and not (obj.parent is not None and obj.parent.get("archyar_kind"))
    ]
    for root in roots:
        if root.name in bpy.data.objects:
            geometry.remove_tree(root)
    while len(scene.archyar_floors):
        scene.archyar_floors.remove(len(scene.archyar_floors) - 1)


def _set_common(root, obj_data, floor_record):
    root["archyar_id"] = obj_data["id"]
    root["archyar_floor_id"] = obj_data["floorId"]
    root["archyar_floor_elevation"] = float(floor_record["elevation"])
    root["archyar_floor_ceiling"] = float(floor_record["ceilingHeight"])
    root["archyar_revision"] = int(obj_data.get("revision", 0))
    root["archyar_layer"] = str(obj_data.get("layer", _LAYER_BY_KIND.get(obj_data["kind"], "Walls")))
    root["archyar_locked"] = bool(obj_data.get("locked", False))


def _set_world_transform(root, obj_data, default_position):
    transform = obj_data.get("transform") or {}
    position = transform.get("position", default_position)
    blender_position = project_to_blender_position(position)
    rotation = project_to_blender_quaternion(transform.get("rotation", [0, 0, 0, 1]))
    scale = transform.get("scale", [1, 1, 1])
    blender_scale = (float(scale[0]), float(scale[2]), float(scale[1]))
    matrix = (
        Matrix.Translation(Vector(blender_position))
        @ Quaternion((rotation[3], rotation[0], rotation[1], rotation[2])).to_matrix().to_4x4()
        @ Matrix.Diagonal((blender_scale[0], blender_scale[1], blender_scale[2], 1.0))
    )
    root.matrix_world = matrix


def _remove_existing(root):
    if root is not None and root.name in bpy.data.objects:
        _delete_tree(root)


def _import_wall(scene, obj_data, floor_record):
    params = obj_data["parameters"]
    start = project_to_blender_plan(params["start"])
    end = project_to_blender_plan(params["end"])
    elevation = float(params.get("baseElevation", 0.0))
    preset = params.get("style", "wall")
    if preset not in WALL_PRESETS:
        preset = "wall"
    root = _find_object(scene, obj_data["id"])
    if root is not None and root.get("archyar_kind") != "WALL":
        _remove_existing(root)
        root = None
    if root is None:
        root = geometry.create_wall(start, end, float(params["thickness"]),
                                    float(params["height"]), preset, elevation)
    else:
        wall = root.archyar_wall
        wall.start = start
        wall.end = end
        wall.thickness = float(params["thickness"])
        wall.height = float(params["height"])
        wall.elevation = elevation
        root["archyar_preset"] = preset
        geometry.refresh_wall(root)
    _set_common(root, obj_data, floor_record)
    root["archyar_preset"] = preset
    return root


def _import_opening(scene, obj_data, floor_record):
    params = obj_data["parameters"]
    wall = _find_object(scene, obj_data["hostId"])
    if wall is None or wall.get("archyar_kind") != "WALL":
        raise ValueError("Opening host wall was not imported: " + obj_data["hostId"])
    root = _find_object(scene, obj_data["id"])
    if root is not None and (root.get("archyar_kind") != "OPENING" or root.parent != wall):
        _remove_existing(root)
        root = None
    style = params["style"]
    width, height, sill = float(params["width"]), float(params["height"]), float(params["sill"])
    host_t = float(params["hostT"])
    arch_rise = float(params.get("archRise", 0))
    mirrored = bool(params.get("mirrored", False))
    open_fraction = float(params.get("openFraction", 0))
    if root is None:
        root = geometry.create_opening(wall, host_t, style, width, height, sill, arch_rise)
        root["archyar_id"] = obj_data["id"]
    # Rebuild newly created and existing openings alike, preserving mirror/open state.
    geometry.apply_opening(root, style, width, height, sill, host_t,
                           arch_rise, mirrored, open_fraction)
    root["archyar_mirrored"] = mirrored
    root["archyar_open_fraction"] = open_fraction
    _set_common(root, obj_data, floor_record)
    return root


def _import_furniture(scene, obj_data, floor_record):
    params = obj_data["parameters"]
    catalog_id = params["catalogId"]
    index = int(catalog_id.split("-", 1)[1])
    asset = get_furniture(index)
    host_id = obj_data.get("hostId")
    host = _find_object(scene, host_id) if host_id else None
    if host_id and (host is None or host.get("archyar_kind") != "WALL"):
        raise ValueError("Furniture host wall was not imported: " + str(host_id))
    root = _find_object(scene, obj_data["id"])
    if (root is not None and
            (root.get("archyar_kind") != "FURNITURE"
             or int(root.get("archyar_catalog_index", -1)) != index
             or root.parent != host)):
        _remove_existing(root)
        root = None
    default_position = [0, float(floor_record["elevation"]), 0]
    if root is None:
        root = make_furniture(index, location=(0, 0, 0), parent=host, preview=False)
    _set_world_transform(root, obj_data, default_position)
    root["archyar_catalog_id"] = catalog_id
    root["archyar_catalog_index"] = index
    root["archyar_width"] = float(params.get("width", asset.width))
    root["archyar_height"] = float(params.get("height", asset.height))
    root["archyar_depth"] = float(params.get("depth", asset.depth))
    _set_common(root, obj_data, floor_record)
    return root


def _import_structure(scene, obj_data, floor_record):
    kind = obj_data["kind"]
    blender_kind = {"floor": "FLOOR", "ceiling": "CEILING", "column": "COLUMN",
                    "railing": "RAILING", "stair": "STAIRS"}[kind]
    root = _find_object(scene, obj_data["id"])
    if root is not None and root.get("archyar_kind") != blender_kind:
        _remove_existing(root)
        root = None
    params = obj_data.get("parameters", {})
    default_position = [0, float(floor_record["elevation"]), 0]
    if root is None:
        blender_position = project_to_blender_position(
            (obj_data.get("transform") or {}).get("position", default_position)
        )
        root = geometry.add_structure(blender_kind.lower(), tuple(blender_position), preview=False)
    if kind == "stair":
        stair = root.archyar_stair
        stair.run = float(params["run"])
        stair.width = float(params["width"])
        stair.rise = float(params["rise"])
        stair.count = int(params["stairCount"])
        stair.filled = params.get("style", "stair-open") == "stair-filled"
        geometry.rebuild_stair(root)
        root["archyar_stair_style"] = "stair-filled" if stair.filled else "stair-open"
    _set_world_transform(root, obj_data, default_position)
    _set_common(root, obj_data, floor_record)
    return root


def _import_route(scene, obj_data, floor_record):
    kind = obj_data["kind"]
    params = obj_data["parameters"]
    service = {"pipe": "PIPE", "duct": "DUCT", "conduit": "CONDUIT"}[kind]
    points = [project_to_blender_position(point) for point in params["route"]]
    width = float(params["width"])
    height = float(params.get("height", width))
    root = _find_object(scene, obj_data["id"])
    if root is not None and (root.get("archyar_kind") != "MEP_ROUTE"
                             or root.get("archyar_service") != service):
        _remove_existing(root)
        root = None
    if root is None:
        root = mep.create_route(points, service, width, height)
    else:
        root["archyar_service"] = service
        root["archyar_width"] = width
        root["archyar_height"] = height
        root["archyar_points"] = json.dumps(points)
        mep.rebuild_route(root)
    _set_common(root, obj_data, floor_record)
    return root


def _import_wall_light(scene, obj_data, floor_record):
    params = obj_data["parameters"]
    wall = _find_object(scene, obj_data["hostId"])
    if wall is None or wall.get("archyar_kind") != "WALL":
        raise ValueError("Wall light host wall was not imported: " + obj_data["hostId"])
    root = _find_object(scene, obj_data["id"])
    if root is not None and (root.get("archyar_kind") != "WALL_LIGHT" or root.parent != wall):
        _remove_existing(root)
        root = None
    if root is None:
        root = mep.create_wall_light(wall)
    root["archyar_width"] = float(params["width"])
    root["archyar_height"] = float(params["height"])
    root["archyar_mount_height"] = float(params["mountHeight"])
    root["archyar_t"] = float(params["hostT"])
    root["archyar_side"] = int(params.get("side", 1))
    mep.rebuild_wall_light(root)
    _set_common(root, obj_data, floor_record)
    return root


def import_project(scene, project, replace_existing=False):
    validate_project(project)
    current_id = str(scene.get("archyar_project_id", ""))
    has_archyar_objects = bool(_semantic_objects(scene))
    if has_archyar_objects and not replace_existing and current_id != project["projectId"]:
        raise ValueError("Scene contains another Archyar project. Enable Replace Existing Archyar Model to continue.")
    if replace_existing:
        _delete_all_archyar(scene)

    floors_by_id = {floor.floor_id: floor for floor in scene.archyar_floors}
    for record in project["floors"]:
        floor = floors_by_id.get(record["id"])
        if floor is None:
            floor = scene.archyar_floors.add()
            floor.floor_id = record["id"]
            floors_by_id[record["id"]] = floor
        floor.name = record["name"]
        floor.elevation = float(record["elevation"])
        floor.ceiling = float(record["ceilingHeight"])
        floor.visible = bool(record["visible"])

    records_by_floor = {record["id"]: record for record in project["floors"]}
    rank = {"wall": 0, "floor": 1, "ceiling": 1, "column": 1, "railing": 1,
            "stair": 1, "furniture": 1, "pipe": 1, "duct": 1, "conduit": 1,
            "opening": 2, "wall_light": 2}
    ordered = sorted(project["objects"], key=lambda item: rank[item["kind"]])
    imported = 0
    for obj_data in ordered:
        floor_record = records_by_floor[obj_data["floorId"]]
        kind = obj_data["kind"]
        if kind == "wall":
            _import_wall(scene, obj_data, floor_record)
        elif kind == "opening":
            _import_opening(scene, obj_data, floor_record)
        elif kind == "furniture":
            _import_furniture(scene, obj_data, floor_record)
        elif kind in {"floor", "ceiling", "column", "railing", "stair"}:
            _import_structure(scene, obj_data, floor_record)
        elif kind in {"pipe", "duct", "conduit"}:
            _import_route(scene, obj_data, floor_record)
        elif kind == "wall_light":
            _import_wall_light(scene, obj_data, floor_record)
        imported += 1

    origin_index = next((index for index, floor in enumerate(scene.archyar_floors)
                         if floor.floor_id == project["originFloorId"]), 0)
    scene.archyar_floor_index = origin_index
    scene["archyar_project_id"] = project["projectId"]
    scene["archyar_project_name"] = project["name"]
    scene["archyar_project_revision"] = int(project["revision"])
    floors.refresh_visibility(scene)
    return imported


class ARCHYAR_OT_export_project(bpy.types.Operator, ExportHelper):
    bl_idname = "archyar.export_project_json"
    bl_label = "Export Shared Project JSON"
    bl_description = "Export semantic Archyar elements using the v1 interchange contract"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            project = export_project(context.scene)
            with open(self.filepath, "w", encoding="utf-8") as handle:
                json.dump(project, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.report({'ERROR'}, "Archyar export failed: " + str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, "Exported %d semantic objects" % len(project["objects"]))
        return {'FINISHED'}


class ARCHYAR_OT_import_project(bpy.types.Operator, ImportHelper):
    bl_idname = "archyar.import_project_json"
    bl_label = "Import Shared Project JSON"
    bl_description = "Merge a v1 Archyar project by stable ID or replace the current Archyar model"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})
    replace_existing: BoolProperty(
        name="Replace Existing Archyar Model",
        description="Delete existing Archyar elements before importing this project",
        default=False,
    )

    def execute(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8") as handle:
                project = json.load(handle)
            count = import_project(context.scene, project, self.replace_existing)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.report({'ERROR'}, "Archyar import failed: " + str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, "Imported %d semantic objects" % count)
        return {'FINISHED'}


class VIEW3D_PT_archyar_interchange(bpy.types.Panel):
    bl_label = "Project Interchange"
    bl_idname = "VIEW3D_PT_archyar_interchange"
    bl_parent_id = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("archyar.export_project_json", text="Export Project JSON", icon='EXPORT')
        layout.operator("archyar.import_project_json", text="Import Project JSON", icon='IMPORT')
        layout.label(text="v1: metric geometry and stable IDs")


CLASSES = (
    ARCHYAR_OT_export_project,
    ARCHYAR_OT_import_project,
    VIEW3D_PT_archyar_interchange,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

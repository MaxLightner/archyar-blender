"""Pure-Python rules for the Archyar v1 JSON interchange adapter."""
import math
import re
import uuid


CONTRACT_COORDINATE_SYSTEM = "archyar-project-v1"
CONTRACT_SCHEMA_VERSION = 1
SUPPORTED_KINDS = {
    "wall", "opening", "floor", "ceiling", "column", "railing", "stair",
    "pipe", "duct", "conduit", "furniture", "wall_light",
}
OPENING_STYLES = {"fixed", "sliding", "hinged", "arched", "door", "sliding-door"}
QUATERNION_BASIS = math.sqrt(0.5)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _vector(value, size, label):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError("%s must contain %d numbers" % (label, size))
    if not all(_finite(part) for part in value):
        raise ValueError("%s contains a non-finite number" % label)
    return tuple(float(part) for part in value)


def _uuid(value, label):
    if not isinstance(value, str):
        raise ValueError("%s must be a UUID string" % label)
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("%s must be a UUID string" % label)
    return value


def _positive(value, label):
    if not _finite(value) or float(value) <= 0:
        raise ValueError("%s must be a positive finite number" % label)
    return float(value)


def blender_to_project_position(point, origin_elevation=0.0):
    """Convert Blender Z-up world XYZ to canonical project XYZ, metres."""
    x, y, z = _vector(point, 3, "Blender position")
    if not _finite(origin_elevation):
        raise ValueError("Origin elevation must be finite")
    return [x, z - float(origin_elevation), -y]


def project_to_blender_position(point, origin_elevation=0.0):
    """Convert canonical project XYZ to Blender Z-up world XYZ, metres."""
    x, y, z = _vector(point, 3, "Project position")
    if not _finite(origin_elevation):
        raise ValueError("Origin elevation must be finite")
    return [x, -z, y + float(origin_elevation)]


def blender_to_project_plan(point):
    """Convert a Blender XY plan point to the project's XZ plan pair."""
    x, y = _vector(point, 2, "Blender plan point")
    return [x, -y]


def project_to_blender_plan(point):
    """Convert a project XZ plan pair to a Blender XY plan point."""
    x, z = _vector(point, 2, "Project plan point")
    return [x, -z]


def _quaternion_multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _normalize_quaternion(value):
    q = _vector(value, 4, "Quaternion")
    magnitude = math.sqrt(sum(component * component for component in q))
    if magnitude < 1e-12:
        raise ValueError("Quaternion magnitude is zero")
    return tuple(component / magnitude for component in q)


def blender_to_project_quaternion(value):
    """Conjugate Blender rotation by the fixed +90-degree X basis rotation."""
    q = _normalize_quaternion(value)
    basis = (QUATERNION_BASIS, 0.0, 0.0, QUATERNION_BASIS)
    inverse = (-QUATERNION_BASIS, 0.0, 0.0, QUATERNION_BASIS)
    return list(_normalize_quaternion(
        _quaternion_multiply(_quaternion_multiply(inverse, q), basis)
    ))


def project_to_blender_quaternion(value):
    """Inverse of blender_to_project_quaternion, quaternion order x,y,z,w."""
    q = _normalize_quaternion(value)
    basis = (QUATERNION_BASIS, 0.0, 0.0, QUATERNION_BASIS)
    inverse = (-QUATERNION_BASIS, 0.0, 0.0, QUATERNION_BASIS)
    return list(_normalize_quaternion(
        _quaternion_multiply(_quaternion_multiply(basis, q), inverse)
    ))


def _validate_transform(transform, label):
    if transform is None:
        return
    if not isinstance(transform, dict):
        raise ValueError("%s transform must be an object" % label)
    if "position" in transform:
        _vector(transform["position"], 3, label + " position")
    if "rotation" in transform:
        _normalize_quaternion(transform["rotation"])
    if "scale" in transform:
        scale = _vector(transform["scale"], 3, label + " scale")
        if any(part <= 0 for part in scale):
            raise ValueError("%s scale values must be positive" % label)


def validate_project(project):
    """Validate v1 structure, cross-references and geometry needed by Blender.

    Full JSON Schemas are checked in CI. This runtime validator avoids requiring
    third-party packages inside Blender's Python installation.
    """
    if not isinstance(project, dict):
        raise ValueError("Project document must be a JSON object")
    if project.get("schemaVersion") != CONTRACT_SCHEMA_VERSION:
        raise ValueError("Unsupported Archyar project schema version")
    _uuid(project.get("projectId"), "projectId")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("Project name is missing or too long")
    coord = project.get("coordinateSystem")
    expected = {
        "id": CONTRACT_COORDINATE_SYSTEM,
        "units": "m",
        "handedness": "right",
        "upAxis": "Y",
        "groundPlane": "XZ",
    }
    if not isinstance(coord, dict) or any(coord.get(key) != value for key, value in expected.items()):
        raise ValueError("Unsupported coordinate system; expected metric right-handed XZ/Y-up v1")
    if coord.get("origin") != [0, 0, 0]:
        raise ValueError("The canonical project origin must be [0, 0, 0]")
    _uuid(project.get("originFloorId"), "originFloorId")
    revision = project.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("Project revision must be a non-negative integer")

    floor_list = project.get("floors")
    if not isinstance(floor_list, list) or not floor_list:
        raise ValueError("Project must contain at least one floor")
    floors_by_id = {}
    for index, floor in enumerate(floor_list):
        if not isinstance(floor, dict):
            raise ValueError("Floor %d must be an object" % index)
        floor_id = _uuid(floor.get("id"), "floor id")
        if floor_id in floors_by_id:
            raise ValueError("Duplicate floor ID: " + floor_id)
        if not isinstance(floor.get("name"), str) or not floor["name"].strip():
            raise ValueError("Floor name is missing")
        elevation = floor.get("elevation")
        ceiling = floor.get("ceilingHeight")
        if not _finite(elevation):
            raise ValueError("Floor elevation must be finite")
        _positive(ceiling, "Floor ceilingHeight")
        if ceiling > 20:
            raise ValueError("Floor ceilingHeight exceeds 20 metres")
        if not isinstance(floor.get("visible"), bool):
            raise ValueError("Floor visibility must be boolean")
        floors_by_id[floor_id] = floor
    if project["originFloorId"] not in floors_by_id:
        raise ValueError("originFloorId does not refer to a project floor")
    if abs(float(floors_by_id[project["originFloorId"]]["elevation"])) > 1e-6:
        raise ValueError("Origin floor elevation must be zero")

    object_list = project.get("objects")
    if not isinstance(object_list, list):
        raise ValueError("Project objects must be an array")
    objects_by_id = {}
    for index, obj in enumerate(object_list):
        if not isinstance(obj, dict):
            raise ValueError("Object %d must be an object" % index)
        if obj.get("schemaVersion") != CONTRACT_SCHEMA_VERSION:
            raise ValueError("Object %d has an unsupported schema version" % index)
        object_id = _uuid(obj.get("id"), "object id")
        if object_id in objects_by_id:
            raise ValueError("Duplicate object ID: " + object_id)
        kind = obj.get("kind")
        if kind not in SUPPORTED_KINDS:
            raise ValueError("Blender interchange does not yet support object kind: %s" % kind)
        floor_id = _uuid(obj.get("floorId"), "object floorId")
        if floor_id not in floors_by_id:
            raise ValueError("Object references an unknown floor: " + floor_id)
        obj_revision = obj.get("revision", 0)
        if not isinstance(obj_revision, int) or isinstance(obj_revision, bool) or obj_revision < 0:
            raise ValueError("Object revision must be a non-negative integer")
        params = obj.get("parameters", {})
        if not isinstance(params, dict):
            raise ValueError("Object parameters must be an object")
        _validate_transform(obj.get("transform"), "Object " + object_id)
        objects_by_id[object_id] = obj

    for object_id, obj in objects_by_id.items():
        kind = obj["kind"]
        params = obj.get("parameters", {})
        host_id = obj.get("hostId")
        if host_id is not None:
            _uuid(host_id, "hostId")
            if host_id not in objects_by_id:
                raise ValueError("Object references an unknown host: " + host_id)
            if objects_by_id[host_id]["kind"] != "wall":
                raise ValueError("Hosted objects must reference a wall")
        if kind in {"opening", "wall_light"} and host_id is None:
            raise ValueError("%s requires a host wall" % kind)
        if kind in {"opening", "wall_light"} and objects_by_id[host_id]["floorId"] != obj["floorId"]:
            raise ValueError("Hosted object and host wall must belong to the same floor")

        if kind == "wall":
            start = _vector(params.get("start"), 2, "Wall start")
            end = _vector(params.get("end"), 2, "Wall end")
            span = math.hypot(end[0] - start[0], end[1] - start[1])
            if span < .10:
                raise ValueError("Wall length must be at least 0.10 m")
            thickness = _positive(params.get("thickness"), "Wall thickness")
            height = _positive(params.get("height"), "Wall height")
            if not .04 <= thickness <= 1.0 or not .3 <= height <= 12.0:
                raise ValueError("Wall thickness or height is outside Blender's supported bounds")
            if not _finite(params.get("baseElevation", 0)):
                raise ValueError("Wall base elevation must be finite")

        elif kind == "opening":
            host = objects_by_id[host_id]
            wall_params = host.get("parameters", {})
            start = _vector(wall_params.get("start"), 2, "Host wall start")
            end = _vector(wall_params.get("end"), 2, "Host wall end")
            span = math.hypot(end[0] - start[0], end[1] - start[1])
            wall_height = float(wall_params["height"])
            style = params.get("style")
            if style not in OPENING_STYLES:
                raise ValueError("Unknown opening style: %s" % style)
            width = _positive(params.get("width"), "Opening width")
            height = _positive(params.get("height"), "Opening height")
            sill = params.get("sill")
            host_t = params.get("hostT")
            if width < .3 or width > 6 or height < .3 or height > 6:
                raise ValueError("Opening width or height is outside supported bounds")
            if not _finite(sill) or sill < 0 or not _finite(host_t) or not 0 <= host_t <= 1:
                raise ValueError("Opening sill or hostT is invalid")
            if width > span - .20 or sill + height > wall_height:
                raise ValueError("Opening does not fit its host wall")
            margin = (width / 2 + .1) / span
            if not margin <= host_t <= 1 - margin:
                raise ValueError("Opening violates the host-wall end clearance")
            if style in {"door", "sliding-door"} and sill > .01:
                raise ValueError("Doors must have a zero sill")
            rise = params.get("archRise", 0)
            if style == "arched":
                if not _finite(rise) or not .05 <= rise <= height * .65:
                    raise ValueError("Arched opening has an invalid archRise")
            elif rise not in (0, 0.0, None):
                raise ValueError("Only arched openings may have a positive archRise")

        elif kind == "stair":
            run = _positive(params.get("run"), "Stair run")
            width = _positive(params.get("width"), "Stair width")
            rise = _positive(params.get("rise"), "Stair rise")
            count = params.get("stairCount")
            if (run < .5 or not .5 <= width <= 5 or not .15 <= rise <= 9
                    or not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 50
                    or not .10 <= rise / count <= .22 or run / count < .20):
                raise ValueError("Stair dimensions violate Archyar's stair constraints")
            if params.get("style", "stair-open") not in {"stair-open", "stair-filled"}:
                raise ValueError("Unknown stair style")

        elif kind == "furniture":
            catalog_id = params.get("catalogId")
            match = re.fullmatch(r"chido-(\d+)", catalog_id or "")
            if not match or not 0 <= int(match.group(1)) <= 21:
                raise ValueError("Furniture must use a supported chido-0 through chido-21 catalogId")
            for field in ("width", "height", "depth"):
                _positive(params.get(field), "Furniture " + field)

        elif kind in {"pipe", "duct", "conduit"}:
            route = params.get("route")
            if not isinstance(route, list) or len(route) < 2 or len(route) > 128:
                raise ValueError("MEP route must contain 2–128 points")
            points = [_vector(point, 3, "MEP route point") for point in route]
            for a, b in zip(points, points[1:]):
                if math.hypot(b[0] - a[0], b[2] - a[2]) < .05:
                    raise ValueError("MEP route segment must be at least 5 cm horizontally")
            for a, b, c in zip(points, points[1:], points[2:]):
                first = (b[0] - a[0], b[2] - a[2])
                second = (c[0] - b[0], c[2] - b[2])
                first_len = math.hypot(*first)
                second_len = math.hypot(*second)
                dot = (first[0] * second[0] + first[1] * second[1]) / (first_len * second_len)
                if dot < -0.999:
                    raise ValueError("MEP route cannot reverse direction by 180 degrees")
            width = _positive(params.get("width"), "MEP route width")
            if width < .008 or width > 3:
                raise ValueError("MEP route width is outside supported bounds")
            if kind == "duct":
                depth = _positive(params.get("height"), "Duct section height")
                if not .04 <= depth <= 3:
                    raise ValueError("Duct section height is outside supported bounds")

        elif kind == "wall_light":
            host = objects_by_id[host_id]
            host_params = host.get("parameters", {})
            start = _vector(host_params.get("start"), 2, "Host wall start")
            end = _vector(host_params.get("end"), 2, "Host wall end")
            span = math.hypot(end[0] - start[0], end[1] - start[1])
            host_height = float(host_params["height"])
            width = _positive(params.get("width"), "Wall light width")
            height = _positive(params.get("height"), "Wall light height")
            mount = params.get("mountHeight")
            host_t = params.get("hostT")
            side = params.get("side", 1)
            if not .15 <= width <= span - .10 or not .02 <= height <= .4:
                raise ValueError("Wall light does not fit its host wall")
            if not _finite(mount) or not height / 2 <= mount <= host_height - height / 2:
                raise ValueError("Wall light mountHeight is invalid")
            if not _finite(host_t) or not width / (2 * span) + .01 <= host_t <= 1 - width / (2 * span) - .01:
                raise ValueError("Wall light hostT is invalid")
            if side not in (-1, 1):
                raise ValueError("Wall light side must be -1 or 1")

    openings_by_wall = {}
    for obj in object_list:
        if obj["kind"] == "opening":
            openings_by_wall.setdefault(obj["hostId"], []).append(obj)
    for host_id, openings in openings_by_wall.items():
        host_params = objects_by_id[host_id]["parameters"]
        start, end = host_params["start"], host_params["end"]
        span = math.hypot(end[0] - start[0], end[1] - start[1])
        ordered = sorted(openings, key=lambda item: item["parameters"]["hostT"])
        for previous, current in zip(ordered, ordered[1:]):
            a, b = previous["parameters"], current["parameters"]
            distance = abs(a["hostT"] - b["hostT"]) * span
            if distance < (a["width"] + b["width"]) / 2 + .05:
                raise ValueError("Hosted openings overlap or lack 5 cm clearance")

    return project

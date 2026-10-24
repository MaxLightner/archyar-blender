"""Validation tests for the cross-client Archyar project contract."""
import json
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "v1"
SCHEMA_NAMES = (
    "project.schema.json",
    "object.schema.json",
    "camera-pose.schema.json",
    "event.schema.json",
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


SCHEMAS = {name: load_json(CONTRACT_DIR / name) for name in SCHEMA_NAMES}
SCHEMA_STORE = {
    (CONTRACT_DIR / name).resolve().as_uri(): schema
    for name, schema in SCHEMAS.items()
}


def validator_for(name):
    schema = SCHEMAS[name]
    resolver = RefResolver(
        base_uri=CONTRACT_DIR.resolve().as_uri() + "/",
        referrer=schema,
        store=SCHEMA_STORE,
    )
    return Draft202012Validator(
        schema, resolver=resolver, format_checker=FormatChecker()
    )


class SharedProjectContractTests(unittest.TestCase):
    def test_all_schemas_are_valid_json_schema(self):
        for name, schema in SCHEMAS.items():
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(schema)

    def test_minimal_project_fixture_validates_and_references_resolve(self):
        project = load_json(CONTRACT_DIR / "examples" / "minimal-project.json")
        validator_for("project.schema.json").validate(project)

        floor_ids = {floor["id"] for floor in project["floors"]}
        object_ids = {obj["id"] for obj in project["objects"]}
        self.assertIn(project["originFloorId"], floor_ids)
        self.assertEqual(len(floor_ids), len(project["floors"]))
        self.assertEqual(len(object_ids), len(project["objects"]))
        for obj in project["objects"]:
            self.assertIn(obj["floorId"], floor_ids)
            if obj.get("hostId") is not None:
                self.assertIn(obj["hostId"], object_ids)
        wall = next(obj for obj in project["objects"] if obj["kind"] == "wall")
        opening = next(obj for obj in project["objects"] if obj["kind"] == "opening")
        self.assertEqual(opening["hostId"], wall["id"])
        self.assertEqual(project["coordinateSystem"]["origin"], [0, 0, 0])
        self.assertEqual(project["floors"][0]["elevation"], 0)

    def test_camera_pose_fixture_validates(self):
        pose = load_json(CONTRACT_DIR / "examples" / "camera-pose.json")
        validator_for("camera-pose.schema.json").validate(pose)
        self.assertEqual(pose["position"], [2, 1.6, 1.5])

    def test_object_change_event_fixture_validates(self):
        event = load_json(CONTRACT_DIR / "examples" / "object-upsert-event.json")
        validator_for("event.schema.json").validate(event)
        validator_for("object.schema.json").validate(event["payload"]["object"])
        self.assertEqual(event["eventType"], "object.upsert")
        self.assertEqual(event["baseRevision"], 0)

    def test_blender_axis_mapping_round_trips(self):
        def project_to_blender(point):
            x, y, z = point
            return (x, -z, y)

        def blender_to_project(point):
            x, y, z = point
            return (x, z, -y)

        original = (1.25, 2.5, -3.75)
        blender = project_to_blender(original)
        restored = blender_to_project(blender)
        for actual, expected in zip(restored, original):
            self.assertTrue(math.isclose(actual, expected, abs_tol=1e-9))
        self.assertEqual(blender, (1.25, 3.75, 2.5))

    def test_bad_host_reference_is_caught_by_fixture_invariant(self):
        project = load_json(CONTRACT_DIR / "examples" / "minimal-project.json")
        object_ids = {obj["id"] for obj in project["objects"]}
        opening = next(obj for obj in project["objects"] if obj["kind"] == "opening")
        opening["hostId"] = "550e8400-e29b-41d4-a716-446655440099"
        self.assertNotIn(opening["hostId"], object_ids)


if __name__ == "__main__":
    unittest.main()

"""Pure-Python tests for the shared Blender interchange adapter."""
import importlib.util
import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "archyar_blender" / "interchange_contract.py"
SPEC = importlib.util.spec_from_file_location("interchange_contract", MODULE_PATH)
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)
FIXTURE = json.loads((ROOT / "contracts" / "v1" / "examples" / "minimal-project.json")
                     .read_text(encoding="utf-8"))


class CoordinateAdapterTests(unittest.TestCase):
    def test_position_round_trip_and_origin_offset(self):
        blender = (1.25, -3.75, 5.5)
        project = CONTRACT.blender_to_project_position(blender, origin_elevation=2.0)
        self.assertEqual(project, [1.25, 3.5, 3.75])
        restored = CONTRACT.project_to_blender_position(project, origin_elevation=2.0)
        for actual, expected in zip(restored, blender):
            self.assertAlmostEqual(actual, expected)

    def test_plan_round_trip(self):
        project = [2.25, -4.5]
        blender = CONTRACT.project_to_blender_plan(project)
        self.assertEqual(blender, [2.25, 4.5])
        self.assertEqual(CONTRACT.blender_to_project_plan(blender), project)

    def test_quaternion_round_trip(self):
        original = [0.0, 0.0, math.sin(.31), math.cos(.31)]
        blender = CONTRACT.project_to_blender_quaternion(original)
        restored = CONTRACT.blender_to_project_quaternion(blender)
        for actual, expected in zip(restored, original):
            self.assertAlmostEqual(actual, expected, places=9)

    def test_identity_quaternion_stays_identity(self):
        result = CONTRACT.blender_to_project_quaternion([0, 0, 0, 1])
        for actual, expected in zip(result, [0, 0, 0, 1]):
            self.assertAlmostEqual(actual, expected, places=9)


class ProjectValidationTests(unittest.TestCase):
    def test_minimal_contract_fixture_validates(self):
        self.assertIs(CONTRACT.validate_project(FIXTURE), FIXTURE)

    def test_unknown_host_is_rejected(self):
        project = json.loads(json.dumps(FIXTURE))
        opening = next(obj for obj in project["objects"] if obj["kind"] == "opening")
        opening["hostId"] = "550e8400-e29b-41d4-a716-446655440099"
        with self.assertRaisesRegex(ValueError, "unknown host"):
            CONTRACT.validate_project(project)

    def test_opening_clearance_is_checked_before_import(self):
        project = json.loads(json.dumps(FIXTURE))
        opening = next(obj for obj in project["objects"] if obj["kind"] == "opening")
        opening["parameters"]["hostT"] = .01
        with self.assertRaisesRegex(ValueError, "end clearance"):
            CONTRACT.validate_project(project)

    def test_unsupported_kind_is_not_silently_dropped(self):
        project = json.loads(json.dumps(FIXTURE))
        project["objects"][0]["kind"] = "custom"
        with self.assertRaisesRegex(ValueError, "does not yet support"):
            CONTRACT.validate_project(project)

    def test_duplicate_object_ids_are_rejected(self):
        project = json.loads(json.dumps(FIXTURE))
        project["objects"][1]["id"] = project["objects"][0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate object ID"):
            CONTRACT.validate_project(project)

    def test_addon_exposes_file_dialog_operators(self):
        source = (ROOT / "archyar_blender" / "interchange.py").read_text(encoding="utf-8")
        self.assertIn("ARCHYAR_OT_export_project", source)
        self.assertIn("ARCHYAR_OT_import_project", source)
        self.assertIn("Replace Existing Archyar Model", source)
        self.assertIn("def export_project(scene):", source)
        self.assertIn("def import_project(scene, project, replace_existing=False):", source)


if __name__ == "__main__":
    unittest.main()

"""Static floor-lifecycle contracts; Blender runtime smoke testing is still required."""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FloorContracts(unittest.TestCase):
    def test_floor_module_parses_and_registers(self):
        code = (ROOT / "archyar_blender" / "floors.py").read_text(encoding="utf-8")
        ast.parse(code)
        for name in ("archyar_floors", "archyar_floor_index", "archyar_solo_floor",
                     "archyar_floor_id", "archyar_floor_elevation",
                     "ARCHYAR_OT_add_floor", "ARCHYAR_OT_remove_floor",
                     "VIEW3D_PT_archyar_floors"):
            self.assertIn(name, code)

    def test_a_floor_with_elements_cannot_be_deleted(self):
        code = (ROOT / "archyar_blender" / "floors.py").read_text(encoding="utf-8")
        self.assertIn('if any(root.get("archyar_floor_id") == floor.floor_id', code)
        self.assertIn("Floor contains elements", code)

    def test_geometry_tags_only_unparented_archyar_roots(self):
        code = (ROOT / "archyar_blender" / "geometry.py").read_text(encoding="utf-8")
        self.assertIn('if parent is None and name.startswith("Archyar |"):', code)
        self.assertIn("floors.tag_root(obj)", code)


if __name__ == "__main__":
    unittest.main()

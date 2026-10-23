"""Structural and pure-function checks for the v0.4 controller architecture.

These tests deliberately run without Blender. A real viewport smoke test is
still required to validate Blender's depsgraph notifications and gizmo drag.
"""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "archyar_blender"


def load_pure_function(filename, name):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[function], type_ignores=[])
    code = compile(ast.fix_missing_locations(module), filename, "exec")
    globals_dict = {}
    exec(code, globals_dict)
    return globals_dict[name]


class FakeObject:
    def __init__(self, kind=None, parent=None):
        self.kind = kind
        self.parent = parent

    def get(self, key):
        return self.kind if key == "archyar_kind" else None


class SemanticControllers(unittest.TestCase):
    def test_mesh_click_selects_nearest_semantic_ancestor(self):
        pick = load_pure_function("selection.py", "semantic_root")
        wall = FakeObject("WALL")
        opening = FakeObject("OPENING", wall)
        glass = FakeObject(parent=FakeObject(parent=opening))
        self.assertIs(pick(glass), opening)
        self.assertIs(pick(FakeObject(parent=wall)), wall)
        self.assertIsNone(pick(FakeObject()))

    def test_modules_are_valid_python(self):
        for name in ("selection.py", "gizmos.py", "view_modes.py"):
            with self.subTest(name=name):
                compile((ROOT / name).read_text(encoding="utf-8"), name, "exec")

    def test_wall_is_an_empty_controller_with_child_mesh(self):
        source = (ROOT / "geometry.py").read_text(encoding="utf-8")
        self.assertIn('obj = empty("Archyar | Wall")', source)
        self.assertIn('visual["archyar_wall_visual"] = True', source)
        self.assertIn('def migrate_legacy_walls():', source)
        self.assertIn('wall_visual(wall).modifiers.new', source)

    def test_handles_are_available_without_starting_modal_operator(self):
        source = (ROOT / "gizmos.py").read_text(encoding="utf-8")
        self.assertIn('bl_options = {\'3D\', \'PERSISTENT\'}', source)
        self.assertIn('self.gizmos.new("GIZMO_GT_move_3d")', source)
        self.assertIn('wall_connection_changes(wall, new_a, new_b)', source)

    def test_plan_opens_separate_live_window_without_rotating_main_view(self):
        source = (ROOT / "view_modes.py").read_text(encoding="utf-8")
        self.assertIn("bpy.ops.screen.area_dupli()", source)
        self.assertIn("view.view_rotation = Quaternion((1, 0, 0, 0))", source)
        self.assertIn("view.view_perspective = 'ORTHO'", source)
        self.assertNotIn('view3d.view_axis', source)
        self.assertIn('bpy.ops.wm.window_close()', source)

    def test_openings_remain_host_bound_and_can_keyframe(self):
        geometry = (ROOT / 'geometry.py').read_text(encoding='utf-8')
        gizmos = (ROOT / 'gizmos.py').read_text(encoding='utf-8')
        controls = (ROOT / 'operators.py').read_text(encoding='utf-8')
        self.assertIn('root.lock_location = (True, True, True)', geometry)
        self.assertIn('def move_opening_handle(index, value):', gizmos)
        self.assertIn('geometry.apply_opening(root, style, width, height, sill, t,', gizmos)
        self.assertIn('def _animate_archyar_openings(scene, depsgraph=None):', controls)
        self.assertIn('root.keyframe_insert(data_path=', controls)


if __name__ == "__main__":
    unittest.main()

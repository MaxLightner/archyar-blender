"""Static pure-Python checks: Blender runtime/device tests still required."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
LIVE=(ROOT/"archyar_blender"/"live.py").read_text(encoding="utf-8")
INIT=(ROOT/"archyar_blender"/"__init__.py").read_text(encoding="utf-8")

class LivePublisherTests(unittest.TestCase):
    def test_module_parses_without_blender_runtime(self):
        ast.parse(LIVE)
        self.assertIn("live.register()",INIT)
        self.assertIn("live.unregister()",INIT)

    def test_limited_pose_and_model_publishing(self):
        self.assertIn("blender_to_project_position",LIVE)
        self.assertIn("blender_to_project_quaternion",LIVE)
        self.assertIn('"/camera"',LIVE)
        self.assertIn('"/project"',LIVE)
        self.assertIn("baseRevision",LIVE)
        self.assertIn("_fingerprint",LIVE)
        self.assertIn("ThreadPoolExecutor(max_workers=1",LIVE)

    def test_no_framebuffer_video_or_persistent_secret(self):
        self.assertNotIn("read_pixels(",LIVE)
        self.assertNotIn("glReadPixels",LIVE)
        self.assertNotIn("scene[\"archyar_live_token\"]",LIVE)
        self.assertIn('context.window_manager.clipboard = viewer_url',LIVE)

if __name__=="__main__":
    unittest.main()

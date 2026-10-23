"""Pure-Python checks that do not need Blender installed."""

import importlib.util
from pathlib import Path
import sys
import unittest


BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('archyar_blender.catalog', BASE/'archyar_blender/catalog.py')
catalog = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = catalog
spec.loader.exec_module(catalog)
constraint_spec = importlib.util.spec_from_file_location(
    'archyar_blender.constraints', BASE/'archyar_blender/constraints.py')
constraints = importlib.util.module_from_spec(constraint_spec)
constraint_spec.loader.exec_module(constraints)


class CatalogContract(unittest.TestCase):
    def test_furniture_count_and_ids(self):
        self.assertEqual(len(catalog.FURNITURE), 22)
        self.assertEqual([item.index for item in catalog.FURNITURE], list(range(22)))

    def test_source_dimensions(self):
        self.assertEqual((catalog.FURNITURE[0].width, catalog.FURNITURE[0].height,
                          catalog.FURNITURE[0].depth), (2.1, .85, .9))
        self.assertEqual((catalog.FURNITURE[8].width, catalog.FURNITURE[8].depth), (1.65, 2.08))
        self.assertEqual(sum(a.wall_mounted for a in catalog.FURNITURE), 6)

    def test_build_and_openings(self):
        self.assertEqual(len(catalog.WALL_PRESETS), 3)
        self.assertEqual(len(catalog.OPENINGS), 6)
        self.assertEqual(len(catalog.BUILD_PARTS), 5)
        with self.assertRaises(ValueError):
            catalog.furniture(22)

    def test_modules_parse(self):
        for source in (BASE/'archyar_blender').glob('*.py'):
            compile(source.read_text(encoding='utf-8'), str(source), 'exec')

    def test_blender_ui_is_english(self):
        labels = list(catalog.CATEGORY_NAMES.values()) + [x.name for x in catalog.FURNITURE]
        labels += list(catalog.OPENINGS.values()) + list(catalog.BUILD_PARTS.values())
        for label in labels:
            self.assertTrue(label.isascii(), label)

    def test_stair_bounds_match_android(self):
        self.assertTrue(constraints.stair_valid(3.0, 1.1, 1.8, 10))
        self.assertFalse(constraints.stair_valid(.49, 1.1, 1.8, 10))
        self.assertFalse(constraints.stair_valid(3.0, .49, 1.8, 10))
        self.assertFalse(constraints.stair_valid(3.0, 1.1, 1.8, 5))
        self.assertFalse(constraints.stair_valid(1.0, 1.1, 1.8, 10))
        self.assertEqual(constraints.STAIR_OPEN, 'stair-open')
        self.assertEqual(constraints.STAIR_FILLED, 'stair-filled')

    def test_opening_bounds_match_android(self):
        pos = constraints.opening_position(4, 3, 1.2, 1.4, .9, 'fixed', 0, .01)
        self.assertAlmostEqual(pos, (1.2/2 + .1)/4)
        with self.assertRaises(ValueError):
            constraints.opening_position(4, 3, 1.2, 2.2, .9, 'fixed', 0, .5)
        with self.assertRaises(ValueError):
            constraints.opening_position(4, 3, .9, 2.1, .9, 'door', 0, .5)
        with self.assertRaises(ValueError):
            constraints.opening_position(4, 3, 1.2, 1.4, .9, 'fixed', 0, .5, [(.5, 1)])


if __name__ == '__main__':
    unittest.main()

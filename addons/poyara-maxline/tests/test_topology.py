import unittest
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'maxline_topology', Path(__file__).resolve().parents[1] / 'poyara_maxline' / 'topology.py'
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
break_vertices = _module.break_vertices
delete_segments = _module.delete_segments
dissolve_vertices = _module.dissolve_vertices


class SplineTopologyTests(unittest.TestCase):
    def test_break_middle_vertex_splits_and_removes_edges(self):
        self.assertEqual(
            break_vertices(list("abcdefg"), {3}),
            [(list("abc"), False), (list("efg"), False)],
        )

    def test_break_end_vertex(self):
        self.assertEqual(break_vertices(list("abcd"), {0}), [(list("bcd"), False)])

    def test_break_multiple_adjacent_vertices(self):
        self.assertEqual(
            break_vertices(list("abcdefgh"), {2, 3, 5}),
            [(list("ab"), False), (list("gh"), False)],
        )

    def test_break_cyclic_ring_turns_it_into_open_spline(self):
        self.assertEqual(
            break_vertices(list("abcde"), {2}, cyclic=True),
            [(list("deab"), False)],
        )

    def test_break_cyclic_two_knots(self):
        self.assertEqual(
            break_vertices(list("abcdef"), {1, 4}, cyclic=True),
            [(list("cd"), False), (list("fa"), False)],
        )

    def test_dissolve_keeps_neighbor_connection(self):
        self.assertEqual(
            dissolve_vertices(list("abcde"), {2}),
            [(list("abde"), False)],
        )

    def test_dissolve_cyclic_keeps_ring(self):
        self.assertEqual(
            dissolve_vertices(list("abcde"), {1}, cyclic=True),
            [(list("acde"), True)],
        )

    def test_delete_middle_segment_splits(self):
        self.assertEqual(
            delete_segments(list("abcdef"), {2}),
            [(list("abc"), False), (list("def"), False)],
        )

    def test_delete_ring_edge_opens_ring(self):
        self.assertEqual(
            delete_segments(list("abcd"), {1}, cyclic=True),
            [(list("cdab"), False)],
        )

    def test_delete_two_ring_edges_splits(self):
        self.assertEqual(
            delete_segments(list("abcdef"), {1, 4}, cyclic=True),
            [(list("cde"), False), (list("fab"), False)],
        )

    def test_noop_preserves_cyclic(self):
        self.assertEqual(break_vertices(list("abc"), [], True), [(list("abc"), True)])
        self.assertEqual(delete_segments(list("abc"), [], True), [(list("abc"), True)])


if __name__ == "__main__":
    unittest.main()

"""Synthetic interface invariants only: no trained map / real-data accuracy claim."""
import json
import math
import random
import unittest
from unittest.mock import patch

from geometry_interface import Edge, OrderedMetricGraph
from reserve_odometry.route import Route


def edge(name='a', points=((0, 0, 0), (10, 0, 0)), start='n0', end='n1'):
    return Edge(name, start, end, points, ('SYNTHETIC_GROUP/ANTENNA_UNRESOLVED',))


def project(graph, q, distance=20., tolerance=0.):
    return graph.nearest_candidates(q, max_distance_m=distance, tie_tolerance_m=tolerance)


class InterfaceTests(unittest.TestCase):
    def test_existing_route_is_used_exactly(self):
        e = edge(points=((0, 0, 1), (3, 4, 2), (10, 7, 5)))
        graph, route = OrderedMetricGraph('SYNTHETIC_METRIC_FRAME', [e]), Route(e.points)
        for n in range(101):
            s = route.arc[-1] * n / 100
            self.assertEqual(graph.at('a', s), route.at(s))

    def test_crossing_is_not_a_switch(self):
        a = edge('a', ((-1, 0, 0), (1, 0, 0)), 'a0', 'a1')
        b = edge('b', ((0, -1, 0), (0, 1, 0)), 'b0', 'b1')
        graph = OrderedMetricGraph('SYNTHETIC_METRIC_FRAME', [a, b])
        self.assertEqual(graph.successors('a'), ())
        self.assertEqual({p.edge_id for p in project(graph, (0, 0, 0))}, {'a', 'b'})

    def test_explicit_switch_retains_all_branches(self):
        graph = OrderedMetricGraph('test', [edge(),
            edge('b', ((10, 0, 0), (20, 0, 0)), 'n1', 'n2'),
            edge('c', ((10, 0, 0), (10, 10, 0)), 'n1', 'n3')])
        self.assertEqual(graph.successors('a'), ('b', 'c'))

    def test_identical_endpoint_without_shared_id_does_not_connect(self):
        graph = OrderedMetricGraph('test', [edge(),
            edge('b', ((10, 0, 0), (20, 0, 0)), 'other', 'end')])
        self.assertEqual(graph.successors('a'), ())

    def test_inconsistent_shared_node_rejected(self):
        with self.assertRaises(ValueError):
            OrderedMetricGraph('test', [edge(), edge('b', ((11, 0, 0), (20, 0, 0)), 'n1', 'end')])

    def test_gap_does_not_get_bridged(self):
        graph = OrderedMetricGraph('test', [edge(), edge('b', ((20, 0, 0), (30, 0, 0)), 'b0', 'b1')])
        self.assertEqual(project(graph, (15, 0, 0), distance=2), ())

    def test_loop_keeps_distinct_arc_positions(self):
        a = edge(points=((0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 0, 0)), end='n0')
        result = project(OrderedMetricGraph('test', [a]), (0, 0, 0), distance=0)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].s_m, 0)
        self.assertGreater(result[1].s_m, 30)

    def test_adjacent_vertex_is_not_two_hypotheses(self):
        a = edge(points=((0, 0, 0), (10, 0, 0), (10, 10, 0)))
        self.assertEqual(len(project(OrderedMetricGraph('test', [a]), (10, 0, 0), distance=0)), 1)

    def test_reversal_roundtrip_preserves_position(self):
        e = edge(points=((0, 0, 0), (3, 4, 1), (8, 9, 2)))
        a, b = OrderedMetricGraph('test', [e]), OrderedMetricGraph('test', [e.reversed()])
        length = Route(e.points).arc[-1]
        for i in range(101):
            s = length if i == 100 else length * (i / 100)
            self.assertLess(math.dist(a.at('a', s)[0], b.at('a', length - s)[0]), 1e-12)
        self.assertEqual(e.reversed().reversed(), e)

    def test_projection_clamps_only_segment_parameter(self):
        g = OrderedMetricGraph('test', [edge()])
        self.assertEqual(project(g, (-2, 1, 0))[0].s_m, 0)
        self.assertEqual(project(g, (12, 1, 0))[0].s_m, 10)
        with self.assertRaises(ValueError):
            g.at('a', 10.1)

    def test_projection_z_is_interpolated_not_used_as_heading_or_branch_oracle(self):
        g = OrderedMetricGraph('test', [edge(points=((0, 0, 2), (10, 0, 4)))])
        p = project(g, (5, 2, 999))[0]
        self.assertEqual(p.xyz_m, (5, 0, 3))
        self.assertEqual(p.horizontal_distance_m, 2)
        self.assertAlmostEqual(p.s_m, math.sqrt(104) / 2)

    def test_finite_and_explicit_z(self):
        for value in (((0, 0), (1, 0)), ((0, 0, 0), (1, 0, math.nan)),
                      ((0, 0, 0), (1, math.inf, 0)), ((0, 0, 0), (2e9, 0, 0))):
            with self.assertRaises(ValueError):
                edge(points=value)

    def test_degenerate_segment_is_rejected(self):
        for points in (((0, 0, 0), (0, 0, 0)), ((0, 0, 0), (0, 0, 1))):
            with self.assertRaises(ValueError):
                edge(points=points)

    def test_explicit_provenance_and_frame(self):
        with self.assertRaises(ValueError):
            Edge('a', 'n0', 'n1', ((0, 0, 0), (1, 0, 0)), ())
        with self.assertRaises(ValueError):
            OrderedMetricGraph('', [edge()])

    def test_serialization_order_and_nonreadiness(self):
        a, b = edge(), edge('b', ((20, 0, 0), (30, 0, 0)), 'b0', 'b1')
        x = OrderedMetricGraph('test', [a, b]).prototype_bytes()
        self.assertEqual(x, OrderedMetricGraph('test', [b, a]).prototype_bytes())
        value = json.loads(x)
        self.assertFalse(value['component_ready'])
        self.assertEqual(value['coordinate_transform'], 'NOT_IMPLEMENTED')
        self.assertEqual(value['body_heading'], 'UNRESOLVED')

    def test_strict_graph_and_actual_byte_budgets(self):
        with self.assertRaises(ValueError):
            OrderedMetricGraph('test', [edge(), edge()])
        with patch('geometry_interface.MAX_SERIALIZED_BYTES', 20):
            with self.assertRaises(ValueError):
                OrderedMetricGraph('test', [edge()])
        with patch('geometry_interface.MAX_POINTS', 3):
            with self.assertRaises(ValueError):
                OrderedMetricGraph('test', [edge(), edge('b')])

    def test_mutating_inputs_does_not_change_graph(self):
        points = [[0, 0, 0], [10, 0, 0]]
        e = edge(points=points)
        g = OrderedMetricGraph('test', [e])
        before = g.prototype_bytes()
        points[0][0] = 500
        self.assertEqual(before, g.prototype_bytes())

    def test_invalid_query_and_thresholds(self):
        g = OrderedMetricGraph('test', [edge()])
        for q in ((1, 2), (1, 2, math.nan)):
            with self.assertRaises(ValueError):
                project(g, q)
        for maximum, tolerance in ((-1, 0), (1, -1), (math.inf, 0), (1, math.nan)):
            with self.assertRaises(ValueError):
                g.nearest_candidates((0, 0, 0), max_distance_m=maximum, tie_tolerance_m=tolerance)

    def test_seeded_projection_optimality_and_reversal(self):
        rng = random.Random(4800)
        for _ in range(200):
            a = tuple(rng.uniform(-20, 20) for _ in range(3))
            b = tuple(rng.uniform(-20, 20) for _ in range(3))
            q = tuple(rng.uniform(-20, 20) for _ in range(3))
            e = edge(points=(a, b))
            p = project(OrderedMetricGraph('test', [e]), q, distance=100)[0]
            reverse = project(OrderedMetricGraph('test', [e.reversed()]), q, distance=100)[0]
            # Independent exhaustive discrete oracle: continuous optimum cannot be worse.
            distances = [math.hypot(q[0] - a[0] - t/100*(b[0]-a[0]),
                                   q[1] - a[1] - t/100*(b[1]-a[1])) for t in range(101)]
            self.assertLessEqual(p.horizontal_distance_m, min(distances) + 1e-12)
            self.assertLess(math.dist(p.xyz_m, reverse.xyz_m), 1e-12)
            self.assertAlmostEqual(p.s_m + reverse.s_m, math.dist(a, b), places=11)


if __name__ == '__main__':
    unittest.main(verbosity=2)

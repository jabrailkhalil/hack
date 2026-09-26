"""Preflight-only metric graph interface; NOT a fitted H48 map or localizer.

Supplied coordinates must already be in one explicitly named metric frame.
No GNSS decoding, frame conversion, route fitting, branch selection or startup
logic is performed here. All examples/tests use synthetic coordinates. Native
H42/H43 dependency verification remains required before any real map fitting.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Sequence

from reserve_odometry.route import Route

MAX_EDGES = 1024
MAX_POINTS = 20000
MAX_SERIALIZED_BYTES = 1_000_000  # Internal interface budget, not organizer limit.
Point = tuple[float, float, float]


def label(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError('A nonempty label of at most 256 characters is required')
    return value


def point(value: Sequence[float]) -> Point:
    if len(value) != 3:
        raise ValueError('Expected three metric coordinates; no implicit z=0')
    result = tuple(float(x) for x in value)
    if not all(math.isfinite(x) and abs(x) <= 1e9 for x in result):
        raise ValueError('Coordinates must be finite and within the interface bound')
    return result


@dataclass(frozen=True)
class Edge:
    edge_id: str
    from_node: str
    to_node: str
    points: tuple[Point, ...]
    provenance: tuple[str, ...]

    def __post_init__(self):
        for item in (self.edge_id, self.from_node, self.to_node):
            label(item)
        if not isinstance(self.points, (tuple, list)) or not 2 <= len(self.points) <= MAX_POINTS:
            raise ValueError('Supply a bounded sequence of 2..MAX_POINTS coordinates')
        if not isinstance(self.provenance, (tuple, list)) or not 1 <= len(self.provenance) <= 256:
            raise ValueError('Explicit bounded source/receiver provenance is required')
        object.__setattr__(self, 'points', tuple(point(p) for p in self.points))
        object.__setattr__(self, 'provenance', tuple(label(p) for p in self.provenance))
        Route(self.points)  # Preserve the existing exact arc-length and at(s) rules.
        for a, b in zip(self.points, self.points[1:]):
            if math.hypot(b[0] - a[0], b[1] - a[1]) <= 1e-6:
                raise ValueError('XY-degenerate segment has no unique horizontal projection')

    def reversed(self) -> Edge:
        """Same edge traversed in reverse. Caller must name any separate directed edge."""
        return Edge(self.edge_id, self.to_node, self.from_node,
                    self.points[::-1], self.provenance)


@dataclass(frozen=True)
class Projection:
    edge_id: str
    segment_index: int
    s_m: float                # Three-dimensional arc length, as in existing Route.
    xyz_m: Point
    horizontal_distance_m: float


class OrderedMetricGraph:
    """Explicit edges, not connectivity inferred from spatial proximity.

    Projecting a complete check trajectory is an offline geometry diagnostic;
    it is not a causal branch/start estimator. Returned ties are NOT resolved.
    """
    def __init__(self, frame_id: str, edges: Sequence[Edge]):
        self.frame_id = label(frame_id)
        if not isinstance(edges, (tuple, list)) or not 1 <= len(edges) <= MAX_EDGES:
            raise ValueError('A bounded nonempty edge sequence is required')
        if not all(isinstance(e, Edge) for e in edges):
            raise TypeError('Only explicit Edge objects are supported')
        if sum(len(e.points) for e in edges) > MAX_POINTS:
            raise ValueError('Graph point budget exceeded')
        self._edges = tuple(sorted(edges, key=lambda e: e.edge_id))
        if len({e.edge_id for e in self._edges}) != len(self._edges):
            raise ValueError('Duplicate edge ID')
        nodes = {}
        for e in self._edges:
            for node_id, xyz in ((e.from_node, e.points[0]), (e.to_node, e.points[-1])):
                if node_id in nodes and nodes[node_id] != xyz:
                    raise ValueError('An explicit shared node must have identical coordinates')
                nodes[node_id] = xyz
        self._routes = {e.edge_id: Route(e.points) for e in self._edges}
        self._by_id = {e.edge_id: e for e in self._edges}
        self.prototype_bytes()  # Fail closed when the actual encoding exceeds budget.

    def successors(self, edge_id: str) -> tuple[str, ...]:
        target = self._by_id[edge_id].to_node
        return tuple(e.edge_id for e in self._edges if e.from_node == target)

    def at(self, edge_id: str, s_m: float):
        """Return supplied branch xyz and its TANGENT quaternion, not body heading."""
        return self._routes[edge_id].at(s_m)

    def nearest_candidates(self, query_xyz: Sequence[float], *,
                           max_distance_m: float, tie_tolerance_m: float) -> tuple[Projection, ...]:
        """Bounded exhaustive XY search; caller must retain uncertainty about ties.

        Both thresholds are explicit caller inputs, NOT fitted H48/start settings.
        Query z is validated but not used to resolve horizontal branch ambiguity.
        """
        q = point(query_xyz)
        if not math.isfinite(max_distance_m) or not 0 <= max_distance_m <= 1e9:
            raise ValueError('Invalid maximum horizontal distance')
        if not math.isfinite(tie_tolerance_m) or not 0 <= tie_tolerance_m <= 1e9:
            raise ValueError('Invalid tie tolerance')
        candidates = {}
        for edge in self._edges:
            arc = self._routes[edge.edge_id].arc
            for i, (a, b) in enumerate(zip(edge.points, edge.points[1:])):
                dx, dy = b[0] - a[0], b[1] - a[1]
                u = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / (dx * dx + dy * dy)
                u = min(1.0, max(0.0, u))
                xyz = tuple(x + u * (y - x) for x, y in zip(a, b))
                distance = math.hypot(q[0] - xyz[0], q[1] - xyz[1])
                if distance > max_distance_m:
                    continue
                # Exact vertex endpoints give the exact stored arc value.
                s = arc[i] if u == 0 else (arc[i + 1] if u == 1 else arc[i] + u * (arc[i + 1] - arc[i]))
                key = (edge.edge_id, s)
                # Deduplicate one vertex only; repeated coordinates at different s survive.
                candidates.setdefault(key, Projection(edge.edge_id, i, s, xyz, distance))
        if not candidates:
            return ()
        best = min(p.horizontal_distance_m for p in candidates.values())
        result = [p for p in candidates.values() if p.horizontal_distance_m <= best + tie_tolerance_m]
        return tuple(sorted(result, key=lambda p: (p.horizontal_distance_m, p.edge_id, p.s_m)))

    def prototype_bytes(self) -> bytes:
        """Deterministic interface fixture, deliberately NOT MAP_V0 or a handoff."""
        value = dict(schema='R5_H48_INTERFACE_ONLY_V1', component_ready=False,
                     frame_id=self.frame_id, units='m', arc_length='3D Euclidean',
                     projection_metric='horizontal XY', body_heading='UNRESOLVED',
                     extrinsics='UNRESOLVED', coordinate_transform='NOT_IMPLEMENTED',
                     edges=[asdict(e) for e in self._edges])
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        if len(raw) > MAX_SERIALIZED_BYTES:
            raise ValueError('Prototype uncompressed byte budget exceeded')
        return raw

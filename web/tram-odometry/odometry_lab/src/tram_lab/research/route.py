"""Directed external route geometry; never built from replay/reference GNSS.

Input is explicit ENU metres with a fixed WGS84 origin, not an assumed MGRS
transform. Tangent heading/pitch and zero roll are engineering approximations.
"""
from bisect import bisect_right
from dataclasses import dataclass
import hashlib
import json
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def triple(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or not all(map(finite, value)):
        raise ValueError('Coordinates must be three finite numbers')
    return tuple(float(x) for x in value)


def ecef(lat, lon, alt):
    if not all(map(finite, (lat, lon, alt))) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid WGS84 coordinate')
    p, l = math.radians(lat), math.radians(lon)
    a, e2 = 6378137.0, 6.6943799901413165e-3
    n = a / math.sqrt(1-e2*math.sin(p)**2)
    return ((n+alt)*math.cos(p)*math.cos(l), (n+alt)*math.cos(p)*math.sin(l),
            (n*(1-e2)+alt)*math.sin(p))


def to_enu(lat, lon, alt, origin):
    olat, olon, oalt = origin
    a, b = ecef(lat, lon, alt), ecef(olat, olon, oalt)
    x, y, z = (u-v for u, v in zip(a, b))
    p, l = math.radians(olat), math.radians(olon)
    return (-math.sin(l)*x+math.cos(l)*y,
            -math.sin(p)*math.cos(l)*x-math.sin(p)*math.sin(l)*y+math.cos(p)*z,
            math.cos(p)*math.cos(l)*x+math.cos(p)*math.sin(l)*y+math.sin(p)*z)


@dataclass(frozen=True)
class Projection:
    path: str
    s: float
    lateral_m: float
    xyz: tuple


class Route:
    def __init__(self, document):
        # Explicit contract; unsupported original formats are not guessed.
        if not isinstance(document, dict):
            raise ValueError('Route must be a JSON object')
        if document.get('schema') != 'tram-route-enu-v1' or document.get('frame') != 'ENU':
            raise ValueError('Expected tram-route-enu-v1, frame ENU; convert the supplied pathgraph explicitly')
        self.origin = triple(document.get('origin_wgs84'))  # lat, lon, ellipsoid h
        ecef(*self.origin)
        if document.get('reference_point') != 'base_link':
            raise ValueError('Route reference_point must explicitly be base_link')
        if document.get('height_reference') not in ('ellipsoidal_enu', 'unknown'):
            raise ValueError('Declare height_reference: ellipsoidal_enu or unknown')
        if not isinstance(document.get('source'), str) or not document['source'].strip():
            raise ValueError('Declare the origin/source of the external route')
        paths = document.get('paths')
        if not isinstance(paths, list) or not 1 <= len(paths) <= 16:
            raise ValueError('Expected 1..16 directed paths')
        self.paths = {}
        self.closed = {}
        total = 0
        for item in paths:
            if not isinstance(item, dict):
                raise ValueError('Path must be an object')
            identity, raw = item.get('id'), item.get('points')
            if not isinstance(identity, str) or not 1 <= len(identity) <= 100 or identity in self.paths:
                raise ValueError('Path IDs must be unique nonempty strings')
            if item.get('direction') != 'forward':
                raise ValueError('Declare forward ordering for every route; no automatic reversal')
            if not isinstance(raw, list) or not 2 <= len(raw) <= 20000:
                raise ValueError('Expected 2..20000 points per path')
            points = [triple(p) for p in raw]
            closed = item.get('closed', False)
            if not isinstance(closed, bool) or (closed and points[0] != points[-1]):
                raise ValueError('closed must be boolean; closed paths must repeat the first point')
            self.closed[identity] = closed
            if any(abs(v) > 100000 for point in points for v in point):
                raise ValueError('Expected local ENU coordinates within 100 km')
            cumulative = [0.]
            segments = []
            for a, b in zip(points, points[1:]):
                d = tuple(v-u for u, v in zip(a, b))
                horizontal = math.hypot(d[0], d[1]); length = math.sqrt(sum(x*x for x in d))
                if horizontal < 1e-5 or length > 2000:
                    raise ValueError('Degenerate/vertical/over-2km segment: repair source topology explicitly')
                axis_x = tuple(v/length for v in d)
                axis_y = (-d[1]/horizontal, d[0]/horizontal, 0.)
                axis_z = (-axis_x[2]*axis_y[1], axis_x[2]*axis_y[0],
                          axis_x[0]*axis_y[1]-axis_x[1]*axis_y[0])
                segments.append((a, d, length, axis_x, axis_y, axis_z))
                cumulative.append(cumulative[-1]+length)
            total += len(segments)
            self.paths[identity] = (segments, cumulative)
        if total > 20000:
            raise ValueError('At most 20000 segments in the research UI')
        self.document = json.loads(json.dumps(document, allow_nan=False))
        self.sha256 = hashlib.sha256(json.dumps(document, sort_keys=True, allow_nan=False,
                                               separators=(',', ':')).encode()).hexdigest()

    def point(self, path, s):
        segments, cumulative = self.paths[path]
        if finite(s) and self.closed[path]:
            s %= cumulative[-1]
        if not finite(s) or not 0 <= s <= cumulative[-1]:
            return None  # Never clamp a trajectory to route end.
        i = min(bisect_right(cumulative, s)-1, len(segments)-1)
        a, d, length, *_ = segments[i]
        u = (s-cumulative[i])/length
        return tuple(x+u*y for x, y in zip(a, d))

    def project(self, xyz, lever, *, path=None, expected_s=None, innovation_gate=20.,
                lateral_gate=8., ambiguity_margin=.5):
        xyz, lever = triple(xyz), triple(lever)
        choices = []
        if path is not None and path not in self.paths:
            raise ValueError('Unknown path')
        for identity, (segments, cumulative) in self.paths.items():
            if path is not None and identity != path:
                continue
            for i, (a, d, length, ex, ey, ez) in enumerate(segments):
                # Evaluate antenna position on EACH candidate segment; subtracting
                # a fixed world-x lever before heading is known would be wrong.
                offset = tuple(lever[0]*ex[k]+lever[1]*ey[k]+lever[2]*ez[k] for k in range(3))
                q = tuple(xyz[k]-offset[k]-a[k] for k in range(3))
                u = max(0., min(1., (q[0]*d[0]+q[1]*d[1])/(d[0]**2+d[1]**2)))
                s = cumulative[i]+u*length
                if expected_s is not None and self.closed[identity]:
                    s += math.floor((expected_s-s)/cumulative[-1]+.5)*cumulative[-1]
                if expected_s is not None and abs(s-expected_s) > innovation_gate:
                    continue
                residual = math.hypot(q[0]-u*d[0], q[1]-u*d[1])
                choices.append(Projection(identity, s, residual, tuple(a[k]+u*d[k] for k in range(3))))
        choices.sort(key=lambda x: (x.lateral_m, x.path, x.s))
        if not choices or choices[0].lateral_m > lateral_gate:
            return None, 'outside_gate'
        best = choices[0]
        # Adjacent polyline segments near one arc coordinate are the same state;
        # a crossing, parallel route or loop elsewhere is not.
        for other in choices[1:]:
            if other.lateral_m > best.lateral_m+ambiguity_margin:
                break
            separation = abs(other.s-best.s)
            if other.path == best.path and expected_s is None and self.closed[best.path]:
                total = self.paths[best.path][1][-1]
                separation = min(separation, total-separation)
            if other.path != best.path or separation > 5.:
                return None, 'ambiguous_route'
        return best, 'accepted'

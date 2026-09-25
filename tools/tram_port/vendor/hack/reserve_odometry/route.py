"""Optional projection onto an explicitly supplied, ordered metric route.

No reconstruction of turns from front/rear bogie speed, no GNSS lookup.
The caller must supply the correct branch through every switch.
"""
import bisect
import csv
import math
from pathlib import Path


class Route:
    def __init__(self, points):
        self.points = [tuple(float(x) for x in p) for p in points]
        if len(self.points) < 2 or any(len(p) != 3 or not all(math.isfinite(x) for x in p)
                                      for p in self.points):
            raise ValueError('Route needs >=2 finite xyz points')
        self.arc = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            distance = math.dist(a, b)
            if distance <= 1e-6:
                raise ValueError('Repeated route point / zero length segment')
            self.arc.append(self.arc[-1] + distance)

    @classmethod
    def from_csv(cls, path):
        with Path(path).open(newline='') as source:
            rows = csv.DictReader(source)
            return cls([(row['x'], row['y'], row.get('z', 0.0)) for row in rows])

    def at(self, s):
        """Return xyz, quaternion(x,y,z,w); do not silently clamp outside route."""
        if not math.isfinite(s) or s < 0 or s > self.arc[-1]:
            raise ValueError('Position outside supplied route')
        i = min(len(self.points) - 2, max(0, bisect.bisect_right(self.arc, s) - 1))
        a, b = self.points[i], self.points[i + 1]
        f = (s - self.arc[i]) / (self.arc[i + 1] - self.arc[i])
        xyz = tuple(x + f * (y - x) for x, y in zip(a, b))
        dx, dy, dz = (y - x for x, y in zip(a, b))
        yaw = math.atan2(dy, dx)
        pitch = -math.atan2(dz, math.hypot(dx, dy))
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        return xyz, (-sy * sp, cy * sp, sy * cp, cy * cp)

"""WGS84 antenna-coordinate geometry. No inferred geoid, MGRS or extrinsics."""
from __future__ import annotations
import math

A = 6378137.0
F = 1.0 / 298.257223563
E2 = F * (2.0 - F)


def ecef(llh):
    lat, lon, h = map(float, llh)
    if not all(math.isfinite(x) for x in (lat, lon, h)) or abs(lat) > 90 or abs(lon) > 180:
        raise ValueError('Finite geodetic latitude/longitude/ellipsoid height required')
    p, l = math.radians(lat), math.radians(lon)
    n = A / math.sqrt(1.0 - E2 * math.sin(p)**2)
    return ((n+h)*math.cos(p)*math.cos(l), (n+h)*math.cos(p)*math.sin(l),
            (n*(1-E2)+h)*math.sin(p))


def geodetic(xyz):
    x, y, z = map(float, xyz)
    if not all(math.isfinite(v) for v in (x,y,z)):
        raise ValueError('Nonfinite ECEF')
    r = math.hypot(x,y)
    if r < 1e-8:
        if abs(z) < 1: raise ValueError('Earth centre is not a geodetic point')
        return (math.copysign(90.,z), 0., abs(z)-A*(1-F))
    p = math.atan2(z, r*(1-E2))
    for _ in range(12):
        n = A/math.sqrt(1-E2*math.sin(p)**2)
        p = math.atan2(z+E2*n*math.sin(p), r)
    n = A/math.sqrt(1-E2*math.sin(p)**2)
    h = r*math.cos(p)+z*math.sin(p)-A*math.sqrt(1-E2*math.sin(p)**2)
    return (math.degrees(p), math.degrees(math.atan2(y,x)), h)


class LocalENU:
    def __init__(self, origin):
        self.origin = tuple(map(float,origin))
        self.zero = ecef(origin)
        p,l=map(math.radians, self.origin[:2]); sp,cp,sl,cl=math.sin(p),math.cos(p),math.sin(l),math.cos(l)
        self.rotation=((-sl,cl,0.),(-sp*cl,-sp*sl,cp),(cp*cl,cp*sl,sp))

    def forward(self, llh):
        d=tuple(a-b for a,b in zip(ecef(llh),self.zero))
        return tuple(sum(a*b for a,b in zip(row,d)) for row in self.rotation)

    def reverse(self, enu):
        if len(enu)!=3 or not all(math.isfinite(float(x)) for x in enu): raise ValueError('Finite ENU required')
        return geodetic(tuple(self.zero[j]+sum(self.rotation[i][j]*enu[i] for i in range(3)) for j in range(3)))

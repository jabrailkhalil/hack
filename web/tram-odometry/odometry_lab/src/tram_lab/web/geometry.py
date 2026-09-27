"""Offline display geometry. Never imported by an estimator."""
from functools import lru_cache
import math
import numpy as np
from ..data import read_bag
from ..signals import align_reference


def route_geometry(events, start_ns):
    events = list(events)
    master = [e for e in events if e.topic == '/sensing/gnss/master/fix']
    rows = master or [e for e in events if e.topic == '/sensing/gnss/rover/fix']
    rows.sort(key=lambda e: (e.stamp_ns, e.sequence))
    segments, current = [], []
    previous = None
    def flush():
        nonlocal current
        if len(current) >= 2:
            points = np.asarray(current, dtype=float)
            latitude = np.radians(points[:, 1])
            longitude = np.radians(points[:, 2])
            a = np.sin(np.diff(latitude)/2)**2 + np.cos(latitude[:-1])*np.cos(latitude[1:])*np.sin(np.diff(longitude)/2)**2
            arc = np.r_[0., np.cumsum(6371008.8 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1))))]
            keep = np.r_[True, np.diff(arc) > 1e-5]
            segments.append(dict(t=points[:, 0].tolist(), lat=points[:, 1].tolist(), lon=points[:, 2].tolist(),
                                 arc=arc.tolist(), route=points[keep, 1:3].tolist(), route_arc=arc[keep].tolist()))
        current = []
    for event in rows:
        data = event.data
        lat, lon = data['latitude'], data['longitude']
        valid = math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180 and data.get('status', 0) >= 0
        t = (event.stamp_ns - start_ns) / 1e9
        if not valid:
            flush(); previous = None
            continue
        if previous is not None:
            dt = t - previous[0]
            dy = (lat - previous[1]) * 111195
            dx = (lon - previous[2]) * 111195 * math.cos(math.radians(lat))
            if dt <= 0 or dt > 1 or math.hypot(dx, dy) > max(50, 60*dt):
                flush()
        current.append((t, lat, lon))
        previous = (t, lat, lon)
    flush()
    return dict(source='master' if master else 'rover' if rows else None, segments=segments,
                semantics='GNSS route for offline display only; jumps/gaps split geometry, not metric masks')


def project(geometry, t, distance):
    predicted = np.full((len(t), 2), np.nan)
    actual = np.full((len(t), 2), np.nan)
    geo_segment = np.full(len(t), -1, dtype=int)
    for index, segment in enumerate(geometry['segments']):
        st = np.asarray(segment['t'])
        inside = np.flatnonzero((t >= st[0]) & (t <= st[-1]))
        if not len(inside):
            continue
        # Nearest actual fix, never smooth or bridge a missing observation.
        ix, _ = align_reference(np.rint(t[inside]*1e9).astype(np.int64), np.rint(st*1e9).astype(np.int64), 250_000_000)
        good = ix >= 0
        actual[inside[good], 0] = np.asarray(segment['lat'])[ix[good]]
        actual[inside[good], 1] = np.asarray(segment['lon'])[ix[good]]
        geo_segment[inside] = index
        candidates = inside[good & np.isfinite(distance[inside])]
        if not len(candidates) or len(segment['route']) < 2:
            continue
        anchor = candidates[0]
        anchor_s = np.interp(t[anchor], st, segment['arc'])
        query = distance[inside] - distance[anchor] + anchor_s
        arc = np.asarray(segment['route_arc'])
        ok = np.isfinite(query) & (query >= 0) & (query <= arc[-1]) & (inside >= anchor)
        points = np.asarray(segment['route'])
        predicted[inside[ok], 0] = np.interp(query[ok], arc, points[:, 0])
        predicted[inside[ok], 1] = np.interp(query[ok], arc, points[:, 1])
    return predicted, actual, geo_segment


@lru_cache(maxsize=4)
def cached_geometry(record_json, cache, msg_dir):
    import json
    record = json.loads(record_json)
    return route_geometry(read_bag(record, cache, msg_dir), record['start_ns'])

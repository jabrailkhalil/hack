"""Causal sparse-GNSS route-offset correction, independent of the speed observer."""
from bisect import bisect_right
from collections import Counter, deque
from dataclasses import dataclass
from .route import finite

ANTENNAS = {'master': (-9.873, 0., 3.), 'rover': (2.563, 0., 3.)}


@dataclass(frozen=True)
class Fix:
    stamp_ns: int
    received_ns: int
    xyz: tuple
    receiver: str = 'master'
    status: int = 0
    frame_id: str = 'gps'
    initialization_only: bool = False


@dataclass(frozen=True)
class Policy:
    gain: float = .35
    max_age_s: float = .5
    lateral_gate_m: float = 8.
    innovation_gate_m: float = 20.
    ambiguity_margin_m: float = .5
    max_correction_m: float = 5.
    initial_only: bool = False
    initial_window_s: float = 3.0  # Engineering setting, not a guaranteed GNSS duration.

    def __post_init__(self):
        for key in ('gain', 'max_age_s', 'lateral_gate_m', 'innovation_gate_m',
                    'ambiguity_margin_m', 'max_correction_m'):
            value = getattr(self, key)
            if not finite(value) or value <= 0:
                raise ValueError('Invalid correction policy: '+key)
        if (self.gain > 1 or self.max_age_s > 2 or self.innovation_gate_m > 100
                or self.lateral_gate_m > 50 or self.max_correction_m > 5
                or self.ambiguity_margin_m > 5 or not isinstance(self.initial_only, bool)
                or not finite(self.initial_window_s) or not .05 <= self.initial_window_s <= 60):
            raise ValueError('Research correction policy outside supported bounds')


class Localizer:
    def __init__(self, route, policy=Policy(), path=None, origin_ns=None):
        if path is not None and path not in route.paths:
            raise ValueError('Unknown path')
        self.route, self.policy, self.path = route, policy, path
        self.offset = None
        self.history = deque(maxlen=128)  # bounded and source-time indexed
        self.last_time = None
        self.last_stamp = {}
        self.counts = Counter()
        self.last_decisions = []
        self.last_raw = None
        self.segment_broken = False
        self.origin_ns = origin_ns
        self.ever_initialized = False
        self.frame_id = None
        self.requires_restart = False
        self.segment_id = 0

    def _raw_at(self, stamp_ns):
        history = list(self.history)
        stamps = [t for t, s in history]
        i = bisect_right(stamps, stamp_ns)-1
        if i < 0:
            return None
        if stamps[i] == stamp_ns:
            return history[i][1]
        if i+1 == len(stamps) or stamps[i+1]-stamps[i] > 100_000_000:
            return None
        alpha = (stamp_ns-stamps[i])/(stamps[i+1]-stamps[i])
        return history[i][1]+alpha*(history[i+1][1]-history[i][1])

    def _fix(self, fix, now):
        p = self.policy
        if (fix.receiver not in ANTENNAS or not finite(fix.status)
                or fix.status not in (0, 1, 2)):
            return 'invalid_fix', None
        if any(not isinstance(t, int) or isinstance(t, bool) for t in (fix.stamp_ns, fix.received_ns)):
            return 'invalid_timestamp', None
        if fix.received_ns > now or fix.stamp_ns > fix.received_ns:
            return 'future_fix', None
        if fix.stamp_ns <= self.last_stamp.get(fix.receiver, -1):
            return 'duplicate_or_reordered', None
        self.last_stamp[fix.receiver] = fix.stamp_ns
        if now-fix.stamp_ns > round(p.max_age_s*1e9):
            return 'stale_fix', None
        if not isinstance(fix.frame_id, str) or not fix.frame_id or (self.frame_id is not None and fix.frame_id != self.frame_id):
            return 'frame_mismatch', None
        if self.requires_restart:
            return 'restart_required', None
        if self.offset is None and (fix.received_ns-self.origin_ns)/1e9 > p.initial_window_s:
            return 'initial_window_expired', None
        if self.ever_initialized and p.initial_only:
            return 'initial_only', None
        if self.offset is not None and fix.initialization_only:
            return 'initial_window_only', None
        raw_at_fix = self._raw_at(fix.stamp_ns)
        if raw_at_fix is None:
            return 'no_odometry_at_fix_time', None
        expected = None if self.offset is None else raw_at_fix+self.offset
        try:
            match, reason = self.route.project(fix.xyz, ANTENNAS[fix.receiver], path=self.path,
                expected_s=expected, innovation_gate=p.innovation_gate_m,
                lateral_gate=p.lateral_gate_m, ambiguity_margin=p.ambiguity_margin_m)
        except ValueError:
            return 'invalid_coordinate', None
        if match is None:
            return reason, None
        if self.offset is None:
            self.path = match.path
            self.offset = match.s-raw_at_fix
            self.ever_initialized = True
            self.frame_id = fix.frame_id
            return 'initialized', 0.
        residual = match.s-expected
        correction = max(-p.max_correction_m, min(p.max_correction_m, p.gain*residual))
        self.offset += correction
        return 'corrected', correction

    def step(self, time_ns, raw_distance, fixes=()):
        if not isinstance(time_ns, int) or isinstance(time_ns, bool):
            raise ValueError('Publication time must be integer nanoseconds')
        if self.last_time is not None and time_ns <= self.last_time:
            raise ValueError('Non-increasing publication clock; start a new Localizer after seek')
        gap = self.last_time is not None and time_ns-self.last_time > 200_000_000
        if self.origin_ns is None:
            self.origin_ns = time_ns
        self.last_time = time_ns
        self.last_decisions = []
        if not finite(raw_distance):
            self.history.clear()
            if not self.segment_broken:
                self.segment_id += 1
            self.segment_broken = True
            self.offset = None
            self.requires_restart |= self.ever_initialized
            for fix in fixes:
                self.counts['odometry_unavailable'] += 1
                self.last_decisions.append({'stamp_ns': str(fix.stamp_ns), 'received_ns': str(fix.received_ns),
                                            'reason': 'odometry_unavailable', 'correction_m': None})
            return dict(status='ODOMETRY_UNAVAILABLE', raw_distance=None,
                        route_s=None, xyz=None, offset_m=None, segment_id=self.segment_id)
        reset = self.last_raw is not None and raw_distance < self.last_raw-1e-6
        if self.segment_broken or reset or gap:
            # No implicit second absolute initialization after loss/reset. A new
            # replay must explicitly declare a new start; the first window never reopens.
            self.offset = None
            self.history.clear()
            self.counts['segment_reset'] += 1
            self.requires_restart |= self.ever_initialized
            self.segment_id += 1
            self.segment_broken = False
        self.last_raw = raw_distance
        self.history.append((time_ns, raw_distance))
        while self.history and time_ns-self.history[0][0] > round((self.policy.max_age_s+.2)*1e9):
            self.history.popleft()
        for fix in fixes:
            reason, correction = self._fix(fix, time_ns)
            self.counts[reason] += 1
            self.last_decisions.append(dict(stamp_ns=str(fix.stamp_ns), received_ns=str(fix.received_ns),
                                             reason=reason, correction_m=correction))
        route_s = raw_distance+self.offset if self.offset is not None else None
        xyz = self.route.point(self.path, route_s) if route_s is not None else None
        return dict(status='TRACKED' if xyz is not None else ('UNLOCALIZED' if self.offset is None else 'OUTSIDE_ROUTE'),
                    raw_distance=raw_distance, route_s=route_s, xyz=xyz, offset_m=self.offset,
                    segment_id=self.segment_id)

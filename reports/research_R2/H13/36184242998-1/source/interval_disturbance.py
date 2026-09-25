"""Bounded causal interval reconstruction for disturbance targets (H13).

The stored values are the native predictor's pre-correction g snapshots, not
wheel acceleration and not g+disturbance. Linear interpolation is confined to
valid adjacent snapshots. No extrapolation across missing/invalid history.
"""
from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    left: float
    right: float
    reason: str = ''


class ModelHistory:
    MAX_SEGMENTS = 32
    HORIZON_S = 0.75
    EPS = 1e-9

    def __init__(self):
        self.segments = deque(maxlen=self.MAX_SEGMENTS)
        self.previous = None
        self.last = None
        self.endpoint_control = False  # non-selectable, offline ablation only
        self.counts = dict(eligible=0, applied=0, changed=0, skipped=0,
                           history=0, stale=0, clipped=0, gap=0, nonfinite=0)

    def clear(self):
        self.segments.clear()
        self.previous = None

    def record(self, previous_t, t, g, reason=''):
        """Call once per native output tick after time validation, before fusion."""
        self.last = None
        if not math.isfinite(t) or not math.isfinite(g):
            self.clear()
            return
        old = self.previous
        if old is not None and previous_t is not None:
            ot, og, why = old
            if abs(ot - previous_t) > self.EPS or t <= ot:
                self.clear()
            else:
                self.segments.append(Segment(ot, t, og, g, reason or why))
        self.previous = (t, g, reason)
        # Drop whole oldest segments; never stretch or bridge a missing edge.
        cutoff = t - self.HORIZON_S
        while self.segments and self.segments[0].start < cutoff - self.EPS:
            self.segments.popleft()

    def mean(self, start, end):
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            return None, 'nonfinite'
        cursor, integral = start, 0.0
        for seg in self.segments:
            if seg.end <= cursor:
                continue
            if seg.start > cursor + self.EPS:
                return None, 'history'
            right = min(end, seg.end)
            if right <= cursor:
                continue
            if seg.reason:
                return None, seg.reason
            width = seg.end - seg.start
            lo = max(cursor, seg.start)
            gl = seg.left + (seg.right - seg.left) * (lo - seg.start) / width
            gr = seg.left + (seg.right - seg.left) * (right - seg.start) / width
            integral += 0.5 * (gl + gr) * (right - lo)
            cursor = right
            if cursor >= end:
                value = integral / (end - start)
                return (value, '') if math.isfinite(value) else (None, 'nonfinite')
        return None, 'history'

    def target(self, start, end, measured_a, endpoint_target, current_g, d_before):
        self.counts['eligible'] += 1
        mean_g, reason = self.mean(start, end)
        desired = None if mean_g is None else measured_a - mean_g
        self.last = dict(start=start, end=end, measured_a=measured_a,
                         current_pre_g=current_g, current_post_g=measured_a-endpoint_target,
                         mean_g=mean_g, original_target=endpoint_target,
                         interval_target=desired, disturbance_before=d_before,
                         reason=reason)
        if desired is None:
            self.counts['skipped'] += 1
            self.counts[reason] += 1
            return None
        self.counts['applied'] += 1
        self.counts['changed'] += int(abs(desired-endpoint_target) > 1e-6)
        return endpoint_target if self.endpoint_control else desired

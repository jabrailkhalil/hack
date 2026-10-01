"""H13 research-only neutral common-acceleration guard; fixed prior constants.

No runtime/evaluator file is modified. Pair history uses two distinct stamps;
held samples can bridge asynchronous callbacks but cannot add confirmations.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Limits:
    neutral_u_max: float = 0.05
    stable_command_delta: float = 0.05
    wheel_accel_min: float = 1.0
    model_accel_max: float = 0.5
    residual_min: float = 0.30
    required_pairs: int = 2
    quarantine_s: float = 1.0


class NeutralGuard:
    """O(1) state. enabled=False is the exact historical execution path."""
    def __init__(self, enabled=True):
        self.enabled = bool(enabled)
        self.limits = Limits()
        self.last_used = (-math.inf, -math.inf)
        self.previous = None
        self.count = 0
        self.sign = 0
        self.blocked_until = -math.inf
        # Diagnostic counters; none are inputs to the decision.
        self.pairs = self.suspicious_pairs = self.triggers = self.vetoes = 0

    def clear_evidence(self):
        self.previous = None
        self.count = self.sign = 0

    def update(self, t, u, command_stale, front, rear, statuses, predicted, acceleration, config):
        if not self.enabled:
            return False
        p = self.limits
        def valid(s):
            return (s is not None and math.isfinite(s.t) and math.isfinite(s.value)
                    and -1e-9 <= t-s.t <= config.max_age_s
                    and abs(s.value) <= config.max_speed_mps)
        pair_valid = (valid(front) and valid(rear)
                      and abs(front.t-rear.t) <= config.pair_skew_s
                      and abs(front.value-rear.value) <= config.disagreement_mps)
        raw_bad = any(s in ('RATE_ANOMALY', 'RANGE', 'MISSING_OR_STALE',
                           'AMBIGUOUS_PAIR', 'ZERO_LOCK_SUSPECT') for s in statuses)
        if command_stale or abs(u) > p.neutral_u_max or not pair_valid or raw_bad:
            self.clear_evidence()
            return False
        # Either wheel reused from the last evaluated pair: no new confirmation.
        if front.t <= self.last_used[0] or rear.t <= self.last_used[1]:
            return t < self.blocked_until
        self.last_used = (front.t, rear.t)
        tz = (front.t + rear.t) * .5
        z = (front.value + rear.value) * .5
        self.pairs += 1
        previous = self.previous
        suspicious = False
        sign = 0
        if previous is not None:
            dt = tz-previous[0]
            if .05-1e-9 <= dt <= .25+1e-9 and abs(u-previous[2]) <= p.stable_command_delta:
                a = (z-previous[1])/dt
                suspicious = (abs(a) > p.wheel_accel_min
                              and abs(acceleration) < p.model_accel_max
                              and abs(z-predicted) > p.residual_min)
                sign = 1 if a-acceleration > 0 else -1
        self.previous = (tz, z, u)
        if suspicious:
            self.suspicious_pairs += 1
            self.count = self.count+1 if sign == self.sign else 1
            self.sign = sign
            if self.count >= p.required_pairs:
                self.blocked_until = max(self.blocked_until, t+p.quarantine_s)
                self.triggers += 1
                self.count = 0
        else:
            # A model-consistent observation breaks consecutive evidence, but is
            # still the reference for the next fresh pair derivative.
            self.count = self.sign = 0
        return t < self.blocked_until


PATCH_MARKER = '        self.v = predicted\n        self.pv = p_prior\n'
HOOK = '''        h13_blocked = self._h13.update(
            t, u, command_stale, front, rear, statuses, predicted, a_model, c)
        if h13_blocked:
            self.reacquire_blocked_until = max(
                self.reacquire_blocked_until, self._h13.blocked_until)
            # Preserve healthy one-wheel fallback exactly as preregistered.
            if len(accepted) == 2:
                accepted = []
                statuses = ['H13_NEUTRAL_QUARANTINE', 'H13_NEUTRAL_QUARANTINE']
                self._h13.vetoes += 1
'''


def patch_core(source: str) -> str:
    """Add two bounded hooks to an isolated copy; fail on unexpected source."""
    reset = '        self.last_estimate = None\n'
    if source.count(PATCH_MARKER) != 1 or source.count(reset) != 1:
        raise ValueError('Pinned core hook locations changed')
    return source.replace(reset, reset+'        self._h13 = NeutralGuard(H13_ENABLED)\n').replace(
        PATCH_MARKER, HOOK+PATCH_MARKER)

"""H01: causal, conditional measurement transport; no reference-sensor inputs.

This consistency gate is not a fault detector with calibrated confidence. In
particular, plausible common-mode wheel errors can still satisfy every check.
It owns two previous raw samples and scalar state, never a growing history.
"""
import math


class ConditionalProjection:
    __slots__ = ('previous', 'since', 'last_reason', 'last_delta')

    def __init__(self):
        self.previous = None
        self.since = None
        self.last_reason = 'RESET'
        self.last_delta = 0.0

    def _reject(self, reason, *, clear=True):
        if clear:
            self.previous = None
        self.since = None
        self.last_reason = reason
        return 0.0

    def delta(self, c, t, a_model, predicted, disturbance,
              samples, accepted, statuses, command_stale):
        """Return an additive correction only after the original observer gates.

        Samples are never mutated. Duplicate prediction ticks cannot produce a
        second correction, but do not erase still-fresh 10 Hz trust evidence.
        """
        self.last_delta = 0.0
        if not c.h01_projection_gain:
            return self._reject('DISABLED')
        if command_stale:
            return self._reject('COMMAND')
        if not all(math.isfinite(x) for x in (t, a_model, predicted, disturbance)):
            return self._reject('NONFINITE')
        if len(accepted) != 2 or any(s is None for s in samples):
            if (all(status == 'DUPLICATE_OR_OLD' for status in statuses)
                    and self.previous is not None
                    and all(0 <= t - s.t <= c.max_age_s for s in self.previous)):
                self.last_reason = 'PREDICTION_ONLY'
                return 0.0
            return self._reject('NOT_TRUSTED_PAIR')
        front, rear = samples
        if not all(math.isfinite(s.t) and math.isfinite(s.value) for s in samples):
            return self._reject('NONFINITE')
        ages = (t - front.t, t - rear.t)
        if (not all(0 <= age <= min(c.max_age_s, c.pair_skew_s) for age in ages)
                or abs(front.t - rear.t) > c.pair_skew_s):
            return self._reject('AGE_OR_SKEW')
        z = (front.value + rear.value) * 0.5
        if (abs(front.value - rear.value) > min(c.disagreement_mps, 3*c.wheel_sigma_mps)
                or front.value * rear.value <= 0
                or abs(z) <= max(0.5, c.reacquire_min_speed_mps)):
            return self._reject('WHEEL_CONFIDENCE')
        if any(abs(s.value - predicted) > c.innovation_floor_mps for s in samples):
            return self._reject('INNOVATION')
        if (abs(a_model) >= c.max_accel_mps2
                or (c.disturbance_limit_mps2 > 0
                    and abs(disturbance) >= c.disturbance_limit_mps2)):
            return self._reject('MODEL_SATURATION')
        old = self.previous
        self.previous = (front, rear)
        if old is None:
            return self._reject('NEED_HISTORY', clear=False)
        intervals = (front.t - old[0].t, rear.t - old[1].t)
        if not all(0.05-1e-9 <= dt <= c.max_age_s for dt in intervals):
            return self._reject('HISTORY_GAP', clear=False)
        accelerations = tuple((s.value - p.value)/dt
                              for s, p, dt in zip(samples, old, intervals))
        margin = c.reacquire_accel_margin_mps2
        if (any(abs(a) > c.max_accel_mps2 or abs(a-a_model) > margin for a in accelerations)
                or abs(accelerations[0] - accelerations[1]) > margin):
            return self._reject('ACCELERATION', clear=False)
        stamp = (front.t + rear.t) * 0.5
        if self.since is None:
            self.since = stamp
        if stamp - self.since + 1e-9 < c.stop_dwell_s:
            self.last_reason = 'DWELL'
            return 0.0
        delta = c.h01_projection_gain * a_model * sum(ages) * 0.5
        delta = max(-c.rate_noise_margin_mps, min(c.rate_noise_margin_mps, delta))
        if any(s.value * (s.value + delta) <= 0 or abs(s.value + delta) > c.max_speed_mps
               for s in samples):
            return self._reject('PROJECTION_BOUNDS')
        self.last_reason = 'PROJECTED' if delta else 'ZERO_DELTA'
        self.last_delta = delta
        return delta

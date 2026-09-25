"""H04: bounded causal learning-rate schedule, not a new measurement filter.

Only the gain of the existing disturbance update changes. Missing evidence
never decays the disturbance, creates a new measurement, or delays output.
The constants belong to the preregistered singleton H04 candidate.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class AdaptationSchedule:
    """Fixed-size state; recreated by Observer.reset(). Times are sensor time."""

    regime: Optional[int] = None
    fast_until: float = float('-inf')
    trusted_since: Optional[float] = None
    blocked_until: float = float('-inf')

    def select(self, *, t, u, command_stale, mode, statuses, front, rear,
               predicted, config):
        """Return tau; never alter the observer, samples, or correction gates.

        Called once per initialized output tick, including prediction-only
        ticks. ACCEPTED/DUPLICATE_OR_OLD alone is not a detected fault: the
        asynchronous source rates need not match the output rate.
        """
        base = config.adaptation_tau_s
        slow = 4.0 * base
        if command_stale:
            self.regime = None
            self.fast_until = float('-inf')
            self.trusted_since = None
            self.blocked_until = t + 0.50
            return slow

        regime = (1 if u > config.command_deadband else
                  -1 if u < -config.command_deadband else 0)
        if self.regime is not None and regime != self.regime:
            self.fast_until = t + 0.75
        self.regime = regime

        if any(s not in ('ACCEPTED', 'DUPLICATE_OR_OLD') for s in statuses):
            self.trusted_since = None
            self.blocked_until = t + 0.50
            return slow
        if mode != 'FUSED':
            return slow  # no learning; do not invent a fault on duplicate ticks

        strong = (front is not None and rear is not None and
                  -1e-9 <= t - front.t <= 0.10 + 1e-9 and
                  -1e-9 <= t - rear.t <= 0.10 + 1e-9 and
                  abs(front.t - rear.t) <= 0.05 + 1e-9 and
                  abs(front.value - rear.value) <= 0.15 + 1e-9 and
                  abs((front.value + rear.value) * 0.5 - predicted) <=
                  max(0.30, 3.0 * config.wheel_sigma_mps))
        if not strong:
            self.trusted_since = None
            return slow
        if self.trusted_since is None:
            self.trusted_since = t
        if t < self.blocked_until - 1e-9:
            return slow
        if (t < self.fast_until - 1e-9 and
                t - self.trusted_since >= 0.20 - 1e-9):
            return 0.5 * base
        return base

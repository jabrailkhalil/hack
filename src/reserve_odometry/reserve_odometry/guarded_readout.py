"""Causal timestamp-bias correction without feedback into the v5 observer.

The inherited v/s/pv/disturbance fields deliberately remain the baseline state.
Consumers use the returned Estimate (or last_estimate), not those inner fields.
There is no second filter, external reference, sensor replay or future input.
"""
from dataclasses import dataclass, replace
import math
from typing import Optional
from .core import Config, Estimate, Observer, Sample, clip


@dataclass(frozen=True)
class ReadoutConfig:
    gain: float = 1.0
    holdoff_s: float = 0.5

    def __post_init__(self):
        if not math.isfinite(self.gain) or not 0.0 <= self.gain <= 1.0:
            raise ValueError('readout gain must be finite and within [0, 1]')
        if not math.isfinite(self.holdoff_s) or not 0.0 <= self.holdoff_s <= 10.0:
            raise ValueError('readout holdoff_s must be finite and within [0, 10]')


class GuardedReadoutObserver(Observer):
    """Unmodified inner v5 plus a bounded correction to its published estimate.

    For an accepted wheel update with gain K and mean age h:
        delta_v <- (1-K)*delta_v + K*gain*a_model*h
    Prediction ticks retain delta_v only while BOTH held wheels are fresh,
    mutually consistent and without rejection. A fault resets delta_v, and
    compensation is blocked until holdoff_s of continuously healthy evidence.
    Neither delta_v nor corrected distance is fed into the inner observer.
    """
    def __init__(self, config: Optional[Config] = None, *,
                 readout: Optional[ReadoutConfig] = None):
        self.readout = readout or ReadoutConfig()
        super().__init__(config)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._velocity_correction = 0.0
        self._distance_correction = 0.0
        self._correction_sigma_s = 0.0
        self._blocked_until = -math.inf

    def step(self, t: float, command: Optional[Sample] = None,
             front: Optional[Sample] = None, rear: Optional[Sample] = None) -> Estimate:
        old_t, old_v = self.t, self.v
        old_pv, old_disturbance = self.pv, self.disturbance
        old_correction = self._velocity_correction
        estimate = super().step(t, command, front, rear)
        if self.readout.gain == 0.0:
            return estimate
        if old_t is None or estimate.mode in ('WAITING_FOR_INITIALIZATION', 'INITIALIZED'):
            self._velocity_correction = 0.0
            return estimate
        dt = t - old_t  # super().step enforces strictly positive, bounded dt.
        statuses = (estimate.front_status, estimate.rear_status)
        pair_ok = (self._valid(front, t, self.c.max_age_s)
                   and self._valid(rear, t, self.c.max_age_s)
                   and abs(front.t - rear.t) <= self.c.pair_skew_s
                   and abs(front.value - rear.value) <= self.c.disagreement_mps)
        healthy = (pair_ok and not estimate.command_stale
                   and all(s in ('ACCEPTED', 'DUPLICATE_OR_OLD') for s in statuses)
                   and estimate.mode not in ('REACQUIRING', 'STOPPED'))
        if not healthy:
            self._blocked_until = t + self.readout.holdoff_s
        if not healthy or t < self._blocked_until:
            self._velocity_correction = 0.0
        else:
            accepted = [sample for sample, status in zip((front, rear), statuses)
                        if status == 'ACCEPTED']
            if accepted:
                age = sum(max(0.0, t - sample.t) for sample in accepted) / len(accepted)
                # These are the SAME pre-correction dynamics used by super().step.
                acceleration = clip(self.drive_a - self.resistance(old_v) + old_disturbance,
                                    -self.c.max_accel_mps2, self.c.max_accel_mps2)
                p_prior = old_pv + self.c.process_noise_v * dt
                # Scalar Joseph update: P_post=(1-K)*P_prior. The clamp handles
                # the baseline variance floor; it never increases trust above 1.
                kalman_gain = clip(1.0 - estimate.variance_v / p_prior, 0.0, 1.0)
                self._velocity_correction = (
                    (1.0 - kalman_gain) * old_correction
                    + kalman_gain * self.readout.gain * acceleration * age)
            limit = self.c.max_accel_mps2 * self.c.max_age_s
            self._velocity_correction = clip(self._velocity_correction, -limit, limit)
        velocity = clip(estimate.v + self._velocity_correction,
                        -self.c.max_speed_mps, self.c.max_speed_mps)
        if estimate.v * velocity <= 0.0:
            # The readout must not create motion or a sign reversal at a stop.
            velocity = estimate.v
        self._velocity_correction = velocity - estimate.v
        self._distance_correction += 0.5 * (old_correction + self._velocity_correction) * dt
        # Conservative temporal envelopes, NOT calibrated confidence intervals.
        self._correction_sigma_s += 0.5 * (abs(old_correction) + abs(self._velocity_correction)) * dt
        self.last_estimate = replace(
            estimate, v=velocity, s=estimate.s + self._distance_correction,
            a=estimate.a + (self._velocity_correction - old_correction) / dt,
            variance_v=estimate.variance_v + self._velocity_correction ** 2,
            variance_s=(math.sqrt(estimate.variance_s) + self._correction_sigma_s) ** 2)
        return self.last_estimate

"""Causal timestamp-bias correction without feedback into the v5 observer.

The inherited v/s/pv/disturbance fields deliberately remain the baseline state.
Consumers use the returned Estimate (or last_estimate), not those inner fields.
There is no second filter, external reference, sensor replay or future input.
"""
from dataclasses import dataclass, replace
from collections import deque
import math
from typing import Optional
from .core import Config, Estimate, Observer, Sample, clip


@dataclass(frozen=True)
class ReadoutConfig:
    gain: float = 1.0
    holdoff_s: float = 0.5
    integral_age: bool = False

    def __post_init__(self):
        if not isinstance(self.integral_age, bool):
            raise ValueError('integral_age must be a bool')
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
        self._model_segments = deque(maxlen=16)

    def _integral_between(self, begin, end):
        """Exact integral of the discrete predictor history, or None for a gap.

        Each segment (left, right] contains the acceleration the core used for
        that completed predictor step. It is NOT a measured historical path.
        """
        if begin >= end:
            return 0.0
        cursor, integral = begin, 0.0
        for left, right, acceleration in self._model_segments:
            if right <= cursor:
                continue
            if left > cursor:
                return None
            edge = min(end, right)
            integral += acceleration * (edge - cursor)
            cursor = edge
            if cursor >= end:
                return integral
        return None

    def _age_increment(self, t, accepted, acceleration, age):
        """Average each accepted sample's integral, never integrate mean stamp."""
        original = acceleration * age
        if not self.readout.integral_age:
            return original
        increments = [self._integral_between(min(t, sample.t), t)
                      for sample in accepted]
        if any(value is None for value in increments):
            return original  # Missing coverage must never wait or fabricate history.
        # Preserve the exact old arithmetic for its constant-acceleration case.
        oldest = min(sample.t for sample in accepted)
        if all(a == acceleration for left, right, a in self._model_segments
               if right > oldest):
            return original
        return sum(increments) / len(increments)

    def step(self, t: float, command: Optional[Sample] = None,
             front: Optional[Sample] = None, rear: Optional[Sample] = None) -> Estimate:
        old_t, old_v = self.t, self.v
        old_pv, old_disturbance = self.pv, self.disturbance
        old_drive = self.drive_a
        old_correction = self._velocity_correction
        estimate = super().step(t, command, front, rear)
        if self.readout.gain == 0.0:
            return estimate
        if old_t is None or estimate.mode in ('WAITING_FOR_INITIALIZATION', 'INITIALIZED'):
            self._velocity_correction = 0.0
            return estimate
        dt = t - old_t  # super().step enforces strictly positive, bounded dt.
        if self.readout.integral_age:
            # Reconstruct the IDENTICAL pre-correction arithmetic; core may have
            # reset drive_a at STOPPED or adapted disturbance after prediction.
            u = 0.0 if estimate.command_stale else clip(command.value, -1, 1)
            target = self.drive_target(u, old_v)
            drive = old_drive + (1.0 - math.exp(-dt / self.c.actuator_tau_s)) * (target - old_drive)
            model_a = clip(drive - self.resistance(old_v) + old_disturbance,
                           -self.c.max_accel_mps2, self.c.max_accel_mps2)
            self._model_segments.append((old_t, t, model_a))
            cutoff = t - self.c.max_age_s
            while self._model_segments and self._model_segments[0][1] <= cutoff:
                self._model_segments.popleft()
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
                contribution = kalman_gain * self.readout.gain * acceleration * age
                if self.readout.integral_age:
                    increment = self._age_increment(t, accepted, acceleration, age)
                    if increment != acceleration * age:
                        contribution = kalman_gain * self.readout.gain * increment
                self._velocity_correction = (
                    (1.0 - kalman_gain) * old_correction
                    + contribution)
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

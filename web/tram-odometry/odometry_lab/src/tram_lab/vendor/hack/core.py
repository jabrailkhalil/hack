"""Causal longitudinal observer; SI units; no GNSS/IMU or future samples.

This is a hackathon baseline, not a certified safety component. Default physical
parameters are illustrative until identified on the organizer's training data.
"""
from dataclasses import dataclass, asdict
import math
from typing import Optional


def clip(x, lo, hi):
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class Sample:
    t: float
    value: float


@dataclass
class Config:
    mass_kg: float = 40000.0
    wheel_radius_m: float = 0.33
    gear_ratio: float = 6.0
    efficiency: float = 0.90
    total_motor_torque_nm: float = 4400.0
    max_power_w: float = 300000.0
    max_brake_force_n: float = 65000.0
    rolling_force_n: float = 1200.0
    quadratic_drag_n_s2_m2: float = 4.0
    actuator_tau_s: float = 0.35
    command_deadband: float = 0.04
    command_exponent: float = 1.25
    travel_direction: float = 1.0
    max_speed_mps: float = 40.0
    max_accel_mps2: float = 3.0
    # Opt-in: transport accepted wheel values to the output timestamp.
    # Zero retains the historical v4/v5 estimator, including its arithmetic.
    wheel_time_compensation: float = 0.0
    wheel_sigma_mps: float = 0.10
    process_noise_v: float = 0.10
    max_age_s: float = 0.25
    command_timeout_s: float = 0.5
    pair_skew_s: float = 0.10
    disagreement_mps: float = 0.7
    wheel_rate_limit_mps2: float = 4.0
    rate_noise_margin_mps: float = 0.25
    innovation_floor_mps: float = 0.8
    innovation_cap_mps: float = 3.0
    stop_speed_mps: float = 0.07
    stop_model_speed_mps: float = 0.25
    stop_dwell_s: float = 0.5
    adaptation_tau_s: float = 8.0
    disturbance_limit_mps2: float = 0.6
    max_step_s: float = 0.20
    reacquire_dwell_s: float = 0.8
    reacquire_max_residual_mps: float = 8.0
    reacquire_step_mps: float = 0.15
    reacquire_min_speed_mps: float = 0.4
    reacquire_accel_margin_mps2: float = 0.8
    # Opt-in H11: after near-simultaneous implausible jumps on both wheels,
    # block only common-mode reacquisition for this source-time interval.
    common_mode_quarantine_s: float = 0.0

    def __post_init__(self):
        for key, value in asdict(self).items():
            if not math.isfinite(value):
                raise ValueError(f'{key} must be finite')
        positive = ('mass_kg', 'wheel_radius_m', 'gear_ratio', 'efficiency',
                    'total_motor_torque_nm', 'max_power_w', 'max_brake_force_n',
                    'actuator_tau_s', 'command_exponent', 'max_speed_mps',
                    'max_accel_mps2', 'wheel_sigma_mps', 'process_noise_v',
                    'max_age_s', 'command_timeout_s', 'pair_skew_s',
                    'wheel_rate_limit_mps2', 'innovation_floor_mps',
                    'innovation_cap_mps', 'stop_dwell_s', 'adaptation_tau_s', 'max_step_s',
                    'reacquire_dwell_s', 'reacquire_max_residual_mps', 'reacquire_step_mps',
                    'reacquire_accel_margin_mps2')
        for key in positive:
            if getattr(self, key) <= 0:
                raise ValueError(f'{key} must be positive')
        if not 0 <= self.command_deadband < 1 or self.efficiency > 1:
            raise ValueError('Invalid deadband or efficiency')
        if not 0.0 <= self.wheel_time_compensation <= 1.0:
            raise ValueError('wheel_time_compensation must be between 0 and 1')
        if self.travel_direction not in (-1.0, 1.0):
            raise ValueError('travel_direction must be -1 or 1')
        if self.innovation_cap_mps < self.innovation_floor_mps:
            raise ValueError('Innovation cap must be >= floor')
        for key in ('rolling_force_n', 'quadratic_drag_n_s2_m2', 'disagreement_mps',
                    'rate_noise_margin_mps', 'stop_speed_mps', 'stop_model_speed_mps',
                    'disturbance_limit_mps2', 'reacquire_min_speed_mps',
                    'common_mode_quarantine_s'):
            if getattr(self, key) < 0:
                raise ValueError(f'{key} must be nonnegative')


@dataclass(frozen=True)
class Estimate:
    t: float
    s: float
    v: float
    a: float
    variance_v: float
    variance_s: float
    disturbance: float
    mode: str
    front_status: str
    rear_status: str
    command_stale: bool


class Observer:
    """One bounded state and two bounded sensor histories; constant memory."""
    def __init__(self, config: Optional[Config] = None):
        self.c = config or Config()
        self.reset()

    def reset(self, *, velocity=None, position=0.0):
        if not math.isfinite(position) or (velocity is not None and
                (not math.isfinite(velocity) or abs(velocity) > self.c.max_speed_mps)):
            raise ValueError('Invalid initial state')
        self.t = None
        self.s = float(position)
        self.v = 0.0 if velocity is None else float(velocity)
        self.initialized = velocity is not None
        self.drive_a = 0.0
        self.disturbance = 0.0
        self.pv = 1.0
        self.sigma_s = 0.0
        self.used = [None, None]
        self.raw_previous = [None, None]
        self.stop_since = None
        self.adapt_previous = None
        self.reacquire_since = None
        self.reacquire_previous = None
        self.pair_pending = [None, None]
        self.rate_anomaly_times = [None, None]
        self.reacquire_blocked_until = -math.inf
        self.last_estimate = None

    def drive_target(self, u, v):
        c = self.c
        q = max(0.0, (abs(u) - c.command_deadband) / (1 - c.command_deadband))
        q = min(1.0, q) ** c.command_exponent
        if u >= 0:
            force = min(c.efficiency * c.gear_ratio * c.total_motor_torque_nm /
                        c.wheel_radius_m, c.max_power_w / max(abs(v), 1.0))
            return c.travel_direction * q * force / c.mass_kg
        return -math.tanh(v / 0.20) * q * c.max_brake_force_n / c.mass_kg

    def resistance(self, v):
        c = self.c
        return (c.rolling_force_n * math.tanh(v / 0.20) +
                c.quadratic_drag_n_s2_m2 * v * abs(v)) / c.mass_kg

    def _valid(self, sample, t, timeout):
        return (sample is not None and math.isfinite(sample.t) and
                math.isfinite(sample.value) and -1e-9 <= t - sample.t <= timeout)

    def _wheel(self, index, sample, t):
        if not self._valid(sample, t, self.c.max_age_s):
            return None, 'MISSING_OR_STALE'
        if abs(sample.value) > self.c.max_speed_mps:
            return None, 'RANGE'
        previous_t = self.used[index]
        if previous_t is not None and sample.t <= previous_t:
            return None, 'DUPLICATE_OR_OLD'
        self.used[index] = sample.t
        previous = self.raw_previous[index]
        self.raw_previous[index] = sample
        if previous is not None:
            dt = sample.t - previous.t
            if dt <= self.c.max_age_s and abs(sample.value - previous.value) > (
                    self.c.wheel_rate_limit_mps2 * dt + self.c.rate_noise_margin_mps):
                if self.c.common_mode_quarantine_s > 0:
                    self.rate_anomaly_times[index] = sample.t
                    other = self.rate_anomaly_times[1 - index]
                    if other is not None and abs(sample.t - other) <= self.c.pair_skew_s + 1e-9:
                        self.reacquire_blocked_until = max(
                            self.reacquire_blocked_until,
                            max(sample.t, other) + self.c.common_mode_quarantine_s)
                return None, 'RATE_ANOMALY'
        return sample, 'CANDIDATE'

    def _clear_reacquire(self):
        self.reacquire_since = None
        self.reacquire_previous = None
        self.pair_pending = [None, None]

    def _take_pending_pair(self, t):
        """Consume two distinct, fresh candidates, even from different ticks.

        This buffer does NOT feed the Kalman correction. It is only evidence
        for bootstrap or recovery after both channels failed the model gate.
        Each pair is consumed once, and prediction-only ticks cannot erase it.
        """
        for i, sample in enumerate(self.pair_pending):
            if sample is not None and not self._valid(sample, t, self.c.max_age_s):
                self.pair_pending[i] = None
        if any(sample is None for sample in self.pair_pending):
            return None
        front, rear = self.pair_pending
        if abs(front.t - rear.t) > self.c.pair_skew_s + 1e-9:
            self.pair_pending[0 if front.t < rear.t else 1] = None
            return None
        self.pair_pending = [None, None]
        return front, rear

    def _reacquire_pair(self, samples, predicted):
        """Return a sustained agreeing pair target after model/odometry divergence.

        This is deliberately conservative: both fresh wheels must agree, the pair
        trajectory must have plausible acceleration, the residual must be bounded,
        and zero-locked wheels cannot drag a moving model to zero. The returned
        target is still approached in bounded increments by step().
        """
        c = self.c
        if not all(sample is not None for sample in samples):
            self._clear_reacquire()
            return None
        front, rear = samples
        if abs(front.t - rear.t) > c.pair_skew_s or abs(front.value - rear.value) > c.disagreement_mps:
            self._clear_reacquire()
            return None
        t_pair = 0.5 * (front.t + rear.t)
        z = 0.5 * (front.value + rear.value)
        residual = z - predicted
        if abs(residual) > c.reacquire_max_residual_mps:
            self._clear_reacquire()
            return None
        if abs(z) < c.reacquire_min_speed_mps and abs(predicted) > c.stop_model_speed_mps:
            self._clear_reacquire()
            return None
        previous = self.reacquire_previous
        if previous is not None:
            dt_pair = t_pair - previous.t
            if dt_pair <= 0 or dt_pair > 2 * c.max_age_s:
                self.reacquire_since = t_pair
            elif abs(z - previous.value) / dt_pair > c.max_accel_mps2 + c.reacquire_accel_margin_mps2:
                self._clear_reacquire()
                return None
        if self.reacquire_since is None:
            self.reacquire_since = t_pair
        self.reacquire_previous = Sample(t_pair, z)
        if t_pair - self.reacquire_since + 1e-9 < c.reacquire_dwell_s:
            return None
        return z

    def step(self, t, command=None, front=None, rear=None):
        """Estimate at time t. A Sample can be assimilated at most once.

        t must increase; negative clock jumps require explicit reset. A long gap
        also requires reset, avoiding fabricated integration over missing time.
        Samples are timestamped in the same clock domain as t, never wall time.
        """
        if not math.isfinite(t):
            raise ValueError('Nonfinite time')
        if self.t is not None and t <= self.t:
            raise ValueError('Time must increase; reset after a clock jump')
        dt = 0.0 if self.t is None else t - self.t
        if dt > self.c.max_step_s + 1e-9:
            raise ValueError('Time gap exceeds max_step_s; explicit reset required')
        c = self.c
        command_stale = not self._valid(command, t, c.command_timeout_s)
        if not command_stale and abs(command.value) > 1.000001:
            command_stale = True
        u = 0.0 if command_stale else clip(command.value, -1, 1)
        previous_v = self.v
        target = self.drive_target(u, self.v)
        alpha = 1.0 - math.exp(-dt / c.actuator_tau_s)
        self.drive_a += alpha * (target - self.drive_a)
        a_model = clip(self.drive_a - self.resistance(self.v) + self.disturbance,
                       -c.max_accel_mps2, c.max_accel_mps2)
        predicted = clip(self.v + dt * a_model, -c.max_speed_mps, c.max_speed_mps)
        # Braking/coasting must not generate a sign reversal numerically.
        if u <= c.command_deadband and self.v * predicted < 0:
            predicted = 0.0
        p_prior = self.pv + c.process_noise_v * dt * (4.0 if command_stale else 1.0)
        samples, statuses = [], []
        for i, sample in enumerate((front, rear)):
            candidate, status = self._wheel(i, sample, t)
            samples.append(candidate)
            statuses.append(status)
        pair = (all(x is not None for x in samples) and
                abs(samples[0].t - samples[1].t) <= c.pair_skew_s)
        agree = pair and abs(samples[0].value - samples[1].value) <= c.disagreement_mps
        # Bootstrap must also work when front/rear arrive on alternating ticks.
        if not self.initialized:
            for i, sample in enumerate(samples):
                if sample is not None:
                    self.pair_pending[i] = sample
            initial_pair = self._take_pending_pair(t)
            if initial_pair and abs(initial_pair[0].value - initial_pair[1].value) <= c.disagreement_mps:
                self.v = sum(sample.value for sample in initial_pair) * .5
                self.initialized = True
                self.pv = c.wheel_sigma_mps ** 2
                self.drive_a = 0.0
                self.t = t
                return self._output(t, 0.0, 'INITIALIZED', ['ACCEPTED'] * 2, command_stale)
            self.t = t
            return self._output(t, 0.0, 'WAITING_FOR_INITIALIZATION', statuses, command_stale)
        gate = min(c.innovation_cap_mps,
                   c.innovation_floor_mps + 3 * math.sqrt(p_prior + c.wheel_sigma_mps ** 2))
        # Fresh common zeros while the model still predicts motion are treated
        # as possible wheel lock, including alternating front/rear callbacks.
        zero_pair = (all(self._valid(x, t, c.max_age_s) and abs(x.value) < c.stop_speed_mps
                         for x in (front, rear)) and
                     abs(front.t - rear.t) <= c.pair_skew_s and
                     abs(predicted) > c.stop_model_speed_mps)
        accepted = []
        for i, sample in enumerate(samples):
            if sample is not None:
                if zero_pair:
                    statuses[i] = 'ZERO_LOCK_SUSPECT'
                elif abs(sample.value - predicted) <= gate:
                    accepted.append(i)
                else:
                    statuses[i] = 'MODEL_DISAGREEMENT'
        if pair and not agree and len(accepted) == 2:
            errors = [abs(sample.value - predicted) for sample in samples]
            if abs(errors[0] - errors[1]) < c.disagreement_mps * 0.5:
                accepted = []  # two competing hypotheses, no independent anchor
            else:
                accepted = [0 if errors[0] < errors[1] else 1]
            for i in range(2):
                if i not in accepted:
                    statuses[i] = 'AMBIGUOUS_PAIR'
        self.v = predicted
        self.pv = p_prior
        mode = 'MODEL_ONLY'
        if accepted:
            self._clear_reacquire()
            z = sum(samples[i].value for i in accepted) / len(accepted)
            age = 0.0
            if c.wheel_time_compensation:
                # Correct only samples that already passed the raw rate/model
                # gates. Keep original stamps/values for adaptation, recovery,
                # stop detection and duplicate rejection; no future data.
                age = sum(max(0.0, t - samples[i].t) for i in accepted) / len(accepted)
                z = clip(z + c.wheel_time_compensation * age * a_model,
                         -c.max_speed_mps, c.max_speed_mps)
            # No 1/N reduction: wheel errors can be correlated.
            r = c.wheel_sigma_mps ** 2 * (1.0 if len(accepted) == 2 and agree else 4.0)
            residual = z - predicted
            r *= max(1.0, abs(residual) / max(3 * c.wheel_sigma_mps, 1e-9))
            # Transport adds model uncertainty; older readings are not extra
            # independent observations. This is a conservative noise allowance,
            # not an exact out-of-sequence Kalman covariance or calibrated CI.
            r += (c.wheel_time_compensation ** 2 * c.process_noise_v * age
                  * (4.0 if command_stale else 1.0))
            gain = p_prior / (p_prior + r)
            self.v += gain * residual
            self.pv = max(1e-8, (1 - gain) ** 2 * p_prior + gain * gain * r)
            mode = 'FUSED' if len(accepted) == 2 and agree else 'SINGLE_WHEEL'
            for i in accepted:
                statuses[i] = 'ACCEPTED'
        else:
            # Prediction ticks at 20 Hz must not reset 10 Hz wheel evidence.
            hard_failure = any(status not in ('MODEL_DISAGREEMENT', 'DUPLICATE_OR_OLD')
                               for status in statuses)
            if hard_failure:
                self._clear_reacquire()
            for i, sample in enumerate(samples):
                if sample is not None and statuses[i] == 'MODEL_DISAGREEMENT':
                    self.pair_pending[i] = sample
            recovery_pair = self._take_pending_pair(t)
            if recovery_pair is not None:
                pair_time = max(recovery_pair[0].t, recovery_pair[1].t)
                if pair_time < self.reacquire_blocked_until - 1e-9:
                    # Do not let a pair that just made an implausible common jump
                    # become the new anchor. Ordinary fusion remains untouched.
                    self._clear_reacquire()
                    statuses = ['COMMON_MODE_QUARANTINE', 'COMMON_MODE_QUARANTINE']
                else:
                    old_pair = self.reacquire_previous
                    target_v = self._reacquire_pair(recovery_pair, predicted)
                    if target_v is not None:
                        pair_dt = self.reacquire_previous.t - old_pair.t if old_pair else 0.0
                        # Config limit is per nominal 0.1 s pair, not per output tick.
                        limit = c.reacquire_step_mps * min(1.0, max(0.0, pair_dt) / .1)
                        correction = clip(target_v - predicted, -limit, limit)
                        self.v = clip(predicted + correction, -c.max_speed_mps, c.max_speed_mps)
                        self.pv = max(self.pv, 4 * c.wheel_sigma_mps ** 2)
                        mode = 'REACQUIRING'
                        statuses = ['REACQUIRE_ACCEPTED', 'REACQUIRE_ACCEPTED']
        # Adapt disturbance only from two new, agreeing and model-consistent wheels.
        if mode == 'FUSED' and not command_stale:
            z = (samples[0].value + samples[1].value) * 0.5
            tz = (samples[0].t + samples[1].t) * 0.5
            old = self.adapt_previous
            if old is not None and 0.05 <= tz - old.t <= c.max_age_s:
                measured_a = (z - old.value) / (tz - old.t)
                if abs(measured_a) <= c.max_accel_mps2 and abs(z) > 0.5:
                    desired = measured_a - self.drive_a + self.resistance(self.v)
                    weight = 1 - math.exp(-(tz - old.t) / c.adaptation_tau_s)
                    self.disturbance = clip(self.disturbance + weight * (desired - self.disturbance),
                                            -c.disturbance_limit_mps2, c.disturbance_limit_mps2)
                self.adapt_previous = Sample(tz, z)
            elif old is None or tz - old.t > c.max_age_s:
                self.adapt_previous = Sample(tz, z)
        elif any(status not in ('DUPLICATE_OR_OLD', 'ACCEPTED') for status in statuses):
            self.adapt_previous = None
        # Fresh held zeros may sustain stop evidence, but may NOT be re-assimilated.
        # A zero reading from locked wheels at substantial model speed is not a stop.
        stop_candidate = (not command_stale and u <= c.command_deadband and
                          abs(predicted) < c.stop_model_speed_mps and
                          all(self._valid(x, t, c.max_age_s) and abs(x.value) < c.stop_speed_mps
                              for x in (front, rear)) and
                          abs(front.t - rear.t) <= c.pair_skew_s)
        if stop_candidate:
            if self.stop_since is None:
                self.stop_since = t
            if t - self.stop_since >= c.stop_dwell_s:
                self.v = 0.0
                self.drive_a = 0.0
                self.disturbance = 0.0
                mode = 'STOPPED'
        else:
            self.stop_since = None
        self.s += 0.5 * (previous_v + self.v) * dt
        # Deliberately conservative temporal-correlation envelope, not calibrated CI.
        self.sigma_s += dt * math.sqrt(max(p_prior, self.pv))
        self.t = t
        a_output = (self.v - previous_v) / dt if dt > 0 else 0.0
        return self._output(t, a_output, mode, statuses, command_stale)

    def _output(self, t, a, mode, statuses, command_stale):
        estimate = Estimate(t, self.s, self.v, a, self.pv, self.sigma_s ** 2,
                            self.disturbance, mode, statuses[0], statuses[1], command_stale)
        self.last_estimate = estimate
        return estimate

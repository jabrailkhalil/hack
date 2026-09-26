"""R5-H47 passive causal features, NOT a fitted reliability observer.

Only native vehicle step arguments enter this collector. It never changes the
returned Estimate, fusion weights, disturbance adaptation, or readout state.
The eventual classifier/action remains gated on the upstream component handoff
and real train/check fault coverage. Standard library only.
"""
from collections import deque
from dataclasses import dataclass
import math
from typing import Optional
from reserve_odometry.core import Config, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

FEATURE_NAMES = (
    'own_age', 'other_age', 'pair_skew', 'rate_innovation',
    'model_innovation', 'pair_mismatch', 'command_mode', 'prior_innovation_mean',
)
HISTORY_SECONDS = 1.0
HISTORY_COUNT = 16
DOMAINS = ((0., 1.), (0., 1.), (0., 1.), (0., 2.),
           (0., 4.), (0., 1.), (-1., 1.), (0., 4.))


@dataclass(frozen=True)
class FeatureRow:
    """Stamp/availability are metadata, not additional classifier features."""
    output_t: float
    source_t: Optional[float]
    values: Optional[tuple[float, ...]]
    reason: str


def in_domain(values):
    return (len(values) == len(FEATURE_NAMES)
            and all(math.isfinite(v) and lo <= v <= hi
                    for v, (lo, hi) in zip(values, DOMAINS))
            and values[6] in (-1., 0., 1.))


class CausalFeatureProbe(GuardedReadoutObserver):
    """Passive collector with <=16 entries/1 s per channel; no trust decisions."""
    def __init__(self, config: Config, *, readout: ReadoutConfig, collect=True):
        if not isinstance(collect, bool):
            raise ValueError('collect must be bool')
        if config.disagreement_mps <= 0:
            raise ValueError('positive baseline disagreement scale is required')
        self._h47_collect = collect
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._h47_histories = [deque(maxlen=HISTORY_COUNT), deque(maxlen=HISTORY_COUNT)]
        self._h47_previous = [None, None]
        self._h47_watermarks = [None, None]
        self.last_features = (None, None)

    @staticmethod
    def _strict_valid(sample, t, timeout, maximum):
        return (sample is not None and math.isfinite(sample.t)
                and math.isfinite(sample.value) and 0 <= t - sample.t <= timeout
                and abs(sample.value) <= maximum)

    def step(self, t, command=None, front=None, rear=None):
        old_t, old_v, old_d = self.t, self.v, self.disturbance
        # Let native validation finish before mutating ANY auxiliary state.
        result = super().step(t, command, front, rear)
        if not self._h47_collect:
            self.last_features = (None, None)
            return result
        if old_t is None or result.mode in ('WAITING_FOR_INITIALIZATION', 'INITIALIZED', 'STOPPED'):
            for history in self._h47_histories:
                history.clear()
            self._h47_previous = [None, None]
            self._h47_watermarks = [None, None]
            self.last_features = tuple(FeatureRow(t, None, None, 'INITIAL_OR_STOP') for _ in range(2))
            return result
        c = self.c
        dt = t - old_t
        command_ok = self._strict_valid(command, t, c.command_timeout_s, 1.000001)
        u = 0.0 if result.command_stale else clip(command.value, -1., 1.)
        # drive_a is the actual native actuator update; v/d are its saved prior.
        acceleration = clip(self.drive_a - self.resistance(old_v) + old_d,
                            -c.max_accel_mps2, c.max_accel_mps2)
        predicted = clip(old_v + dt * acceleration, -c.max_speed_mps, c.max_speed_mps)
        if u <= c.command_deadband and old_v * predicted < 0:
            predicted = 0.0
        mode = 1.0 if u > c.command_deadband else (-1.0 if u < -c.command_deadband else 0.0)
        samples = (front, rear)
        fresh = [self._strict_valid(s, t, c.max_age_s, c.max_speed_mps) for s in samples]
        native_pair = (result.mode == 'FUSED'
                       and result.front_status == result.rear_status == 'ACCEPTED')
        rows = []
        for i, own in enumerate(samples):
            history = self._h47_histories[i]
            while history and t - history[0][0] > HISTORY_SECONDS:
                history.popleft()
            previous = self._h47_previous[i]
            watermark = self._h47_watermarks[i]
            new = fresh[i] and (watermark is None or own.t > watermark)
            reason, values = 'READY', None
            if not new:
                reason = 'NO_NEW_FRESH_SAMPLE'
            elif not native_pair or not all(fresh) or not command_ok:
                reason = 'NATIVE_OR_INPUT_GATE'
            elif abs(predicted) < 1.0 or any(s.value * predicted <= 0 for s in samples):
                reason = 'DIRECTION_OR_LOW_SPEED'
            elif previous is None or not 0 < own.t - previous.t <= c.max_age_s:
                reason = 'RATE_HISTORY_MISSING'
            elif len(history) < 3 or history[-1][0] - history[0][0] < .1 - 1e-12:
                reason = 'PRIOR_HISTORY_MISSING'
            else:
                other = samples[1 - i]
                rate = (own.value - previous.value) / (own.t - previous.t)
                vector = ( (t - own.t) / c.max_age_s,
                           (t - other.t) / c.max_age_s,
                           abs(own.t - other.t) / c.pair_skew_s,
                           abs(rate - acceleration) / c.wheel_rate_limit_mps2,
                           abs(own.value - predicted) / c.innovation_floor_mps,
                           abs(own.value - other.value) / c.disagreement_mps,
                           mode,
                           sum(v for _, v in history) / len(history) )
                if in_domain(vector):
                    values = vector
                else:
                    reason = 'OUT_OF_DOMAIN'
            rows.append(FeatureRow(t, own.t if fresh[i] else None, values, reason))
            # Only raw, genuinely new causal wheel information creates history.
            # This occurs AFTER the current feature vector, excluding self-labeling.
            if new:
                history.append((t, abs(own.value - predicted) / c.innovation_floor_mps))
                self._h47_previous[i] = own
                self._h47_watermarks[i] = own.t
        self.last_features = tuple(rows)
        return result

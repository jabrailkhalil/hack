"""Example extension: causal exponential smoothing. Not a recommended final model."""
import math
from .estimators import WheelEstimator
from .types import Estimate


class ExponentialMeanEstimator:
    def __init__(self):
        self.reset({})

    def reset(self, config):
        self.base = WheelEstimator({**config, "name": "mean"})
        self.tau = float(config.get("time_constant_s", .15))
        if not math.isfinite(self.tau) or self.tau <= 0:
            raise ValueError("time_constant_s must be positive")
        self.previous_ns = None
        self.velocity = None
        self.distance = 0.0

    def update(self, event):
        self.base.update(event)

    def predict(self, time_ns):
        raw = self.base.predict(time_ns)
        if raw.velocity is None:
            return raw
        if self.previous_ns is None:
            self.velocity = raw.velocity
        else:
            dt = (time_ns - self.previous_ns) / 1e9
            alpha = -math.expm1(-dt / self.tau)
            previous_velocity = self.velocity
            self.velocity += alpha * (raw.velocity - self.velocity)
            self.distance += .5 * dt * (previous_velocity + self.velocity)
        self.previous_ns = time_ns
        return Estimate(time_ns, self.velocity, self.distance, raw.status, {**raw.diagnostics, "raw_velocity": raw.velocity})

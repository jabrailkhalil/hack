import importlib
import math
from typing import Mapping, Any
from .types import Event, Estimate, FRONT, REAR, VEHICLE_TOPICS


class WheelEstimator:
    """Diagnostic zero-order-hold baselines, not a slip-resistant vehicle model."""

    def __init__(self, config=None):
        self.reset(config or {})

    def reset(self, config: Mapping[str, Any]):
        self.mode = config.get("name", "mean")
        if self.mode not in {"front", "rear", "mean"}:
            raise ValueError("baseline name must be front, rear or mean")
        self.scale = float(config.get("wheel_scale", 1 / 3.6))
        self.stale_ns = round(float(config.get("stale_after_s", 0.5)) * 1e9)
        if not math.isfinite(self.scale) or self.scale <= 0 or self.stale_ns <= 0:
            raise ValueError("wheel_scale and stale_after_s must be positive")
        self.latest = {}
        self.last_headers = {}
        self.clock_anomalies = 0
        self.rejected_values = 0
        self.last_prediction_ns = None
        self.last_velocity = None
        self.distance = 0.0

    def update(self, event: Event):
        if event.topic not in VEHICLE_TOPICS:
            raise ValueError("GNSS and other external measurements are forbidden estimator inputs")
        previous = self.last_headers.get(event.topic)
        if previous is not None and event.stamp_ns < previous:
            self.clock_anomalies += 1
        self.last_headers[event.topic] = event.stamp_ns
        if event.topic not in (FRONT, REAR):
            return
        velocity = float(event.data["velocity"])
        if not math.isfinite(velocity):
            self.rejected_values += 1
            return
        self.latest[event.topic] = event

    def predict(self, time_ns: int):
        if self.last_prediction_ns is not None and time_ns < self.last_prediction_ns:
            raise ValueError("clock rollback requires an explicit episode reset")
        required = (FRONT, REAR) if self.mode == "mean" else ((FRONT,) if self.mode == "front" else (REAR,))
        diagnostics = {"clock_anomalies": self.clock_anomalies, "rejected_values": self.rejected_values}
        if any(topic not in self.latest for topic in required):
            return Estimate(time_ns, None, None, "unavailable", diagnostics)
        events = [self.latest[topic] for topic in required]
        if any(event.received_ns > time_ns for event in events):
            raise ValueError("attempt to predict with an input not yet received")
        velocity = sum(float(e.data["velocity"]) * self.scale for e in events) / len(events)
        age = max(time_ns - e.received_ns for e in events) / 1e9
        measurement_age = max(time_ns - e.stamp_ns for e in events) / 1e9
        future_header = any(e.stamp_ns > time_ns for e in events)
        diagnostics.update(age_s=age, measurement_age_s=measurement_age, future_header=future_header)
        stale = max(age, measurement_age) * 1e9 > self.stale_ns
        if self.last_prediction_ns is not None:
            self.distance += (time_ns - self.last_prediction_ns) / 1e9 * (velocity + self.last_velocity) / 2
        self.last_prediction_ns, self.last_velocity = time_ns, velocity
        return Estimate(time_ns, velocity, self.distance, "stale" if stale else "ok", diagnostics)


def make_estimator(config):
    """Optional trusted local plugin: factory='module:callable', called without args."""
    if "factory" in config:
        module, name = config["factory"].split(":", 1)
        estimator = getattr(importlib.import_module(module), name)()
        estimator.reset(config)
        return estimator
    return WheelEstimator(config)

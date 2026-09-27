"""Hookable B, with an exact parity test against the unchanged first-round B."""
import math
from collections import deque
import numpy as np
from tram_lab.types import Estimate, FRONT, REAR
from tram_lab.hypotheses.common import dynamics
from tram_lab.hypotheses.concept_b import AdaptiveEKF


class ModularB(AdaptiveEKF):
    def transition(self, command, dt):
        return dynamics(self.v, self.force, self.disturbance, command, dt, self.model, self.gain)

    def predict(self, now):
        if self.time_ns is not None and now < self.time_ns:
            raise ValueError("clock rollback requires explicit reset")
        if self.time_ns is not None and now == self.time_ns:
            return self.last_estimate
        command = self.command(now)
        observations = self.observations(now)
        if self.v is None:
            if not observations:
                return Estimate(now, None, None, "unavailable", {"rejected_values": self.rejected})
            self.v = float(np.mean([o["value"] for o in observations]))
        dt = 0. if self.time_ns is None else (now - self.time_ns) / 1e9
        if dt > 1:
            raise ValueError("prediction gap >1s: use EventClock or reset")
        previous_v = self.v
        features = self.features(command)
        predicted, self.force, acceleration, jac = self.transition(command, dt)
        correction = self.residual(features)
        predicted = max(0., predicted + dt * correction)
        selected = self.select(observations, predicted, now)
        self.v = float(np.clip(self.correct(predicted, selected, dt, jac), 0, 55))
        stopped = self.confirmed_stop(observations, now, command, predicted)
        if stopped:
            self.v = self.force = 0.
        self.s += .5 * dt * (previous_v + self.v)
        self.time_ns = now
        self.history.append((command, self.v))
        diagnostics = {"rejected_values": self.rejected, "clock_anomalies": self.backward_headers,
                       "mode": "stop" if stopped else ("wheel" if selected else "model"),
                       "command_stale": self.command_stale, "accepted_wheels": len(selected),
                       "variance_v": float(self.P[0, 0]), "gain": self.gain,
                       "physics_acceleration": acceleration, "residual_acceleration": correction,
                       "features": features.tolist()}
        self.last_estimate = Estimate(now, self.v, self.s, "ok" if selected else "model", diagnostics)
        return self.last_estimate


def checked_positive(config, key, default):
    value = float(config.get(key, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{key} must be positive and finite")
    return value

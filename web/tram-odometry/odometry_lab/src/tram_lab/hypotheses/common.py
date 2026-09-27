"""Causal inputs and effective longitudinal dynamics shared by the experiments.

The fitted gains are acceleration coefficients, NOT separately identified mass,
wheel radius, gear ratio, motor torque or gradient. No GNSS import is permitted.
"""
from collections import deque
import json
import math
from pathlib import Path
import numpy as np
from ..types import COMMAND, FRONT, REAR, VEHICLE_TOPICS, Estimate

DEFAULT_MODEL = {
    "coefficients": [1.8, 2.8, 0.05, 0.005, 0.0004],
    "tau_traction_s": 0.45, "tau_brake_s": 0.30,
    "power_speed_mps": 18.0,
}


def dynamics(v, force, disturbance, command, dt, model, gain=1.0):
    """One causal step, with an analytic Jacobian for [v, force, disturbance]."""
    kt, kb, c0, c1, c2 = model["coefficients"]
    vp = model["power_speed_mps"]
    u = float(np.clip(command, -1, 1))
    th = math.tanh(v / .3)
    dth = (1 - th * th) / .3
    target = gain * (kt * max(u, 0) / (1 + v / vp) + kb * min(u, 0) * th)
    target_dv = gain * (-kt * max(u, 0) / vp / (1 + v / vp) ** 2 + kb * min(u, 0) * dth)
    drag = c0 * th + c1 * v + c2 * v * abs(v)
    drag_dv = c0 * dth + c1 + 2 * c2 * abs(v)
    tau = model["tau_brake_s"] if u < 0 else model["tau_traction_s"]
    decay = math.exp(-dt / tau)
    force_new = decay * force + (1 - decay) * target
    acceleration = float(np.clip(.5 * (force + force_new) - drag + disturbance, -4, 3))
    velocity = max(0.0, v + dt * acceleration)
    jac = np.array([[1 + dt * (.5 * (1 - decay) * target_dv - drag_dv),
                     .5 * dt * (1 + decay), dt],
                    [(1 - decay) * target_dv, decay, 0.], [0., 0., 1.]])
    return velocity, force_new, acceleration, jac


class CausalInputs:
    """Storage is bounded; messages are used only after receipt, not by header."""
    def __init__(self, config=None):
        self.reset(config or {})

    def reset(self, config):
        self.config = dict(config)
        self.model = dict(DEFAULT_MODEL)
        if config.get("model_file"):
            document = json.loads(Path(config["model_file"]).read_text(encoding="utf-8"))
            self.model.update(document.get("dynamics", document))
        self.model.update(config.get("dynamics", {}))
        coefficients = np.asarray(self.model["coefficients"], dtype=float)
        if coefficients.shape != (5,) or not np.isfinite(coefficients).all() or (coefficients < 0).any():
            raise ValueError("five finite nonnegative effective coefficients required")
        for key in ("tau_traction_s", "tau_brake_s", "power_speed_mps"):
            if not math.isfinite(self.model[key]) or self.model[key] <= 0:
                raise ValueError(f"invalid {key}")
        self.scale = float(config.get("wheel_scale", 1 / 3.6))
        self.stale_s = float(config.get("stale_after_s", .5))
        self.gate = float(config.get("innovation_gate_mps", .75))
        if not all(math.isfinite(x) and x > 0 for x in (self.scale, self.stale_s, self.gate)):
            raise ValueError("scale, stale timeout and gate must be positive and finite")
        self.latest, self.derivatives, self.used = {}, {}, {}
        self.rejected = self.backward_headers = 0
        self.time_ns = None
        self.v = None
        self.s = self.force = self.disturbance = 0.0
        self.gain = 1.0
        self.history = deque(maxlen=11)
        self.stop_since = None
        self.command_stale = True
        self.pair_recovery_since = None
        self.P = np.diag([.2, 1., .1])

    def update(self, event):
        if event.topic not in VEHICLE_TOPICS:
            raise ValueError("only controller and two wheel topics are allowed")
        previous = self.latest.get(event.topic)
        if previous is not None and (event.stamp_ns < previous.stamp_ns or
                                     event.received_ns < previous.received_ns):
            self.backward_headers += 1
            return
        field = "position" if event.topic == COMMAND else "velocity"
        value = float(event.data[field])
        limit = 15 if event.topic == COMMAND else 55 / self.scale
        if not math.isfinite(value) or abs(value) > limit or (event.topic != COMMAND and value < 0):
            self.rejected += 1
            return
        if event.topic != COMMAND and previous is not None:
            dt = (event.stamp_ns - previous.stamp_ns) / 1e9
            if 0 < dt <= 1:
                delta = (value - float(previous.data[field])) * self.scale / dt
                a = float(np.clip(delta, -4, 3))
                alpha = -math.expm1(-dt / .25)
                self.derivatives[event.topic] = self.derivatives.get(event.topic, 0.) * (1 - alpha) + alpha * a
        self.latest[event.topic] = event

    def command(self, now):
        event = self.latest.get(COMMAND)
        self.command_stale = event is None or max(now - event.received_ns, now - event.stamp_ns) / 1e9 > self.stale_s
        if event is not None and event.received_ns > now:
            raise ValueError("future receipt")
        return 0.0 if self.command_stale else float(event.data["position"]) / 15

    def observations(self, now):
        result = []
        for topic in (FRONT, REAR):
            event = self.latest.get(topic)
            if event is None:
                continue
            if event.received_ns > now:
                raise ValueError("future receipt")
            age = max(0., (now - event.stamp_ns) / 1e9, (now - event.received_ns) / 1e9)
            if age > self.stale_s or event.stamp_ns > now + 100_000_000:
                continue
            raw = float(event.data["velocity"]) * self.scale
            projected = max(0., raw + self.derivatives.get(topic, 0.) * min(age, .25))
            result.append({"topic": topic, "value": projected, "raw": raw, "age": age,
                           "key": (event.stamp_ns, event.sequence),
                           "variance": .025 ** 2 + (.25 * age) ** 2})
        return result

    def select(self, observations, predicted, now):
        if not self.config.get("adaptive_trust", True) or predicted is None:
            return observations
        if not observations:
            self.pair_recovery_since = None
            return []
        good = [o for o in observations if abs(o["value"] - predicted) <= self.gate]
        if len(observations) == 2 and abs(observations[0]["value"] - observations[1]["value"]) > .3:
            self.pair_recovery_since = None
            return sorted(good, key=lambda o: abs(o["value"] - predicted))[:1]
        if good:
            self.pair_recovery_since = None
            return good
        # Without independent speed, sustained common slip and model bias cannot
        # be distinguished. Reacquire agreeing sensors after a finite hold, rather
        # than remaining permanently locked out after a long outage.
        if len(observations) == 2:
            if self.pair_recovery_since is None:
                self.pair_recovery_since = now
            if now - self.pair_recovery_since >= 1_000_000_000:
                return observations
        return []

    def confirmed_stop(self, observations, now, command, predicted):
        evidence = (self.config.get("zupt", True) and len(observations) == 2 and
                    all(o["raw"] < .06 for o in observations) and
                    predicted < .4 and command <= 0)
        if not evidence:
            self.stop_since = None
            return False
        if self.stop_since is None:
            self.stop_since = now
        return now - self.stop_since >= 600_000_000

    def features(self, command):
        lag_u = self.history[0][0] if self.history else command
        lag_v = self.history[0][1] if self.history else (self.v or 0.)
        return np.array([1., command, command * abs(command), lag_u,
                         command - lag_u, (self.v or 0.) / 20,
                         ((self.v or 0.) - lag_v) / 3, self.force / 3])

    def residual(self, features):
        return 0.0

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
            raise ValueError("prediction gap >1s: use a regular EventClock or reset")
        previous_v = self.v
        features = self.features(command)
        predicted, self.force, acceleration, jac = dynamics(self.v, self.force, self.disturbance,
                                                            command, dt, self.model, self.gain)
        correction = self.residual(features)
        predicted = max(0., predicted + dt * correction)
        selected = self.select(observations, predicted, now)
        self.v = self.correct(predicted, selected, dt, jac)
        self.v = float(np.clip(self.v, 0, 55))
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

    def correct(self, predicted, selected, dt, jac):
        raise NotImplementedError

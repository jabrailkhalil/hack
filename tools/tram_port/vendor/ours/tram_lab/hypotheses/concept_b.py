"""Concept B: EKF of speed, effective drive acceleration and disturbance.

Distance is a separate trapezoidal integral of published speed, never a GNSS
position update. Covariance is diagnostic, not an empirically calibrated bound.
"""
import numpy as np
from .common import CausalInputs


class AdaptiveEKF(CausalInputs):
    def correct(self, predicted, selected, dt, jac):
        state = np.array([predicted, self.force, self.disturbance])
        self.P = jac @ self.P @ jac.T + np.diag([.12 ** 2, .35 ** 2, .015 ** 2]) * dt
        reliable = len(selected) == 2 and abs(selected[0]["raw"] - selected[1]["raw"]) < .15
        innovations = []
        for observation in selected:
            topic = observation["topic"]
            if self.used.get(topic) == observation["key"]:
                continue  # never count a held sample as a new independent measurement
            self.used[topic] = observation["key"]
            variance = observation["variance"]
            innovation = observation["value"] - state[0]
            if self.config.get("adaptive_trust", True):
                variance *= max(1., (abs(innovation) / .2) ** 2)
            gain = self.P[:, 0] / (self.P[0, 0] + variance)
            state += gain * innovation
            identity = np.eye(3)
            identity[:, 0] -= gain
            self.P = identity @ self.P @ identity.T + variance * np.outer(gain, gain)
            innovations.append(innovation)
        self.P = .5 * (self.P + self.P.T)
        # Limited online adaptation only when independent wheel checks agree.
        command = self.command(self.time_ns + round(dt * 1e9)) if self.time_ns is not None else 0.
        if (self.config.get("adaptation", True) and reliable and innovations and
                not self.command_stale and abs(command) > .2 and state[0] > .5):
            step = float(np.clip(np.mean(innovations) * command * .02, -.002 * dt, .002 * dt))
            self.gain = float(np.clip(self.gain + step, .8, 1.2))
        self.force = float(np.clip(state[1], -4, 3))
        self.disturbance = float(np.clip(state[2], -.4, .4))
        return float(state[0])

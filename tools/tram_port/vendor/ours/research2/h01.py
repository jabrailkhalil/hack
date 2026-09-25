"""H1: factorial age transport x physics, one shared Kalman correction."""
import numpy as np
from .core import ModularB


class Estimator(ModularB):
    def observations(self, now):
        result = super().observations(now)
        if not self.config.get("age_transport", True):
            result = [dict(o, value=o["raw"]) for o in result]
        return result

    def transition(self, command, dt):
        if self.config.get("physics", True):
            return super().transition(command, dt)
        # Constant-acceleration kinematics learned ONLY from the causal wheel past.
        a = float(np.mean(list(self.derivatives.values()))) if self.derivatives else 0.
        self.disturbance = self.force = 0.
        return max(0., self.v + dt*a), 0., a, np.eye(3)

    def correct(self, predicted, selected, dt, jac):
        result = super().correct(predicted, selected, dt, jac)
        if not self.config.get("physics", True):
            self.disturbance = self.force = 0.
        return result

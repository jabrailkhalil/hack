"""Concept A: bounded model forecast plus age-weighted robust wheel fusion."""
from .common import CausalInputs


class RobustEstimator(CausalInputs):
    def correct(self, predicted, selected, dt, jac):
        if not selected:
            self.P[0, 0] += dt * .3
            return predicted
        weights = [1 / o["variance"] for o in selected]
        measurement = sum(w * o["value"] for w, o in zip(weights, selected)) / sum(weights)
        self.P[0, 0] = 1 / sum(weights)
        # On healthy data do not impose an arbitrary smoothing lag.
        return measurement

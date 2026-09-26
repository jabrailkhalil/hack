"""R4-H35: one actuator state, separate release time constant. Stdlib only.

Loaded in the explicitly patched private package by factory.py. The original
canonical observer, readout, parameters and evaluator are not overwritten.
"""
import math
from .guarded_readout import GuardedReadoutObserver


def release_phase(x: float, target: float) -> bool:
    """No near-zero deadband: exactly zero is a growth initial condition."""
    return x != 0.0 and (
        (x > 0.0 and target < 0.0) or (x < 0.0 and target > 0.0)
        or abs(target) < abs(x))


def advance_release(x: float, target: float, dt: float,
                    base_tau: float, ratio: float) -> float:
    """Exact piecewise-constant-target actuator endpoint, not a new v integral.

    At an opposite-sign zero crossing the release ODE is continued from zero
    using base_tau for the rest of the same step. No output tick is inserted.
    """
    if dt == 0.0:
        return x
    tau = base_tau * ratio
    opposite = (x > 0.0 and target < 0.0) or (x < 0.0 and target > 0.0)
    if opposite:
        q = abs(x) / abs(target)
        # Avoid overflowing the ratio for a finite, subnormal target.
        crossing = tau * (math.log1p(q) if math.isfinite(q)
                          else math.log(abs(x) + abs(target)) - math.log(abs(target)))
        if dt >= crossing:
            return target * (1.0 - math.exp(-(dt - crossing) / base_tau))
    if not release_phase(x, target):
        tau = base_tau
    alpha = 1.0 - math.exp(-dt / tau)
    return x + alpha * (target - x)


class ReleaseObserver(GuardedReadoutObserver):
    """Full v8 with one immutable parameter, no extra dynamical histories."""
    def __init__(self, config=None, *, readout=None, release_ratio=1.0):
        if not math.isfinite(release_ratio) or release_ratio not in (0.5, 1.0, 2.0):
            raise ValueError('R4-H35 permits release_ratio 0.5, 1 (off), or 2')
        self.release_ratio = float(release_ratio)
        super().__init__(config, readout=readout)

    def _advance_drive(self, target, dt, command_stale):
        if self.release_ratio == 1.0 or command_stale:
            return super()._advance_drive(target, dt, command_stale)
        return advance_release(self.drive_a, target, dt,
                               self.c.actuator_tau_s, self.release_ratio)

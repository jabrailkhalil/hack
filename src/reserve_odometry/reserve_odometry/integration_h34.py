"""H34 opt-in quadrature. Controller/front/rear only; constant memory.

The exact held-target drive integral is not an exact nonlinear vehicle model.
Apply research/R4_H34/hooks.patch in an isolated worktree before using this class.
"""
import math
from .core import clip
from .guarded_readout import GuardedReadoutObserver


def mean_fraction(x: float) -> float:
    """Mean fraction of first-order transition, continuous and stable at x=0."""
    if not math.isfinite(x) or x < 0:
        raise ValueError('Expected finite nonnegative dt/tau')
    if x < 1e-4:
        return x * (0.5 + x * (-1.0 / 6 + x * (1.0 / 24 +
                    x * (-1.0 / 120 + x / 720))))
    return 1.0 + math.expm1(-x) / x


def integrate(dt, tau, drive, velocity, target, disturbance, resistance,
              max_accel, max_speed):
    """Return end drive, effective pre-correction acceleration, predicted v."""
    if not math.isfinite(dt) or dt < 0 or not math.isfinite(tau) or tau <= 0:
        raise ValueError('Expected finite dt >= 0 and finite tau > 0')
    if dt == 0:
        return drive, clip(drive-resistance(velocity)+disturbance,
                           -max_accel,max_accel), velocity
    change = target - drive
    x = dt / tau
    mean_half = drive + change * mean_fraction(0.5 * x)
    half_accel = clip(mean_half - resistance(velocity) + disturbance,
                      -max_accel,max_accel)
    midpoint = clip(velocity + 0.5 * dt * half_accel,-max_speed,max_speed)
    mean_drive = drive + change * mean_fraction(x)
    acceleration = clip(mean_drive - resistance(midpoint) + disturbance,
                        -max_accel,max_accel)
    end_drive = drive - math.expm1(-x) * change
    predicted = clip(velocity + dt * acceleration,-max_speed,max_speed)
    return end_drive, acceleration, predicted


class DiscretizationObserver(GuardedReadoutObserver):
    """A is exact legacy dispatch; B uses integrated drive/midpoint resistance."""
    def __init__(self, config=None, *, readout=None, scheme='B'):
        if scheme not in ('A','B'):
            raise ValueError('scheme must be A or B')
        if not hasattr(GuardedReadoutObserver,'_propagate_h34'):
            raise RuntimeError('Apply the isolated H34 hooks patch first')
        self.scheme = scheme
        super().__init__(config,readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity,position=position)
        self._effective_acceleration_h34 = 0.0

    def _propagate_h34(self,dt,u):
        if self.scheme == 'A':
            return super()._propagate_h34(dt,u)
        c = self.c
        self.drive_a, a, predicted = integrate(
            dt,c.actuator_tau_s,self.drive_a,self.v,self.drive_target(u,self.v),
            self.disturbance,self.resistance,c.max_accel_mps2,c.max_speed_mps)
        self._effective_acceleration_h34 = a
        return a,predicted

    def _readout_acceleration_h34(self,old_v,old_disturbance):
        if self.scheme == 'A':
            return super()._readout_acceleration_h34(old_v,old_disturbance)
        return self._effective_acceleration_h34

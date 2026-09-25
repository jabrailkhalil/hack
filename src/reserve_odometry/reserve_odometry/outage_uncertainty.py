"""H18 research-only covariance transport over canonical guarded v7.

No mean dynamics, readout, guards, sensor history, or runtime dependencies are
replaced. This episode-wise consider approximation is NOT a calibrated CI.
Instantiate explicitly; the canonical ROS launch is intentionally unchanged.
"""
import math
from .core import Config, clip
from .guarded_readout import GuardedReadoutObserver


class OutageUncertaintyObserver(GuardedReadoutObserver):
    def __init__(self, config=None, *, readout=None, pdd=0.0, enabled=True):
        config = config or Config()
        if not math.isfinite(pdd) or not 0.0 <= pdd <= config.disturbance_limit_mps2 ** 2:
            raise ValueError('Pdd must be finite and within the configured disturbance scale')
        self._h18_pdd = float(pdd)
        self._h18_enabled = bool(enabled)
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._h18_pvd = 0.0
        self._h18_last_trust = None
        self._h18_active = False
        self._h18_injection = 0.0
        self._h18_last_gain = 0.0
        self._h18_prior = self.pv

    def step(self, t, command=None, front=None, rear=None):
        if not self._h18_enabled or self._h18_pdd == 0.0:
            return super().step(t, command, front, rear)
        # Do not modify covariance before the inherited time checks can fail.
        if (not math.isfinite(t) or (self.t is not None and
                (t <= self.t or t - self.t > self.c.max_step_s + 1e-9))):
            return super().step(t, command, front, rear)
        dt = 0.0 if self.t is None else t - self.t
        self._h18_injection = 0.0
        self._h18_last_gain = 0.0
        if self.initialized and self.t is not None and self._h18_last_trust is not None:
            boundary = self._h18_last_trust + self.c.max_age_s
            h = max(0.0, t - max(self.t, boundary))
            if h > 0.0:
                if not self._h18_active:
                    # Unknown cross correlation, not an independence assertion.
                    # Largest forward scalar variance for these two marginals.
                    self._h18_pvd = math.sqrt(self.pv * self._h18_pdd)
                    self._h18_active = True
                extra = 2.0 * h * self._h18_pvd + h * h * self._h18_pdd
                self.pv += extra
                self._h18_pvd += h * self._h18_pdd
                self._h18_injection = extra
        effective_old_pv = self.pv
        estimate = super().step(t, command, front, rear)
        self._h18_prior = effective_old_pv + self.c.process_noise_v * dt * (
            4.0 if estimate.command_stale else 1.0)
        accepted = [sample for sample, status in zip((front, rear),
                    (estimate.front_status, estimate.rear_status)) if status == 'ACCEPTED' and sample is not None]
        if accepted:
            if estimate.mode != 'INITIALIZED':
                # Scalar Joseph identity; preserve the inherited variance floor.
                # This is also how guarded_readout reconstructs its scalar gain.
                factor = clip(self.pv / self._h18_prior, 0.0, 1.0)
                self._h18_last_gain = 1.0 - factor
                self._h18_pvd *= factor
            newest = max(x.t for x in accepted)
            self._h18_last_trust = newest if self._h18_last_trust is None else max(self._h18_last_trust, newest)
            self._h18_active = False
        if estimate.mode == 'STOPPED':
            self._h18_active = False
        # No reduction for bounded reacquisition: it is not a fresh KF update.
        # No Pvv/Pdd reset at recovery or STOPPED; uncertainty is not discarded.
        determinant = self.pv * self._h18_pdd - self._h18_pvd ** 2
        if not math.isfinite(determinant) or determinant < -1e-10 * max(
                1.0, self.pv * self._h18_pdd):
            raise ArithmeticError('H18 covariance lost PSD/finite invariant')
        return estimate

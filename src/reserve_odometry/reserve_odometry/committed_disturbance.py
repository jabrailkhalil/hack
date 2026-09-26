"""R3-H27: opt-in output-only committed disturbance; full native v8 is unchanged.

The inherited state remains canonical. Consume returned Estimate.v/s, never
self.v/s as the corrected output. No reference, future data or fault flags.
"""
from dataclasses import replace
import math
from .core import clip
from .guarded_readout import GuardedReadoutObserver
from .committed_history import History, command_mode


class CommittedDisturbanceObserver(GuardedReadoutObserver):
    def __init__(self, config, *, readout, lag_s, threshold, enabled=True):
        if lag_s not in (.2, .4):
            raise ValueError('Only preregistered lag .2/.4s is allowed')
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError('threshold must be finite and positive')
        self.lag_s = lag_s
        self.threshold = threshold
        self.enabled = bool(enabled)
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._committed_history = History()
        self._committed_d = None
        self._committed_dv = 0.0
        self._committed_ds = 0.0
        self._committed_sigma_s = 0.0
        self._committed_applied_da = 0.0
        self._committed_opened = False
        self._committed_eligible_entry = False
        self._committed_native_estimate = None

    def step(self, t, command=None, front=None, rear=None):
        if not self.enabled:
            return super().step(t, command, front, rear)
        old_t, old_v, old_d, old_pv = self.t, self.v, self.disturbance, self.pv
        old_pair = self.adapt_previous
        old_reacquire = self.reacquire_previous
        old_dv = self._committed_dv
        estimate = super().step(t, command, front, rear)
        self._committed_native_estimate = estimate
        closed, _, opened = self._committed_history.observe(
            t, command, front, rear, estimate, old_pair, old_d, self.c, self.threshold)
        self._committed_applied_da = 0.0
        self._committed_opened = opened is not None
        self._committed_eligible_entry = False
        if closed is not None or self._committed_history.episode is None:
            self._committed_d = None
        if opened is not None:
            proposal = opened['proposals'][str(self.lag_s)]
            self._committed_d = proposal['checkpoint'] if proposal['eligible'] else None
            self._committed_eligible_entry = proposal['eligible']
        if old_t is None or estimate.mode in ('WAITING_FOR_INITIALIZATION', 'INITIALIZED'):
            self._committed_dv = 0.0
            return estimate
        dt = t-old_t  # canonical step validated increasing bounded time
        c = self.c
        if estimate.mode == 'MODEL_ONLY' and self._committed_d is not None:
            g = self.drive_a-self.resistance(old_v)
            delta_a = (clip(g+self._committed_d, -c.max_accel_mps2, c.max_accel_mps2)
                       -clip(g+old_d, -c.max_accel_mps2, c.max_accel_mps2))
            self._committed_dv += dt*delta_a
            self._committed_applied_da = delta_a
        elif estimate.mode in ('FUSED', 'SINGLE_WHEEL'):
            p_prior = old_pv+c.process_noise_v*dt*(4.0 if estimate.command_stale else 1.0)
            gain = clip(1.0-self.pv/p_prior, 0.0, 1.0)
            self._committed_dv *= 1.0-gain
        elif estimate.mode == 'REACQUIRING':
            pair_dt = (self.reacquire_previous.t-old_reacquire.t
                       if old_reacquire and self.reacquire_previous else 0.0)
            limit = c.reacquire_step_mps*min(1.0, max(0.0, pair_dt)/.1)
            self._committed_dv += clip(-self._committed_dv, -limit, limit)
        elif estimate.mode == 'STOPPED':
            self._committed_dv = 0.0
        # Invalid/mode-changed command cancels future acceleration replacement,
        # but a prior velocity correction is not silently discarded.
        velocity = clip(estimate.v+self._committed_dv, -c.max_speed_mps, c.max_speed_mps)
        if estimate.v*velocity <= 0.0:
            velocity = estimate.v
        self._committed_dv = velocity-estimate.v
        self._committed_ds += .5*(old_dv+self._committed_dv)*dt
        self._committed_sigma_s += .5*(abs(old_dv)+abs(self._committed_dv))*dt
        if self._committed_dv == 0.0 and self._committed_ds == 0.0 and self._committed_sigma_s == 0.0:
            return estimate
        self.last_estimate = replace(
            estimate, v=velocity, s=estimate.s+self._committed_ds,
            a=estimate.a+(self._committed_dv-old_dv)/dt,
            variance_v=estimate.variance_v+self._committed_dv**2,
            variance_s=(math.sqrt(estimate.variance_s)+self._committed_sigma_s)**2)
        return self.last_estimate

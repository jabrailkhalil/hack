"""I01: one preregistered causal, state-aligned reserve readout.

Research-only. Published plan commit 2b6277fe1c3dda08b17c4858deb1b8cea8f1a951.
The original main observer is unmodified. The shadow receives exactly the same
causal inputs. There are no references, model-selection knobs or fault oracles.
"""
from dataclasses import fields, replace
import math
from typing import Optional
from reserve_odometry.core import Config, Estimate, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig


class CausalReserveObserver(GuardedReadoutObserver):
    def __init__(self, config: Config, *, readout: ReadoutConfig,
                 shadow_config: Config, enabled: bool = True):
        if not isinstance(config, Config) or not isinstance(shadow_config, Config):
            raise TypeError('Explicit main and frozen shadow Config required')
        if not isinstance(readout, ReadoutConfig) or type(enabled) is not bool:
            raise TypeError('Explicit readout and boolean enabled required')
        allowed = {'total_motor_torque_nm', 'max_power_w', 'max_brake_force_n'}
        changed = {f.name for f in fields(Config)
                   if getattr(config, f.name) != getattr(shadow_config, f.name)}
        if changed - allowed:
            raise ValueError('Shadow may change only frozen torque/power/brake')
        self._reserve_enabled = enabled and bool(changed)
        self._reserve_shadow = GuardedReadoutObserver(shadow_config, readout=readout)
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._reserve_shadow.reset(velocity=velocity, position=position)
        self._reserve_episode = False
        self._reserve_anchor = 0.0
        self._reserve_previous_difference = 0.0
        self._reserve_dv = 0.0
        self._reserve_ds = 0.0
        self._reserve_sigma_s = 0.0
        self._reserve_shadow_v = 0.0

    def _reserve_healthy(self, e: Estimate, t: float,
                         front: Optional[Sample], rear: Optional[Sample]) -> bool:
        return (self._valid(front, t, self.c.max_age_s)
                and self._valid(rear, t, self.c.max_age_s)
                and abs(front.value) <= self.c.max_speed_mps
                and abs(rear.value) <= self.c.max_speed_mps
                and abs(front.t - rear.t) <= self.c.pair_skew_s
                and abs(front.value - rear.value) <= self.c.disagreement_mps
                and e.front_status in ('ACCEPTED', 'DUPLICATE_OR_OLD')
                and e.rear_status in ('ACCEPTED', 'DUPLICATE_OR_OLD')
                and e.mode != 'REACQUIRING')

    def step(self, t: float, command: Optional[Sample] = None,
             front: Optional[Sample] = None, rear: Optional[Sample] = None) -> Estimate:
        old_t = self.t
        old_delta = self._reserve_dv
        # No shadow value is fed back into any inherited numerical state.
        base = super().step(t, command, front, rear)
        if not self._reserve_enabled:
            return base
        shadow = self._reserve_shadow.step(t, command, front, rear)
        difference = shadow.v - base.v
        self._reserve_shadow_v = shadow.v
        eligible = (old_t is not None and not base.command_stale
                    and base.mode not in ('WAITING_FOR_INITIALIZATION', 'INITIALIZED', 'STOPPED')
                    and not self._reserve_healthy(base, t, front, rear))
        if eligible:
            if not self._reserve_episode:
                self._reserve_anchor = self._reserve_previous_difference
            self._reserve_episode = True
            delta = difference - self._reserve_anchor
        else:
            self._reserve_episode = False
            delta = 0.0
        self._reserve_previous_difference = difference
        if old_t is None or base.mode in ('WAITING_FOR_INITIALIZATION', 'INITIALIZED'):
            self._reserve_dv = 0.0
            return base
        velocity = clip(base.v + delta, -self.c.max_speed_mps, self.c.max_speed_mps)
        if base.v * velocity <= 0.0:
            velocity = base.v
        delta = velocity - base.v
        dt = t - old_t  # validated by the unchanged main observer
        self._reserve_dv = delta
        self._reserve_ds += 0.5 * (old_delta + delta) * dt
        self._reserve_sigma_s += 0.5 * (abs(old_delta) + abs(delta)) * dt
        # Recovery removes velocity correction but NEVER the distance integral.
        # main.last_estimate remains main's output for complete state isolation.
        return replace(base, v=velocity, s=base.s + self._reserve_ds,
                       a=base.a + (delta - old_delta) / dt,
                       variance_v=base.variance_v + delta * delta,
                       variance_s=(math.sqrt(base.variance_s) + self._reserve_sigma_s) ** 2)

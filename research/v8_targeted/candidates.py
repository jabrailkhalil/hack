"""Fixed v8 candidates. Config variants are static, never switched at dropout."""
from dataclasses import asdict, replace
from functools import partial
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/reserve_odometry'))
from reserve_odometry.core import Config, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

VARIANTS = {
    'main': {},
    'brake_090': {'max_brake_force_n': .90},
    'brake_110': {'max_brake_force_n': 1.10},
    'brake_120': {'max_brake_force_n': 1.20},
    'traction_090': {'total_motor_torque_nm': .90, 'max_power_w': .90},
    'power_090': {'max_power_w': .90},
    'torque_090': {'total_motor_torque_nm': .90},
    'carry_readout': {},
    'brake_094': {'max_brake_force_n': .94},
    'brake_095': {'max_brake_force_n': .95},
    'brake_096': {'max_brake_force_n': .96},
    'disturbance_070': {'disturbance_limit_mps2': .7/.6},
    'disturbance_080': {'disturbance_limit_mps2': .8/.6},
    'disturbance_100': {'disturbance_limit_mps2': 1.0/.6},
    'disturbance_120': {'disturbance_limit_mps2': 1.2/.6},
}


class CarryReadout(GuardedReadoutObserver):
    """Carry the past timestamp correction through genuine missing-wheel intervals.

    Additional output-only delta; baseline core, guards and raw integral untouched.
    Returned s always integrates the returned v. No s reset at recovery.
    """
    def __init__(self, config=None, *, readout=None, enabled=True):
        self.enabled = enabled
        super().__init__(config, readout=readout)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self._carry_v = self._carry_s = 0.0
        self._carry_active = False
        self._carry_activations = 0

    def step(self, t, command=None, front=None, rear=None):
        old_t, old_pv = self.t, self.pv
        old_extra, old_readout = self._carry_v, self._velocity_correction
        e = super().step(t, command, front, rear)
        if not self.enabled or old_t is None:
            return e
        dt = t-old_t
        statuses = (e.front_status, e.rear_status)
        ordinary_loss = (e.mode == 'MODEL_ONLY' and not e.command_stale and
                         all(s in ('MISSING_OR_STALE','DUPLICATE_OR_OLD') for s in statuses))
        if ordinary_loss:
            if not self._carry_active and 'MISSING_OR_STALE' in statuses:
                self._carry_v += old_readout
                self._carry_active = True
                if old_readout != 0.0: self._carry_activations += 1
        elif e.mode in ('FUSED', 'SINGLE_WHEEL'):
            p_prior = old_pv+self.c.process_noise_v*dt*(4 if e.command_stale else 1)
            self._carry_v *= clip(e.variance_v / p_prior, 0.0, 1.0)
            self._carry_active = False
        elif not (e.mode == 'MODEL_ONLY' and all(s == 'DUPLICATE_OR_OLD' for s in statuses)):
            self._carry_v = 0.0
            self._carry_active = False
        velocity = clip(e.v+self._carry_v, -self.c.max_speed_mps, self.c.max_speed_mps)
        if e.v*velocity <= 0: velocity=e.v
        self._carry_v = velocity-e.v
        self._carry_s += .5*(old_extra+self._carry_v)*dt
        self.last_estimate = replace(e, v=velocity, s=e.s+self._carry_s,
            a=e.a+(self._carry_v-old_extra)/dt, variance_v=e.variance_v+self._carry_v**2)
        return self.last_estimate


def configuration(name):
    if name not in VARIANTS: raise ValueError('Unknown fixed candidate '+name)
    p = json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
    c = Config(**p['config'])
    for k, factor in VARIANTS[name].items(): setattr(c,k,getattr(c,k)*factor)
    c.__post_init__()
    return c, ReadoutConfig(**p['readout'])


def models(names=None):
    out = {}
    for name in names or VARIANTS:
        c, readout = configuration(name)
        cls = CarryReadout if name == 'carry_readout' else GuardedReadoutObserver
        out[name] = (partial(cls, readout=readout), c)
    return out


def manifest(names=None):
    return {name: {'config': asdict(configuration(name)[0]),
                   'readout': asdict(configuration(name)[1]),
                   'class': 'CarryReadout' if name == 'carry_readout' else 'GuardedReadoutObserver'}
            for name in names or VARIANTS}

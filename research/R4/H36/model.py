"""H36 offline conditional integral identification; no changes to runtime.

Wheel paths are offline regressors/pseudotargets, not recursive predictions.
The nuisance acceleration is eliminated per window and never exported.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from scipy.signal import lfilter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/finalization'))
import evaluate as ev
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

BASE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
TREE = 'eae49a504bc59b5c9b408445150bef32e111956f'
PLAN_SHA = 'a7e3436adbb7cfc614d8ea367205103cac8c786c'
DT, BIN, WARM, STEPS = .05, .5, 100, 200
LOW, HIGH = np.array([.05, 1., .05]), np.array([5., 100., 5.])
PARAMETERS = ('force_per_mass', 'power_per_mass', 'brake_per_mass')
FIELDS = ('total_motor_torque_nm', 'max_power_w', 'max_brake_force_n')


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, allow_nan=False)
        fh.write('\n')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for block in iter(lambda: fh.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def profile():
    values = {}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and key.startswith(('model.', 'readout.')):
            values[key] = float(value)
    cfg = Config(**{k[6:]: v for k,v in values.items() if k.startswith('model.')})
    readout = ReadoutConfig(**{k[8:]: v for k,v in values.items() if k.startswith('readout.')})
    assert cfg.common_mode_quarantine_s == 1.5 and cfg.adaptation_tau_s == .5
    assert cfg.wheel_time_compensation == 0 and readout.gain == 1 and readout.holdoff_s == .5
    return cfg, readout


def theta0():
    c, _ = profile()
    return np.array([c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m/c.mass_kg,
                     c.max_power_w/c.mass_kg, c.max_brake_force_n/c.mass_kg])


def configuration(theta=None):
    c, _ = profile()
    if theta is None:
        return c
    x = np.asarray(theta, float)
    if x.shape != (3,) or not np.all(np.isfinite(x)) or np.any(x<LOW) or np.any(x>HIGH):
        raise ValueError('Invalid force coefficients')
    c.total_motor_torque_nm = float(x[0]*c.mass_kg*c.wheel_radius_m/(c.efficiency*c.gear_ratio))
    c.max_power_w = float(x[1]*c.mass_kg)
    c.max_brake_force_n = float(x[2]*c.mass_kg)
    c.__post_init__()
    return c


def factory(theta=None, *, enabled=True):
    # No subclass, nuisance lookup, per-bag parameter, or new runtime state.
    c = configuration(theta if enabled else None)
    return GuardedReadoutObserver(c, readout=profile()[1])


def physical(theta, u, v, *, return_drive=False):
    """Integrate along OFFLINE wheel path; prefix through index100 is causal warmup.

    Inputs each have 201 values at anchor-5,...,anchor+5. Output has ten
    half-second physical increments. Same exponential drive update and clipping
    as v8 at b=0, with observed rather than recursively predicted speed.
    """
    u, v = np.asarray(u, float), np.asarray(v, float)
    if u.ndim != 2 or u.shape != v.shape or u.shape[1] != STEPS+1:
        raise ValueError('Expected N by 201 paths')
    c = configuration(theta)
    q = np.clip((np.abs(u[:,1:])-c.command_deadband)/(1-c.command_deadband),0,1)**c.command_exponent
    oldv = v[:,:-1]
    target = np.where(u[:,1:]>=0,
        c.travel_direction*q*np.minimum(theta[0],theta[1]/np.maximum(np.abs(oldv),1.)),
        -np.tanh(oldv/.2)*q*theta[2])
    alpha = 1-np.exp(-DT/c.actuator_tau_s)
    drive = lfilter([alpha],[1.,-(1-alpha)],target,axis=1)
    resistance = (c.rolling_force_n*np.tanh(oldv/.2)+c.quadratic_drag_n_s2_m2*oldv*np.abs(oldv))/c.mass_kg
    acceleration = np.clip(drive-resistance,-c.max_accel_mps2,c.max_accel_mps2)
    increments = (DT*acceleration[:,WARM:]).reshape(-1,10,10).sum(axis=2)
    if return_drive:
        return increments, drive[:,WARM-1]
    return increments


def profile_load(error, limit=None):
    """Unique bounded soft-L1 minimizer for error=physical minus wheel increment.

    All bins have the same duration and scale. Monotone bisection handles both
    interior roots and boundary optima, without adding a prior penalty.
    """
    error = np.asarray(error,float)
    if error.ndim != 2 or error.shape[1] == 0 or not np.all(np.isfinite(error)):
        raise ValueError('Finite nonempty increment matrix required')
    c,_ = profile()
    limit = c.disturbance_limit_mps2 if limit is None else float(limit)
    if not np.isfinite(limit) or limit < 0:
        raise ValueError('Invalid load bound')
    lo, hi = np.full(len(error),-limit), np.full(len(error),limit)
    sigma = np.sqrt(2.)*c.wheel_sigma_mps
    for _ in range(60):
        mid = (lo+hi)*.5
        r = (error+BIN*mid[:,None])/sigma
        grad = np.sum(r/np.hypot(1.,r),axis=1)
        lo = np.where(grad<0,mid,lo)
        hi = np.where(grad>=0,mid,hi)
    return (lo+hi)*.5


def transformed(r):
    # sign(r)*sqrt(soft_l1(r**2)); stable also near r=0.
    return r*np.sqrt(2./(np.hypot(1.,r)+1.))


def weights(meta):
    groups = {m['group'] for m in meta}
    phases = {g:{m['phase'] for m in meta if m['group']==g} for g in groups}
    counts = Counter((m['group'],m['phase']) for m in meta)
    return np.array([1/(len(groups)*len(phases[m['group']])*counts[m['group'],m['phase']]) for m in meta])


def residual(theta, data, nuisance=True):
    error = physical(theta,data['u'],data['v'])-data['y']
    b = profile_load(error) if nuisance else np.zeros(len(error))
    sigma = np.sqrt(2.)*profile()[0].wheel_sigma_mps
    r = (error+BIN*b[:,None])/sigma
    return (transformed(r)*np.sqrt(weights(data['meta'])[:,None]/r.shape[1])).ravel()


def rank_report(theta, data):
    # Always eliminate the FREE constant component. Bounds must not create rank.
    scale = theta0()
    jac = []
    for k in range(3):
        hi,lo = np.array(theta,float).copy(),np.array(theta,float).copy()
        step = 1e-4*scale[k]
        hi[k] = min(HIGH[k],hi[k]+step)
        lo[k] = max(LOW[k],lo[k]-step)
        d = (physical(hi,data['u'],data['v'])-physical(lo,data['u'],data['v']))/(hi[k]-lo[k])
        jac.append(d*scale[k]/(np.sqrt(2.)*profile()[0].wheel_sigma_mps))
    J = np.stack(jac,axis=-1)
    J -= J.mean(axis=1,keepdims=True)
    flat = J.reshape(-1,3)
    s = np.linalg.svd(flat,compute_uv=False)
    rank = int(np.sum(s>(s[0]*1e-10 if s[0]>0 else 1e-10)))
    groups = sorted({m['group'] for m in data['meta']})
    by_group = {}
    for g in groups:
        subset = J[[m['group']==g for m in data['meta']]]
        by_group[g] = np.sqrt(np.mean(subset**2,axis=(0,1))).tolist()
    support = [sum(v[k]>=.001 for v in by_group.values()) for k in range(3)]
    phase_groups = {p:len({m['group'] for m in data['meta'] if m['phase']==p}) for p in ('traction','braking','coast')}
    condition = float(s[0]/s[-1]) if s[-1]>0 else None
    minimum = float(s[-1]/np.sqrt(len(flat)))
    ok = rank==3 and condition is not None and condition<=1e4 and minimum>=.001 and min(support)>=3
    return dict(passed=bool(ok and min(phase_groups.values())>=3),rank=rank,
        singular_values=s.tolist(),min_singular_rms=minimum,condition=condition,
        support_groups_per_parameter=support,phase_groups=phase_groups,
        per_group_projected_column_rms=by_group,
        windows=len(data['meta']),original_groups=len(groups))

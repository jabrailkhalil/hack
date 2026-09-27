"""R7-A1: bounded causal MHE. No labels, identity, fault schedule or v8 fusion.

Only the newest optimized state is published. Previously published distance is
never recomputed. All numerical constants are preregistered in PLAN.md.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, fields
from pathlib import Path
import math
import sys
import time
from typing import Callable
import numpy as np
from scipy.optimize import least_squares
from scipy.linalg import cho_factor, cho_solve
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/reserve_odometry'))
from reserve_odometry.core import Config, Estimate, Sample, Observer, clip
from reserve_odometry.guarded_readout import ReadoutConfig

VARIANTS = {'V1': (3.0, .01), 'V2': (3.0, .03), 'V3': (3.0, .10), 'V4': (1.5, .03)}
SOLVER = dict(method='trf', jac='2-point', loss='linear', max_nfev=20,
              ftol=1e-6, xtol=1e-6, gtol=1e-6, x_scale=1.)
BOUNDS = np.array([-40., -3., -.6]), np.array([40., 3., .6])
ARRIVAL = np.array([.5, .5, .3])


def profile():
    model, readout = {}, {}
    p = ROOT / 'src/reserve_odometry/config/champion_v8.yaml'
    for line in p.read_text().splitlines():
        key, sep, val = line.strip().partition(':')
        if sep and key.startswith('model.'):
            model[key[6:]] = float(val)
        elif sep and key.startswith('readout.'):
            readout[key[8:]] = float(val)
    if set(model) != {f.name for f in fields(Config)}:
        raise ValueError('Incomplete pinned profile')
    return Config(**model), ReadoutConfig(**readout)


def pseudo_huber(e):
    """Signed square-root residual; algebraically exact, stable near zero."""
    return e * np.sqrt(2. / (np.sqrt(1. + (e / 3.) ** 2) + 1.))


def physics(x, u, dt, c):
    """Vectorized literal canonical physical equation, not observation fusion."""
    x = np.asarray(x, dtype=float)
    v, a, d = x[..., 0], x[..., 1], x[..., 2]
    q = np.minimum(1., np.maximum(0., (np.abs(u)-c.command_deadband)/(1-c.command_deadband))) ** c.command_exponent
    force = np.minimum(c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m,
                       c.max_power_w/np.maximum(np.abs(v), 1.))
    target = np.where(np.asarray(u) >= 0, c.travel_direction*q*force/c.mass_kg,
                      -np.tanh(v/.20)*q*c.max_brake_force_n/c.mass_kg)
    ap = a + (1.-math.exp(-dt/c.actuator_tau_s))*(target-a)
    resist = (c.rolling_force_n*np.tanh(v/.20)+c.quadratic_drag_n_s2_m2*v*np.abs(v))/c.mass_kg
    am = np.clip(ap-resist+d, -c.max_accel_mps2, c.max_accel_mps2)
    vp = np.clip(v+dt*am, -c.max_speed_mps, c.max_speed_mps)
    vp = np.where((np.asarray(u) <= c.command_deadband) & (v*vp < 0), 0., vp)
    return np.stack((vp, ap, d), axis=-1)


@dataclass(frozen=True)
class Measurement:
    z: float
    sigma: float
    ids: tuple[tuple[int, float], ...]


class Cost:
    """Pure residual with a deterministic batched numerical-difference map."""
    def __init__(self, config, controls, arrival, measurements, sigma_d):
        self.c = config
        self.u = np.asarray(controls[:-1], float)
        self.arrival = np.asarray(arrival, float)
        self.n = len(controls)
        self.sigma = np.array([math.sqrt(config.process_noise_v*.1), .05, sigma_d])
        nodes, zs, sigmas, ids = [], [], [], []
        for k, mm in enumerate(measurements):
            for m in mm:
                nodes.append(k); zs.append(m.z); sigmas.append(m.sigma); ids.extend(m.ids)
        if len(ids) != len(set(ids)):
            raise AssertionError('A raw sample entered the horizon twice')
        self.ids = tuple(ids)
        self.nodes = np.asarray(nodes, dtype=int)
        self.z = np.asarray(zs, float)
        self.ms = np.asarray(sigmas, float)
        self.points = 0
        self.batch_calls = 0

    def batch(self, x):
        x = np.asarray(x, float).reshape(-1, self.n, 3)
        prior = (x[:, 0]-self.arrival)/ARRIVAL
        pred = physics(x[:, :-1], self.u[None, :], .1, self.c)
        dynamic = ((x[:, 1:]-pred)/self.sigma).reshape(len(x), -1)
        wheel = pseudo_huber((self.z[None, :]-x[:, self.nodes, 0])/self.ms[None, :])
        return np.concatenate((prior, dynamic, wheel), axis=1)

    def __call__(self, x):
        self.points += 1
        return self.batch(x)[0]

    def numerical_map(self, fun, iterable):
        # SciPy supplies independent 2-point perturbations of our same residual.
        # Return the same f(x) per point; no change to perturbations or Jacobian.
        xs = list(iterable)
        self.points += len(xs)
        self.batch_calls += 1
        return list(self.batch(np.asarray(xs))) if xs else []


class MovingHorizonObserver:
    def __init__(self, config=None, variant='V2', telemetry_sink: Callable | None=None):
        if variant not in VARIANTS:
            raise ValueError('Unknown preregistered variant')
        self.c = config or profile()[0]
        self.variant = variant
        self.horizon, self.sd = VARIANTS[variant]
        self.max_nodes = int(round(self.horizon/.1))+1
        self.telemetry_sink = telemetry_sink
        # Scalar propagation uses exact original functions, never Observer.step.
        self._physics_only = Observer(self.c)
        self.reset()

    def __getstate__(self):
        state = self.__dict__.copy()
        state['telemetry_sink'] = None  # external diagnostics are not runtime state
        return state

    def reset(self, *, velocity=None, position=0.):
        if not math.isfinite(position) or (velocity is not None and (not math.isfinite(velocity) or abs(velocity)>40)):
            raise ValueError('Invalid reset state')
        self.t = None
        self.initialized = velocity is not None
        self.v = 0. if velocity is None else float(velocity)
        self.drive_a = self.disturbance = 0.
        self.s = float(position)
        self.pv = .25
        self.sigma_s = 0.
        self.used = [None, None]
        self.raw_previous = [None, None]
        self.pending = [[], []]
        self.initial_pending = [None, None]
        self.nodes = deque()
        self.solution = np.empty((0, 3))
        self.init_t = None
        self.publish_index = 0
        self.stop_since = None
        self.last_estimate = None
        self.last_fallback = False
        self.counters = dict(solves=0, fallback=0, residual_points=0, raw_used=0,
                             max_nodes=0, max_measurements=0, max_pending=0,
                             future_rejected=0, raw_rate_rejected=0)

    @staticmethod
    def valid(sample, t, age):
        return sample is not None and math.isfinite(sample.t) and math.isfinite(sample.value) and -1e-9 <= t-sample.t <= age

    def raw_gate(self, channel, sample, t):
        if not self.valid(sample, t, self.c.max_age_s):
            if sample is not None and math.isfinite(sample.t) and sample.t>t+1e-9:
                self.counters['future_rejected'] += 1
            return None, 'MISSING_OR_STALE'
        if abs(sample.value)>self.c.max_speed_mps:
            return None, 'RANGE'
        if self.used[channel] is not None and sample.t<=self.used[channel]:
            return None, 'DUPLICATE_OR_OLD'
        self.used[channel] = sample.t
        previous = self.raw_previous[channel]
        self.raw_previous[channel] = sample
        if previous is not None:
            dt = sample.t-previous.t
            if dt<=self.c.max_age_s and abs(sample.value-previous.value)>self.c.wheel_rate_limit_mps2*dt+self.c.rate_noise_margin_mps:
                self.counters['raw_rate_rejected'] += 1
                return None, 'RATE_ANOMALY'
        return sample, 'CANDIDATE'

    def _take_measurements(self, t):
        p = [[s for s in q if self.valid(s, t, self.c.max_age_s)] for q in self.pending]
        self.pending = [[], []]
        measurements = []
        while p[0] or p[1]:
            if p[0] and p[1] and abs(p[0][0].t-p[1][0].t)<=self.c.pair_skew_s+1e-9:
                f, r = p[0].pop(0), p[1].pop(0)
                if abs(f.value-r.value)<=self.c.disagreement_mps:
                    measurements.append(Measurement((f.value+r.value)*.5, .1, ((0,f.t),(1,r.t))))
                else:
                    measurements.extend((Measurement(f.value,.2,((0,f.t),)), Measurement(r.value,.2,((1,r.t),))))
            else:
                i = 0 if p[0] and (not p[1] or p[0][0].t<=p[1][0].t) else 1
                s = p[i].pop(0)
                measurements.append(Measurement(s.value,.2,((i,s.t),)))
        return measurements

    def _propagate(self, x, u, dt):
        v, a, d = map(float, x)
        target = self._physics_only.drive_target(u, v)
        ap = a+(1.-math.exp(-dt/self.c.actuator_tau_s))*(target-a)
        am = clip(ap-self._physics_only.resistance(v)+d,-3.,3.)
        vp = clip(v+dt*am,-40.,40.)
        if u<=self.c.command_deadband and v*vp<0:
            vp = 0.
        return np.array([vp, ap, d])

    def _solve(self, t, u, fallback, measurements):
        prior = np.array([self.v,self.drive_a,self.disturbance])
        if len(self.nodes)==0:
            guess = prior[None, :].copy()
        else:
            guess = np.vstack((self.solution, self._propagate(self.solution[-1], self.nodes[-1][1], .1)))
        self.nodes.append((float(t),float(u),measurements))
        if len(self.nodes)>self.max_nodes:
            self.nodes.popleft()
            guess = guess[1:]
        # The arrival comes from the shifted previous ACCEPTED causal trajectory.
        arrival = guess[0].copy()
        cost = Cost(self.c,[n[1] for n in self.nodes],arrival,[n[2] for n in self.nodes],self.sd)
        lb, ub = (np.tile(v,len(self.nodes)) for v in BOUNDS)
        x0 = np.minimum(np.maximum(guess.reshape(-1),lb),ub)
        started = time.perf_counter()
        result = None
        exception = None
        try:
            result = least_squares(cost,x0,bounds=(lb,ub),workers=cost.numerical_map,**SOLVER)
            success = bool(result.success and np.isfinite(result.x).all() and np.isfinite(result.fun).all() and math.isfinite(result.cost))
        except Exception as error:
            success = False
            exception = type(error).__name__+': '+str(error)
        elapsed = time.perf_counter()-started
        if success:
            self.solution = result.x.reshape(-1,3).copy()
            current = self.solution[-1].copy()
            # Diagnostic local Gauss-Newton approximation, not calibrated CI.
            try:
                information = result.jac.T@result.jac
                unit = np.zeros(len(x0)); unit[-3] = 1.
                pv = float(cho_solve(cho_factor(information,check_finite=False),unit,check_finite=False)[-3])
                if not math.isfinite(pv) or pv<0: raise ValueError('Invalid local covariance')
                self.pv = max(1e-8,pv)
            except (ValueError,np.linalg.LinAlgError):
                self.pv += self.c.process_noise_v*.1
        else:
            current = fallback.copy()
            guess[-1] = current
            self.solution = guess.copy()  # never use failed optimizer state
        self.last_fallback = not success
        self.counters['solves'] += 1
        self.counters['fallback'] += int(not success)
        self.counters['residual_points'] += cost.points
        self.counters['raw_used'] += sum(len(m.ids) for m in measurements)
        self.counters['max_nodes'] = max(self.counters['max_nodes'],len(self.nodes))
        self.counters['max_measurements'] = max(self.counters['max_measurements'],len(cost.ids))
        active = 0 if result is None else int(np.count_nonzero(result.active_mask))
        rec = dict(t=float(t),window_start=self.nodes[0][0],window_end=float(t),variant=self.variant,
                   dimension=len(x0),nfev=0 if result is None else int(result.nfev),
                   njev=0 if result is None else int(result.njev or 0),
                   residual_points=cost.points,numerical_batch_calls=cost.batch_calls,
                   cost=None if result is None or not math.isfinite(result.cost) else float(result.cost),
                   optimality=None if result is None or not math.isfinite(result.optimality) else float(result.optimality),
                   status=-999 if result is None else int(result.status),success=success,
                   fallback=not success,wall_s=elapsed,initial_state=x0.reshape(-1,3)[-1].tolist(),
                   final_state=current.tolist(),arrival_state=arrival.tolist(),raw_measurements=len(cost.ids),
                   residual_measurements=len(cost.z),new_raw_measurements=sum(len(m.ids) for m in measurements),
                   active_bounds=active,error=exception)
        if self.telemetry_sink is not None:
            self.telemetry_sink(rec)
        return current

    def step(self, t, command=None, front=None, rear=None):
        if not math.isfinite(t) or (self.t is not None and t<=self.t):
            raise ValueError('Time must be finite and increase; explicit reset required')
        dt = 0. if self.t is None else t-self.t
        if dt>self.c.max_step_s+1e-9:
            raise ValueError('Time gap exceeds max_step_s')
        stale = not self.valid(command,t,self.c.command_timeout_s)
        if not stale and abs(command.value)>1.000001: stale=True
        u = 0. if stale else clip(command.value,-1.,1.)
        statuses = []
        for i,sample in enumerate((front,rear)):
            candidate,status = self.raw_gate(i,sample,t)
            statuses.append(status)
            if candidate is not None:
                if not self.initialized:
                    self.initial_pending[i]=candidate
                else:
                    self.pending[i].append(candidate)
        self.counters['max_pending'] = max(self.counters['max_pending'],sum(map(len,self.pending)))
        if sum(map(len,self.pending))>16:
            raise AssertionError('Unexpected input grid: pending queue would exceed bound')
        just_initialized = False
        if not self.initialized:
            for i,s in enumerate(self.initial_pending):
                if not self.valid(s,t,self.c.max_age_s):self.initial_pending[i]=None
            f,r = self.initial_pending
            if f is not None and r is not None:
                if abs(f.t-r.t)>self.c.pair_skew_s+1e-9:
                    self.initial_pending[0 if f.t<r.t else 1]=None
                elif abs(f.value-r.value)<=self.c.disagreement_mps:
                    self.v=(f.value+r.value)*.5
                    self.drive_a=self.disturbance=0.
                    self.initialized=True;self.init_t=t;self.publish_index=0
                    self.pending=[[f],[r]];self.initial_pending=[None,None]
                    just_initialized=True
                else:self.initial_pending=[None,None]
            if not self.initialized:
                self.t=t
                return self._output(t,0.,'WAITING_FOR_INITIALIZATION',statuses,stale)
        if self.init_t is None:
            self.init_t=t;self.publish_index=0;just_initialized=True
        previous_v = self.v
        fallback = np.array([self.v,self.drive_a,self.disturbance]) if just_initialized else self._propagate([self.v,self.drive_a,self.disturbance],u,dt)
        self.pv += self.c.process_noise_v*dt*(4. if stale else 1.)
        if self.publish_index%2==0:
            mm=self._take_measurements(t)
            state=self._solve(t,u,fallback,mm)
            mode='MHE_SOLVE_FALLBACK' if self.last_fallback else ('MHE_FUSED' if mm else 'MODEL_ONLY')
        else:
            state=fallback;self.last_fallback=False;mode='MHE_PROPAGATED'
        self.v,self.drive_a,self.disturbance=map(float,state)
        if not (np.isfinite(state).all() and np.all(state>=BOUNDS[0]-1e-9) and np.all(state<=BOUNDS[1]+1e-9)):
            raise AssertionError('Nonfinite or out-of-bounds MHE state')
        stop_candidate=(not stale and u<=self.c.command_deadband and abs(self.v)<self.c.stop_speed_mps and
                        all(self.valid(s,t,self.c.max_age_s) and abs(s.value)<self.c.stop_speed_mps for s in (front,rear)) and
                        abs(front.t-rear.t)<=self.c.pair_skew_s)
        if stop_candidate:
            if self.stop_since is None:self.stop_since=t
            if t-self.stop_since>=self.c.stop_dwell_s:mode='STOPPED'
        else:self.stop_since=None
        if not just_initialized:
            self.s += .5*(previous_v+self.v)*dt
            self.sigma_s += dt*math.sqrt(self.pv)
        self.t=t;self.publish_index+=1
        return self._output(t,0. if just_initialized or dt==0 else (self.v-previous_v)/dt,mode,statuses,stale)

    def _output(self,t,a,mode,statuses,stale):
        self.last_estimate=Estimate(t,self.s,self.v,a,self.pv,self.sigma_s**2,self.disturbance,
                                   mode,statuses[0],statuses[1],stale)
        return self.last_estimate

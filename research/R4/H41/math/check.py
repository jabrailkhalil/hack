"""Independent offline algebra checks for H41; NOT a runtime candidate.

Uses the verified canonical predictor as the finite-difference oracle. Tests
conditional formula correctness, not data coverage or odometry accuracy.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import platform
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import foundation as f
import numpy as np
import sympy as sp


def jacobian(o, v: float, drive: float, d: float, u: float, h: float):
    c = o.c
    q = min(1., max(0., (abs(u)-c.command_deadband)/(1-c.command_deadband)))**c.command_exponent
    tq = c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m
    if u >= 0:
        tv = (-c.travel_direction*q*c.max_power_w/c.mass_kg
              * math.copysign(1., v)/(v*v)) if abs(v)>1. and c.max_power_w/abs(v)<tq else 0.
    else:
        tv = -q*c.max_brake_force_n/c.mass_kg/.2*(1.-math.tanh(v/.2)**2)
    rv = (c.rolling_force_n/.2*(1.-math.tanh(v/.2)**2)
          + 2*c.quadratic_drag_n_s2_m2*abs(v))/c.mass_kg
    rho = math.exp(-h/c.actuator_tau_s)
    av, aa = (1-rho)*tv, rho
    # Do not replace the legacy arithmetic of the predictor being differentiated.
    next_drive = drive+(1-rho)*(o.drive_target(u,v)-drive)
    raw_accel = next_drive-o.resistance(v)+d
    accel = f.clip(raw_accel, -c.max_accel_mps2, c.max_accel_mps2)
    raw_v = v+h*accel
    sa = float(abs(raw_accel)<c.max_accel_mps2)
    sv = float(abs(raw_v)<c.max_speed_mps)
    if u <= c.command_deadband and v*f.clip(raw_v,-c.max_speed_mps,c.max_speed_mps)<0:
        sv = 0.
    return np.array([[sv*(1+h*sa*(av-rv)), sv*h*sa*aa], [av, aa]])


def run():
    v, a, h, rho, d = sp.symbols('v a h rho d', real=True)
    T, R = sp.Function('T'), sp.Function('R')
    state = sp.Matrix([v+h*(rho*a+(1-rho)*T(v)-R(v)+d),rho*a+(1-rho)*T(v)])
    expected = sp.Matrix([[1+h*((1-rho)*sp.diff(T(v),v)-sp.diff(R(v),v)),h*rho],
                          [(1-rho)*sp.diff(T(v),v),rho]])
    assert sp.simplify(state.jacobian([v,a])-expected) == sp.zeros(2)
    H = sp.Matrix([[1,0]])
    frozen = sp.Matrix([[1,h*rho],[0,rho]])
    obs_det = H.col_join(H*frozen).det()
    assert sp.simplify(obs_det-h*rho) == 0
    p, x, b, kv, ka, r = sp.symbols('p x b kv ka r', real=True)
    P=sp.Matrix([[p,x],[x,b]]); K=sp.Matrix([kv,ka]); M=sp.eye(2)-K*H
    joseph=sp.simplify(M*P*M.T+r*K*K.T)
    form=sp.Matrix([[(1-kv)**2*p+kv**2*r,(1-kv)*(x-ka*p)+kv*ka*r],
                    [(1-kv)*(x-ka*p)+kv*ka*r,b-2*ka*x+ka**2*(p+r)]])
    assert sp.simplify(joseph-form)==sp.zeros(2)
    qa,qv = sp.symbols('qa qv', nonnegative=True)
    Q=qa*sp.Matrix([[h*h,h],[h,1]])+sp.diag(qv,0)
    assert sp.factor(Q.det())==qa*qv
    c,readout=f.profile(); o=f.GuardedReadoutObserver(c,readout=readout)
    rng=np.random.default_rng(41)
    fd_max=0.; examples=[]
    cases=[]
    for _ in range(800):
        cases.append((float(rng.uniform(-35,35)),float(rng.uniform(-1.2,1.2)),
                      float(rng.uniform(-.6,.6)),float(rng.uniform(-1,1)),float(rng.uniform(.005,.19))))
    # Clipping/no-reversal branches away from exact nondifferentiable boundaries.
    cases += [(v0,a0,dd,uu,.1) for v0,a0,dd,uu in
              [(.02,-1,0,-.8),(-.02,1,0,-.8),(39.99,1,0,.8),(-39.99,-1,0,-.8),
               (10,10,0,.8),(10,-10,0,-.8),(.3,.1,.1,-.7),(-.3,-.1,-.1,-.7)]]
    eps=1e-5
    for v0,a0,dd,uu,dt in cases:
        actual=jacobian(o,v0,a0,dd,uu,dt)
        columns=[]
        for dv,da in ((eps,0.),(0.,eps)):
            plus=np.array(f.predict(o,v0+dv,a0+da,dd,uu,dt)[:2])
            minus=np.array(f.predict(o,v0-dv,a0-da,dd,uu,dt)[:2])
            columns.append((plus-minus)/(2*eps))
        numeric=np.column_stack(columns)
        error=float(np.max(np.abs(actual-numeric))); fd_max=max(fd_max,error)
        if error>2e-7: raise AssertionError(('finite-difference Jacobian',error,(v0,a0,dd,uu,dt),actual,numeric))
    numeric_max=0.; min_eigen=math.inf
    for i in range(5000):
        B=rng.normal(size=(2,2)); PP=B@B.T+np.eye(2)*1e-6
        rr=float(rng.uniform(.001,2.)); KV=PP[0,0]/(PP[0,0]+rr)
        KA=PP[0,1]/(PP[0,0]+rr)
        if i%3==0: KA=0.
        elif i%3==1: KA*=float(rng.uniform(0,1))  # arbitrary constrained effective Ka
        KK=np.array([KV,KA]); MM=np.eye(2)-KK[:,None]@np.array([[1.,0.]])
        matrix=MM@PP@MM.T+rr*np.outer(KK,KK)
        pv,px,pa=PP[0,0],PP[0,1],PP[1,1]
        scalar=np.array([[(1-KV)**2*pv+KV**2*rr,(1-KV)*(px-KA*pv)+KV*KA*rr],
                         [(1-KV)*(px-KA*pv)+KV*KA*rr,pa-2*KA*px+KA*KA*(pv+rr)]])
        error=float(np.max(np.abs(matrix-scalar)));numeric_max=max(numeric_max,error)
        eig=float(np.linalg.eigvalsh(scalar).min());min_eigen=min(min_eigen,eig)
        if error>1e-11 or eig < -1e-10:raise AssertionError(('Joseph',i,error,eig))
    # Exponents of (length,time), with A measured as acceleration.
    units={'v':(1,-1),'A':(1,-2),'h':(0,1),'Pvv':(2,-2),'PvA':(2,-3),'PAA':(2,-4)}
    add=lambda x,y:tuple(a+b for a,b in zip(x,y))
    assert add(units['A'],units['h'])==units['v']
    assert add(add(units['PAA'],units['h']),units['h'])==units['Pvv']
    assert add(units['PAA'],units['h'])==units['PvA']
    actual_gain=20/21; legacy_reconstruction=401/441
    result=dict(scope='OFFLINE_ALGEBRA_NOT_RUNTIME_OR_ACCURACY',seed=41,
        python=platform.python_version(),numpy=np.__version__,sympy=sp.__version__,
        jacobian=str(expected),frozen_observability_determinant=str(obs_det),
        symbolic_joseph_difference_zero=True,process_Q_determinant=str(Q.det()),
        jacobian_fd_cases=len(cases),jacobian_max_abs_delta=fd_max,
        joseph_psd_cases=5000,joseph_max_abs_delta=numeric_max,joseph_min_eigenvalue=min_eigen,
        unit_dimensions=units,units_passed=True,actual_gain_example=actual_gain,
        wrong_legacy_gain_example=legacy_reconstruction,
        warnings=['Local derivatives do not prove nonlinear switched/clipped stability',
                  'Ka-constrained Joseph preserves PSD conditional on a PSD prior; not calibrated covariance',
                  'Fixed engineering Q_A/P_A is not identified from train',
                  'Persistent d variance grows quadratically with outage time, unlike independent per-step noise',
                  'No runtime observer, actual-gain hook, or data accuracy has been implemented or tested here'])
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); result=run()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as out: json.dump(result,out,indent=2,ensure_ascii=False);out.write('\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))

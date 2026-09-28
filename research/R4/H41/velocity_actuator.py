"""One preregistered [velocity, actuator acceleration] observer.

Runtime is stdlib-only. The legacy disturbance remains a separate input;
its step-local noise allowance is NOT a bound on persistent unknown bias.
This module is imported in an isolated package with the explicit H41 hooks.
"""
from __future__ import annotations
import math
from .core import clip
from .guarded_readout import GuardedReadoutObserver


def drive_bound(c):
    return max(c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m,
               c.max_brake_force_n)/c.mass_kg


def derivatives(c, u, v):
    """Exact local T_v and R_v away from max/min branch boundaries."""
    q = min(1., max(0., (abs(u)-c.command_deadband)/(1.-c.command_deadband)))**c.command_exponent
    tangent = math.tanh(v/.2)
    if u >= 0.:
        force = c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m
        tv = (-c.travel_direction*q*c.max_power_w*math.copysign(1.,v)/(c.mass_kg*v*v)
              if abs(v)>1. and c.max_power_w/abs(v)<force else 0.)
    else:
        tv = -q*c.max_brake_force_n/(.2*c.mass_kg)*(1.-tangent*tangent)
    rv = c.rolling_force_n/(.2*c.mass_kg)*(1.-tangent*tangent)
    rv += 2.*c.quadratic_drag_n_s2_m2*abs(v)/c.mass_kg
    return tv, rv


def jacobian(c, u, v, a_prior, d, h):
    rho = math.exp(-h/c.actuator_tau_s)
    tv, rv = derivatives(c,u,v)
    resistance = (c.rolling_force_n*math.tanh(v/.2)+c.quadratic_drag_n_s2_m2*v*abs(v))/c.mass_kg
    raw_a = a_prior-resistance+d
    sa = float(abs(raw_a)<c.max_accel_mps2)
    limited_a = clip(raw_a,-c.max_accel_mps2,c.max_accel_mps2)
    raw_v = v+h*limited_a
    sv = float(abs(raw_v)<c.max_speed_mps)
    if u<=c.command_deadband and v*clip(raw_v,-c.max_speed_mps,c.max_speed_mps)<0.:
        sv = 0.
    av = (1.-rho)*tv
    return (sv*(1.+h*sa*(av-rv)), sv*h*sa*rho, av, rho), h*sv*sa


def joseph(p, cross, aa, kv, ka, r):
    """Full symmetric Joseph update for the EFFECTIVE applied gain, H=[1,0]."""
    q = 1.-kv
    return (q*q*p+kv*kv*r,
            q*(cross-ka*p)+kv*ka*r,
            aa-2.*ka*cross+ka*ka*(p+r))


def stabilize(p, cross, aa, c):
    """Finite PSD safeguard; congruent cap scaling, not a calibrated CI."""
    if not all(math.isfinite(x) for x in (p,cross,aa)):
        raise FloatingPointError('H41 nonfinite covariance')
    p, aa = max(p,1e-8), max(aa,1e-12)
    cross = clip(cross,-math.sqrt(p*aa),math.sqrt(p*aa))
    sv = min(1.,c.max_speed_mps/math.sqrt(p))
    sa = min(1.,drive_bound(c)/math.sqrt(aa))
    return p*sv*sv, cross*sv*sa, aa*sa*sa


class VelocityActuatorObserver(GuardedReadoutObserver):
    """A 2x2 covariance, frozen engineering prior, and no extra sensor history."""
    def __init__(self, config=None, *, readout=None, enabled=True, synthetic_scale=1.):
        if not math.isfinite(synthetic_scale) or synthetic_scale not in (.5,1.,2.):
            raise ValueError('Only fixed scale 1 or documented synthetic sensitivity .5/2')
        if not getattr(self,'H41_HOOKS',False):
            raise RuntimeError('H41 requires the explicitly patched runtime package')
        self.h41_enabled = bool(enabled)
        self.h41_synthetic_scale = float(synthetic_scale)
        super().__init__(config,readout=readout)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.h41_sa = (self.c.disturbance_limit_mps2/2.)**2*self.h41_synthetic_scale
        self.h41_sd = (self.c.disturbance_limit_mps2/2.)**2
        self.h41_paa, self.h41_pva = self.h41_sa, 0.
        self.h41_prior = self.pv
        self.h41_kv = self.h41_ka = self.h41_a_model = self.h41_delta_a = 0.
        self.h41_updates = self.h41_nonzero = self.h41_clipped = 0
        self.h41_prediction_cross = self.h41_prediction_aa = 0.

    def _h41_predict(self,h,u,v,a_model,predicted,command_stale):
        f,l0 = jacobian(self.c,u,v,self.drive_a,self.disturbance,h)
        f11,f12,f21,f22 = f
        p,cross,aa = self.pv,self.h41_pva,self.h41_paa
        qa = self.h41_sa*(-math.expm1(-2.*h/self.c.actuator_tau_s))
        qv = self.c.process_noise_v*h*(4. if command_stale else 1.)+h*h*self.h41_sd
        p_new = f11*f11*p+2.*f11*f12*cross+f12*f12*aa+qv+qa*l0*l0
        c_new = f11*f21*p+(f11*f22+f12*f21)*cross+f12*f22*aa+qa*l0
        a_new = f21*f21*p+2.*f21*f22*cross+f22*f22*aa+qa
        p_new,self.h41_pva,self.h41_paa = stabilize(p_new,c_new,a_new,self.c)
        self.h41_prior,self.h41_a_model = p_new,a_model
        self.h41_prediction_cross,self.h41_prediction_aa = self.h41_pva,self.h41_paa
        self.h41_kv=self.h41_ka=self.h41_delta_a=0.
        return p_new

    def _h41_correct(self,t,samples,accepted,agree,stale,p_prior,residual,r,kv):
        trusted = (len(accepted)==2 and agree and not stale
            and abs(samples[0].value-samples[1].value)<=.15
            and abs(samples[0].t-samples[1].t)<=.05
            and all(0.<=t-s.t<=.20 for s in samples)
            and abs(sum(s.value for s in samples)/2.)>.5
            and abs(residual)<=.3
            and max(s.t for s in samples)>=self.reacquire_blocked_until)
        ka = self.h41_pva/(p_prior+r) if trusted else 0.
        delta = 0.
        if trusted:
            bound = drive_bound(self.c)
            proposed = ka*residual
            delta = clip(self.drive_a+proposed,-bound,bound)-self.drive_a
            if residual != 0.: ka = delta/residual
            self.drive_a += delta
            self.h41_updates = min(2**31-1,self.h41_updates+1)
            if abs(delta)>1e-12:self.h41_nonzero=min(2**31-1,self.h41_nonzero+1)
            if abs(delta-proposed)>1e-12:self.h41_clipped=min(2**31-1,self.h41_clipped+1)
        self.pv,self.h41_pva,self.h41_paa = stabilize(
            *joseph(p_prior,self.h41_pva,self.h41_paa,kv,ka,r),self.c)
        self.h41_kv,self.h41_ka,self.h41_delta_a=kv,ka,delta

    def _output(self,t,a,mode,statuses,command_stale):
        if self.h41_enabled:
            if mode in ('INITIALIZED','STOPPED'):
                self.h41_paa,self.h41_pva=self.h41_sa,0.
            self.pv,self.h41_pva,self.h41_paa=stabilize(self.pv,self.h41_pva,self.h41_paa,self.c)
        return super()._output(t,a,mode,statuses,command_stale)

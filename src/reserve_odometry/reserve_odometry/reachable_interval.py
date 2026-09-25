"""H21 conditional reachable envelope; supervisor only, not a truth interval.

Needs the explicit research core-hooks.patch. No new physical coefficients,
reference signals, alternate readout or optimizer. Agreement cannot identify a
common wheel bias. Bounds apply only under PLAN's anchor/error/ZOH assumptions.
"""
import math
from .core import Observer, clip
from .guarded_readout import GuardedReadoutObserver


def drive_bounds(observer, u, lo, hi):
    """Exact target extrema on a velocity interval, including zero/power cap."""
    if u < 0:
        return observer.drive_target(u, hi), observer.drive_target(u, lo)
    near = 0.0 if lo <= 0.0 <= hi else min(abs(lo), abs(hi))
    far = max(abs(lo), abs(hi))
    values = (observer.drive_target(u, near), observer.drive_target(u, far))
    return min(values), max(values)


def physical_drive_bounds(c):
    traction = c.efficiency*c.gear_ratio*c.total_motor_torque_nm/(c.wheel_radius_m*c.mass_kg)
    brake = c.max_brake_force_n/c.mass_kg
    return min(-brake, c.travel_direction*traction), max(brake, c.travel_direction*traction)


def propagate(observer, bounds, dt, commands):
    """Outward tube enclosure, not a midpoint approximation.

    commands=None means unknown input. Otherwise the previous/current command
    hull bounds a causal held-input step. Absolute additive error <= D is an
    assumption, not a fitted confidence level. Roundoff padding is outward.
    """
    c = observer.c
    lo, hi, dl, dh = bounds
    tube_lo = max(-c.max_speed_mps, lo-c.max_accel_mps2*dt)
    tube_hi = min(c.max_speed_mps, hi+c.max_accel_mps2*dt)
    if commands is None:
        tl, th = physical_drive_bounds(c)
    else:
        us = [min(commands), max(commands)]
        if us[0] <= 0 <= us[-1]:
            us.append(0.0)
        extrema = [drive_bounds(observer, u, tube_lo, tube_hi) for u in us]
        tl, th = min(x[0] for x in extrema), max(x[1] for x in extrema)
    rho = math.exp(-dt/c.actuator_tau_s)
    ndl, ndh = rho*dl+(1-rho)*tl, rho*dh+(1-rho)*th
    gl = clip(min(dl, ndl)-observer.resistance(tube_hi)-c.disturbance_limit_mps2,
              -c.max_accel_mps2, c.max_accel_mps2)
    gh = clip(max(dh, ndh)-observer.resistance(tube_lo)+c.disturbance_limit_mps2,
              -c.max_accel_mps2, c.max_accel_mps2)
    vl = clip(lo+dt*gl-1e-12, -c.max_speed_mps, c.max_speed_mps)
    vh = clip(hi+dt*gh+1e-12, -c.max_speed_mps, c.max_speed_mps)
    if tube_lo <= 0 <= tube_hi:
        vl, vh = min(vl, 0.0), max(vh, 0.0)
    return vl, vh, ndl-1e-12, ndh+1e-12


class ReachableIntervalObserver(GuardedReadoutObserver):
    """One preregistered variant: weak-update veto, bounded ambiguity fallback."""
    def __init__(self, config=None, *, readout=None, enabled=True):
        if enabled and not hasattr(Observer, '_supervise_updates'):
            raise RuntimeError('H21 requires explicit research/R2/H21/core-hooks.patch')
        self.h21_enabled = bool(enabled)
        super().__init__(config, readout=readout)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.h21_bounds = None
        self.h21_anchor_t = None
        self.h21_healthy_since = None
        self.h21_ambiguity_since = None
        self.h21_cooldown_until = -math.inf
        self.h21_previous_command = None
        self.h21_active = False
        self.h21_last_bounds = None
        self.h21_rejections = ()
        self.h21_predicted = 0.0
        self.h21_counts = dict(active=0, anchors=0, weak_eligible=0, veto=0,
                               veto_ticks=0, wide=0, expired=0, fallback=0)

    def _count(self, key, n=1):
        self.h21_counts[key] = min(2147483647, self.h21_counts[key]+n)

    def _invalidate(self, t, cooldown=0.0):
        self.h21_bounds = None
        self.h21_anchor_t = None
        self.h21_healthy_since = None
        self.h21_ambiguity_since = None
        self.h21_active = False
        self.h21_cooldown_until = t+cooldown

    def step(self, t, command=None, front=None, rear=None):
        if not self.h21_enabled:
            return super().step(t, command, front, rear)
        # Fail before modifying supervisor state, exactly as the base time guard.
        if not math.isfinite(t):
            raise ValueError('Nonfinite time')
        if self.t is not None and t <= self.t:
            raise ValueError('Time must increase; reset after a clock jump')
        dt = 0.0 if self.t is None else t-self.t
        if dt > self.c.max_step_s+1e-9:
            raise ValueError('Time gap exceeds max_step_s; explicit reset required')
        valid = self._valid(command, t, self.c.command_timeout_s)
        valid = valid and abs(command.value) <= 1.000001
        u = clip(command.value, -1, 1) if valid else None
        self.h21_rejections = ()
        if self.h21_bounds is not None:
            commands = None if u is None or self.h21_previous_command is None else (u, self.h21_previous_command)
            self.h21_bounds = propagate(self, self.h21_bounds, dt, commands)
            self.h21_last_bounds = self.h21_bounds
            if self.h21_bounds[1]-self.h21_bounds[0] > self.c.innovation_cap_mps:
                self._count('wide'); self._invalidate(t)
            elif t-self.h21_anchor_t > 2.0:
                self._count('expired'); self._invalidate(t)
        self.h21_active = self.h21_bounds is not None and t >= self.h21_cooldown_until
        if self.h21_active:
            self._count('active')
        result = super().step(t, command, front, rear)
        statuses = (result.front_status, result.rear_status)
        healthy = (valid and self._valid(front, t, self.c.max_age_s)
                   and self._valid(rear, t, self.c.max_age_s)
                   and abs(front.t-rear.t) <= self.c.pair_skew_s
                   and abs(front.value-rear.value) <= 3*self.c.wheel_sigma_mps
                   and all(s in ('ACCEPTED', 'DUPLICATE_OR_OLD') for s in statuses)
                   and result.mode not in ('STOPPED', 'REACQUIRING', 'WAITING_FOR_INITIALIZATION'))
        if not healthy:
            self.h21_healthy_since = None
        elif self.h21_healthy_since is None:
            self.h21_healthy_since = t
        if (self.h21_bounds is None and healthy and result.mode == 'FUSED'
                and t >= self.h21_cooldown_until
                and t-self.h21_healthy_since >= .5
                and max(abs(x.value-self.h21_predicted) for x in (front,rear)) <= self.c.innovation_floor_mps):
            z = (front.value+rear.value)*.5
            age = max(0.0,t-(front.t+rear.t)*.5)
            epsilon = 3*self.c.wheel_sigma_mps+self.c.max_accel_mps2*age
            dl, dh = physical_drive_bounds(self.c)
            self.h21_bounds = (clip(z-epsilon,-self.c.max_speed_mps,self.c.max_speed_mps),
                               clip(z+epsilon,-self.c.max_speed_mps,self.c.max_speed_mps),dl,dh)
            self.h21_anchor_t = t
            self.h21_ambiguity_since = None
            self._count('anchors')
        self.h21_previous_command = u
        return result

    def _supervise_updates(self, t, predicted, samples, statuses, accepted):
        self.h21_predicted = predicted
        if not self.h21_enabled or not self.h21_active:
            return accepted
        lo, hi = self.h21_bounds[:2]
        rejected = []
        for i in accepted:
            s = samples[i]
            weak = (abs(s.value-predicted) <= self.c.innovation_floor_mps
                    and abs(s.value) > self.c.stop_model_speed_mps)
            if not weak:
                continue
            self._count('weak_eligible')
            pad = 3*self.c.wheel_sigma_mps+self.c.max_accel_mps2*max(0.,t-s.t)
            if s.value < lo-pad or s.value > hi+pad:
                rejected.append((i,s.t,s.value,lo-pad,hi+pad))
        if not rejected:
            return accepted
        if self.h21_ambiguity_since is None:
            self.h21_ambiguity_since = t
        if t-self.h21_ambiguity_since >= .5:
            self._count('fallback'); self._invalidate(t,.5)
            return accepted
        # Never intersect with the conflicting measurement or alter recovery.
        self.h21_rejections = tuple(rejected)
        self._count('veto',len(rejected)); self._count('veto_ticks')
        removed = {x[0] for x in rejected}
        for i in removed:
            statuses[i] = 'REACHABILITY_AMBIGUOUS'
        return [i for i in accepted if i not in removed]

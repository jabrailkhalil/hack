"""R3-H31: bounded past-score ensemble, published outage path only.

The contained canonical v8 is NEVER modified by ensemble state or pseudotargets.
This experimental module is opt-in; canonical ROS launch does not use it.
"""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, replace
import math
from typing import Optional
from .core import Config, Estimate, Sample, clip
from .guarded_readout import GuardedReadoutObserver, ReadoutConfig


@dataclass(frozen=True)
class EnsembleConfig:
    enabled: bool = True
    equal_weight_control: bool = False  # diagnostic only; not a second candidate


@dataclass(frozen=True)
class CompletedScore:
    start: float
    horizon: float
    completed: float
    losses: tuple


@dataclass
class PendingForecast:
    start: float
    horizon: float
    physics: GuardedReadoutObserver
    velocity: float
    acceleration: float
    command: Sample
    endpoint: Optional[tuple] = None


@dataclass
class Outage:
    trigger: float
    seed_time: float
    velocity: float
    acceleration: float
    weights: tuple
    usable: bool
    score_stamp: Optional[float]
    score_count: int
    revoked: bool = False


class PrequentialOutageObserver:
    """One canonical + at most one virtual canonical, eight score triplets.

    Published last_estimate is deliberately separate from base.last_estimate.
    Only controller/front/rear samples enter step(). No runtime file/data IDs.
    """
    HORIZON = 1.0
    SPACING = 2.0
    MAX_RECORDS = 8
    SCORE_AGE = 20.0
    RECENT_SCORE = 4.0
    MIN_RECORDS = 3
    PRIORS = (.5, .25, .25)
    PHYSICS_FLOOR = .25
    COMMAND_CHANGE = .2
    STATS = ('steps', 'launches', 'completed', 'cancelled', 'outage_ticks',
             'selected_outages', 'effective_ticks', 'regime_resets',
             'guarded_resets', 'limit_failures', 'outage_episodes')

    def __init__(self, config: Config, *, readout: Optional[ReadoutConfig] = None,
                 ensemble: Optional[EnsembleConfig] = None):
        self.ensemble = ensemble or EnsembleConfig()
        self.base = GuardedReadoutObserver(config, readout=readout)
        self.reset()

    @property
    def c(self):
        return self.base.c

    @property
    def t(self):
        return self.base.t

    def reset(self, *, velocity=None, position=0.0):
        self.base.reset(velocity=velocity, position=position)
        self.scores = deque(maxlen=self.MAX_RECORDS)
        self.pending = None
        self.outage = None
        self.endpoint_previous = None
        self.endpoint_stamps = (-math.inf, -math.inf)
        self.command_epoch = None
        self.next_launch = -math.inf
        self.delta_v = self.delta_s = self.extra_sigma_s = 0.0
        self.last_estimate = None
        self.stats = dict.fromkeys(self.STATS, 0)
        self.last_diag = None

    def _count(self, key):
        self.stats[key] = min(2**31-1, self.stats[key]+1)

    def _cancel(self):
        if self.pending is not None:
            self._count('cancelled')
        self.pending = None
        self.endpoint_previous = None

    def _regime(self, u):
        return 1 if u > self.c.command_deadband else (-1 if u < -self.c.command_deadband else 0)

    def _bounded_member(self, v, initial, u):
        v = clip(v, -self.c.max_speed_mps, self.c.max_speed_mps)
        if u <= self.c.command_deadband and initial*v < 0:
            return 0.0
        return v

    def _trusted(self, e, front, rear):
        return (not e.command_stale and self.base._valid(front, e.t, self.c.max_age_s)
                and self.base._valid(rear, e.t, self.c.max_age_s)
                and abs(front.t-rear.t) <= .05
                and abs(front.value-rear.value) <= .15
                and abs(e.v) > .5
                and e.mode not in ('INITIALIZED', 'WAITING_FOR_INITIALIZATION', 'STOPPED', 'REACQUIRING')
                and e.t >= self.base.reacquire_blocked_until
                and all(s in ('ACCEPTED', 'DUPLICATE_OR_OLD')
                        for s in (e.front_status, e.rear_status)))

    def _weights(self, trigger):
        records = [s for s in self.scores if trigger-self.SCORE_AGE <= s.completed < trigger-1e-9]
        if len(records) < self.MIN_RECORDS or trigger-records[-1].completed > self.RECENT_SCORE:
            return (1.0, 0.0, 0.0), False, None, len(records)
        if self.ensemble.equal_weight_control:
            weights = (1/3, 1/3, 1/3)
        else:
            losses = [sum(r.losses[i] for r in records)/len(records) for i in range(3)]
            masses = [prior*math.exp(-loss) for prior, loss in zip(self.PRIORS, losses)]
            z = sum(masses)
            q = [m/z for m in masses]
            weights = (self.PHYSICS_FLOOR+(1-self.PHYSICS_FLOOR)*q[0],
                       (1-self.PHYSICS_FLOOR)*q[1], (1-self.PHYSICS_FLOOR)*q[2])
        return weights, True, records[-1].completed, len(records)

    def _learn(self, e, command, front, rear, healthy, u):
        """Targets arrive AFTER prediction; no target is passed to virtual step."""
        if not healthy:
            self._cancel()
            return False
        if self.pending is not None:
            p = self.pending
            if e.t > p.horizon+self.c.max_age_s:
                self._cancel()
            elif p.endpoint is None:
                deadline = min(e.t, p.horizon)
                # Do not inject a just-arrived command backwards across the horizon.
                held_command = command if command.t <= deadline+1e-9 else p.command
                if deadline > p.physics.t+1e-12:
                    p.physics.step(deadline, held_command)
                p.command = command
                if e.t+1e-9 >= p.horizon:
                    p.endpoint = (p.physics.last_estimate.v, p.velocity,
                                  self._bounded_member(p.velocity+p.acceleration*self.HORIZON,
                                                       p.velocity, u))
        # Held duplicates and half-new pairs cannot rescore an episode.
        if front.t <= self.endpoint_stamps[0] or rear.t <= self.endpoint_stamps[1]:
            return False
        self.endpoint_stamps = (front.t, rear.t)
        tz = (front.t+rear.t)*.5
        z = (front.value+rear.value)*.5
        old = self.endpoint_previous
        completed = False
        p = self.pending
        if (p is not None and p.endpoint is not None and old is not None
                and old[0] <= p.horizon <= tz and 0 < tz-old[0] <= self.c.max_age_s
                and e.t >= p.horizon):
            target = old[1]+(z-old[1])*(p.horizon-old[0])/(tz-old[0])
            sigma = self.c.wheel_sigma_mps+.5*self.c.disturbance_limit_mps2*self.HORIZON
            losses = tuple(min(4.0, 2*(math.hypot(1.0, (v-target)/sigma)-1)) for v in p.endpoint)
            self.scores.append(CompletedScore(p.start, p.horizon, e.t, losses))
            self.pending = None
            self._count('completed')
            completed = True
        self.endpoint_previous = (tz, z)
        if self.pending is None and e.t >= self.next_launch:
            a = clip(self.base.drive_a-self.base.resistance(self.base.v)+self.base.disturbance,
                     -self.c.max_accel_mps2, self.c.max_accel_mps2)
            self.pending = PendingForecast(e.t, e.t+self.HORIZON, deepcopy(self.base), e.v, a, command)
            self.next_launch = e.t+self.SPACING
            self._count('launches')
        return completed

    def step(self, t, command=None, front=None, rear=None) -> Estimate:
        old_t = self.base.t
        old_canonical = self.base.last_estimate
        old_published = self.last_estimate
        old_delta = self.delta_v
        old_a = clip(self.base.drive_a-self.base.resistance(self.base.v)+self.base.disturbance,
                     -self.c.max_accel_mps2, self.c.max_accel_mps2)
        e = self.base.step(t, command, front, rear)
        if not self.ensemble.enabled:
            self.last_estimate = e
            return e
        self._count('steps')
        if old_t is None or e.mode in ('INITIALIZED', 'WAITING_FOR_INITIALIZATION'):
            self.last_estimate = e
            return e
        dt = t-old_t
        u = 0.0 if e.command_stale else clip(command.value, -1, 1)
        current_regime = self._regime(u)
        changed = (e.command_stale or self.command_epoch is None
                   or current_regime != self.command_epoch[0]
                   or abs(u-self.command_epoch[1]) > self.COMMAND_CHANGE)
        if changed:
            self.scores.clear()
            self._cancel()
            self.command_epoch = None if e.command_stale else (current_regime, u)
            self._count('regime_resets')
            if self.outage is not None:
                self.outage.revoked = True
        while self.scores and t-self.scores[0].completed > self.SCORE_AGE:
            self.scores.popleft()
        healthy = self._trusted(e, front, rear)
        missing = (e.mode == 'MODEL_ONLY' and
                   e.front_status == e.rear_status == 'MISSING_OR_STALE')
        permitted = missing and not e.command_stale and t >= self.base.reacquire_blocked_until
        output_v = e.v
        members = (e.v, e.v, e.v)
        weights = (1.0, 0.0, 0.0)
        triggered = False
        if missing:
            self._count('outage_ticks')
            if self.outage is None:
                weights, usable, stamp, count = self._weights(t)
                self.outage = Outage(t, old_t, old_canonical.v, old_a, weights,
                                     usable and permitted, stamp, count, not permitted)
                self._count('outage_episodes')
                triggered = True
                if self.outage.usable:
                    self._count('selected_outages')
            o = self.outage
            if not permitted or changed:
                o.revoked = True
            target = e.v
            if o.usable and not o.revoked:
                weights = o.weights
                cv = self._bounded_member(o.velocity, o.velocity, u)
                ca = self._bounded_member(o.velocity+o.acceleration*min(t-o.seed_time, self.HORIZON),
                                          o.velocity, u)
                members = (e.v, cv, ca)
                mix = sum(w*v for w, v in zip(weights, members))
                taper = clip(2.0-(t-o.trigger), 0.0, 1.0)
                target = e.v+taper*(mix-e.v)
            # Applicability revoked: weights no longer drive target; only a bounded
            # residual transition toward canonical may remain on missing ticks.
            if permitted or (old_delta != 0 and t >= self.base.reacquire_blocked_until):
                if o.usable or old_delta != 0:
                    previous_v = old_published.v
                    cap = self.c.disturbance_limit_mps2*self.HORIZON
                    lower = max(-self.c.max_speed_mps, e.v-cap, previous_v-self.c.max_accel_mps2*dt)
                    upper = min(self.c.max_speed_mps, e.v+cap, previous_v+self.c.max_accel_mps2*dt)
                    if u <= self.c.command_deadband:
                        if previous_v > 0: lower = max(lower, 0.0)
                        elif previous_v < 0: upper = min(upper, 0.0)
                    if lower <= upper:
                        output_v = clip(target, lower, upper)
                    else:
                        self._count('limit_failures')
                        o.revoked = True
        else:
            if old_delta != 0:
                self._count('guarded_resets')
            self.outage = None
        completed = self._learn(e, command, front, rear, healthy, u)
        self.delta_v = output_v-e.v
        if abs(self.delta_v) > 1e-6:
            self._count('effective_ticks')
        self.delta_s += .5*(old_delta+self.delta_v)*dt
        self.extra_sigma_s += .5*(abs(old_delta)+abs(self.delta_v))*dt
        o = self.outage
        self.last_diag = dict(t=t, triggered=triggered, completed=completed,
                              score_count=len(self.scores), selected=o is not None and o.usable,
                              revoked=o is not None and o.revoked,
                              trigger=o.trigger if o is not None else None,
                              score_stamp=o.score_stamp if o is not None else None,
                              weights=weights, members=members, missing=missing,
                              delta_v=self.delta_v, delta_s=self.delta_s,
                              pending_start=self.pending.start if self.pending is not None else None)
        if self.delta_v == self.delta_s == self.extra_sigma_s == 0:
            self.last_estimate = e
        else:
            self.last_estimate = replace(e, v=output_v, s=e.s+self.delta_s,
                a=e.a+(self.delta_v-old_delta)/dt,
                variance_v=e.variance_v+self.delta_v**2,
                variance_s=(math.sqrt(e.variance_s)+self.extra_sigma_s)**2)
        return self.last_estimate

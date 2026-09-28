"""Opt-in R3-H23 output-only B physics. No IO, reference, or fault labels.

The canonical observer is held by composition and never receives corrections.
One three-scalar model-only rollout has a fixed five-second horizon. All
additional runtime memory is constant; telemetry belongs in offline callers.
"""
from dataclasses import dataclass, replace
import math
from reserve_odometry.core import Config, Estimate, Observer, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig


@dataclass(slots=True)
class Rollout:
    c: Config
    v: float
    drive_a: float
    disturbance: float

    drive_target = Observer.drive_target
    resistance = Observer.resistance

    def advance(self, dt: float, u: float) -> None:
        target = self.drive_target(u, self.v)
        self.drive_a += (1.0 - math.exp(-dt / self.c.actuator_tau_s)) * (target - self.drive_a)
        acceleration = clip(self.drive_a - self.resistance(self.v) + self.disturbance,
                            -self.c.max_accel_mps2, self.c.max_accel_mps2)
        predicted = clip(self.v + dt * acceleration, -self.c.max_speed_mps, self.c.max_speed_mps)
        if u <= self.c.command_deadband and self.v * predicted < 0:
            predicted = 0.0
        self.v = predicted


class OutagePhysicsObserver:
    """Canonical v8 plus one bounded, non-feedback alternate prediction.

    Configuration is mandatory: callers must supply the pinned v8 and H16-B
    profiles, not Config() defaults. Disabling this object returns the actual
    canonical Estimate, without changing or disabling the v8 readout.
    """
    HORIZON_S = 5.0
    ALLOWED = ('MISSING_OR_STALE', 'DUPLICATE_OR_OLD', 'ZERO_LOCK_SUSPECT')
    __slots__ = ('inner', 'alternate_config', 'enabled', 'last_trusted', 'rollout',
                 'started_at', 'blocked', 'delta_v', 'delta_s', 'sigma_delta_s',
                 'phase', 'last_estimate')

    def __init__(self, config: Config, alternate: Config, *,
                 readout: ReadoutConfig, enabled: bool = True):
        config.__post_init__()
        alternate.__post_init__()
        self.inner = GuardedReadoutObserver(config, readout=readout)
        self.alternate_config = alternate
        self.enabled = bool(enabled)
        self.reset()

    @property
    def c(self):
        return self.inner.c

    @property
    def t(self):
        return self.inner.t

    def reset(self, *, velocity=None, position=0.0):
        # Validation is performed by the inner reset before extra state changes.
        self.inner.reset(velocity=velocity, position=position)
        self.last_trusted = None
        self.rollout = None
        self.started_at = None
        self.blocked = False
        self.delta_v = self.delta_s = self.sigma_delta_s = 0.0
        self.phase = 'DORMANT'
        self.last_estimate = None

    def _start(self, t):
        b = self.inner
        a0 = b.drive_a - b.resistance(b.v) + b.disturbance
        alt = Rollout(self.alternate_config, b.v, b.drive_a, 0.0)
        required = a0 - alt.drive_a + alt.resistance(alt.v)
        self.blocked = True  # At most one attempt per trusted-update episode.
        if (not math.isfinite(required) or abs(required) > self.c.disturbance_limit_mps2
                or abs(a0) > self.c.max_accel_mps2):
            self.phase = 'FALLBACK_OFFSET'
            return
        alt.disturbance = required
        self.rollout = alt
        self.started_at = t
        self.phase = 'ACTIVE'

    def step(self, t: float, command: Sample | None = None,
             front: Sample | None = None, rear: Sample | None = None) -> Estimate:
        old_t, old_delta = self.t, self.delta_v
        estimate = self.inner.step(t, command, front, rear)
        if not self.enabled:
            self.last_estimate = estimate
            return estimate
        statuses = (estimate.front_status, estimate.rear_status)
        trusted = [s.t for s, status in zip((front, rear), statuses)
                   if s is not None and status == 'ACCEPTED'
                   and self.inner._valid(s, t, self.c.max_age_s)]
        if trusted:
            self.last_trusted = max([self.last_trusted] + trusted) if self.last_trusted is not None else max(trusted)
            self.blocked = False
        if old_t is None or estimate.mode in ('WAITING_FOR_INITIALIZATION', 'INITIALIZED'):
            self.last_estimate = estimate
            return estimate
        dt = t - old_t  # Strictly positive and bounded by the canonical observer.
        eligible = (self.last_trusted is not None
                    and t - self.last_trusted > self.c.max_age_s + 1e-9
                    and estimate.mode == 'MODEL_ONLY' and not estimate.command_stale
                    and all(status in self.ALLOWED for status in statuses)
                    and t >= self.inner.reacquire_blocked_until
                    and abs(self.inner.v) > self.c.stop_model_speed_mps)
        if self.rollout is not None:
            if not eligible or t - self.started_at > self.HORIZON_S + 1e-9:
                self.rollout = None
                # A genuine new ACCEPTED sample permits a subsequent episode.
                self.blocked = not bool(trusted)
            else:
                self.rollout.advance(dt, clip(command.value, -1.0, 1.0))
        elif eligible and not self.blocked and old_delta == 0.0:
            self._start(t)
        if self.rollout is not None:
            limit = self.c.max_accel_mps2 * self.c.max_age_s
            desired = clip(self.rollout.v - self.inner.v, -limit, limit)
            delta = old_delta + clip(desired - old_delta,
                                     -self.c.max_accel_mps2 * dt, self.c.max_accel_mps2 * dt)
            self.phase = 'ACTIVE'
        else:
            release = self.c.reacquire_step_mps / 0.1 * dt
            delta = old_delta - clip(old_delta, -release, release)
            if old_delta != 0.0:
                self.phase = 'RELEASE'
            elif self.phase != 'FALLBACK_OFFSET' or not self.blocked:
                self.phase = 'BLOCKED' if self.blocked else 'DORMANT'
        velocity = clip(estimate.v + delta, -self.c.max_speed_mps, self.c.max_speed_mps)
        if estimate.mode == 'STOPPED' or estimate.v * velocity <= 0.0:
            velocity = estimate.v
        self.delta_v = velocity - estimate.v
        self.delta_s += 0.5 * (old_delta + self.delta_v) * dt
        self.sigma_delta_s += 0.5 * (abs(old_delta) + abs(self.delta_v)) * dt
        if self.delta_v == old_delta == self.delta_s == self.sigma_delta_s == 0.0:
            self.last_estimate = estimate
        else:
            self.last_estimate = replace(
                estimate, v=velocity, s=estimate.s + self.delta_s,
                a=estimate.a + (self.delta_v - old_delta) / dt,
                variance_v=estimate.variance_v + self.delta_v ** 2,
                variance_s=(math.sqrt(estimate.variance_s) + self.sigma_delta_s) ** 2)
        return self.last_estimate

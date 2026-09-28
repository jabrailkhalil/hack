"""H32: bounded, availability-causal event-time actuator propagation only.

No scientific dependencies, sensor replay, physical dead time, or modified
velocity integration. The caller retains the canonical outer-step guards.
"""
from collections import Counter
import math
from reserve_odometry.core import clip
from reserve_odometry.timeline import Timeline


class CommandEventMixin:
    def __init__(self, *args, enabled=True, **kwargs):
        self.h32_enabled = bool(enabled)
        super().__init__(*args, **kwargs)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self._commands = []             # <=31 pending samples + one predecessor
        self._predecessor = None
        self._lost_from = math.inf
        self._lost_until = -math.inf
        self.h32_counts = Counter()
        self.h32_last_drive_delta = 0.0
        self.h32_max_commands = 0

    def _lost(self, sample, reason):
        self._lost_from = min(self._lost_from, sample.t)
        self._lost_until = max(self._lost_until, sample.t)
        self.h32_counts[reason] += 1

    def receive_command(self, sample):
        """Call only after successful Timeline ingest, never before arrival."""
        if not self.h32_enabled:
            return
        if (sample is None or not math.isfinite(sample.t) or
                not math.isfinite(sample.value) or abs(sample.value) > 1.000001):
            self.h32_counts['invalid_delivery'] += 1
            return
        if self._predecessor is not None and sample.t <= self._predecessor.t:
            return
        if any(s.t == sample.t for s in self._commands):
            return
        # The source-time window is referenced to the last published output,
        # not to the newest/future stamp. Future inputs cannot evict useful past.
        origin = self.t if self.t is not None else min(
            [sample.t] + [s.t for s in self._commands])
        if sample.t > origin + .5 + 1e-9 or sample.t < origin - .5 - 1e-9:
            self._lost(sample, 'horizon_loss')
            return
        if len(self._commands) == 31:
            if sample.t >= self._commands[-1].t:
                self._lost(sample, 'overflow_loss')
                return
            self._lost(self._commands.pop(), 'overflow_loss')
        self._commands.append(sample)
        self._commands.sort(key=lambda s: s.t)  # already arrived, <=31 pending entries
        self.h32_max_commands = max(self.h32_max_commands,
                                   len(self._commands) + int(self._predecessor is not None))

    def step(self, t, command=None, front=None, rear=None):
        # The pristine core must validate time before any mutation on error.
        if (math.isfinite(t) and (self.t is None or
                0 < t - self.t <= self.c.max_step_s + 1e-9)):
            # Supports the original direct step API; the Timeline delivery hook
            # additionally supplies changes coalesced before this held sample.
            if self._valid(command, t, self.c.command_timeout_s):
                self.receive_command(command)
        return super().step(t, command, front, rear)

    def _h32_propagate_drive(self, dt, u, t, command):
        c = self.c
        target = self.drive_target(u, self.v)
        alpha = 1.0 - math.exp(-dt / c.actuator_tau_s)
        legacy = self.drive_a + alpha * (target - self.drive_a)
        self.h32_last_drive_delta = 0.0
        if not self.h32_enabled:
            self.drive_a = legacy
            return
        old = self.t
        ready = [s for s in self._commands if s.t <= t + 1e-9]
        self._commands = [s for s in self._commands if s.t > t + 1e-9]
        fresh = (self._valid(command, t, c.command_timeout_s)
                 and abs(command.value) <= 1.000001)
        prior = self._predecessor
        if prior is not None and old is not None:
            late = [s for s in ready if s.t <= old]
            if late:
                prior = max([prior] + late, key=lambda s: s.t)
                self.h32_counts['late_commands'] += len(late)
        history_ok = prior is not None and self._valid(prior, t, c.command_timeout_s)
        loss_affected = self._lost_from <= t + 1e-9
        if old is None or dt == 0 or not fresh or not history_ok or loss_affected:
            self.drive_a = legacy
            reason = ('initial' if old is None or dt == 0 else 'stale_current' if not fresh
                      else 'lost_history' if loss_affected else 'missing_predecessor')
            self.h32_counts['fallback_' + reason] += 1
        else:
            start = old
            current = clip(prior.value, -1., 1.)
            pieces = []
            changes = 0
            for s in ready:
                if s.t <= old:
                    continue
                value = clip(s.value, -1., 1.)
                if value != current:
                    boundary = min(t, s.t)  # same 1 ns tolerance as Timeline
                    if boundary > start:
                        pieces.append((boundary - start, current))
                    start, current = boundary, value
                    changes += 1
            if t > start:
                pieces.append((t - start, current))
            if not changes:
                # Exact historical arithmetic, including equal-value refreshes.
                self.drive_a = legacy
            else:
                d = self.drive_a
                for duration, value in pieces:
                    segment_target = self.drive_target(value, self.v)
                    d += (1.0 - math.exp(-duration / c.actuator_tau_s)) * (segment_target - d)
                self.drive_a = d
                self.h32_last_drive_delta = d - legacy
                self.h32_counts['event_steps'] += 1
                self.h32_counts['events_applied'] += changes
                if abs(d - legacy) >= 1e-6:
                    self.h32_counts['material_drive_steps'] += 1
        self._predecessor = command if fresh else None
        if t >= self._lost_until - 1e-9:
            self._lost_from, self._lost_until = math.inf, -math.inf
        kept = []
        for s in self._commands:
            if s.t <= t + .5 + 1e-9:
                kept.append(s)
            else:
                self._lost(s, 'horizon_loss')
        self._commands = kept
        self.h32_max_commands = max(self.h32_max_commands,
                                   len(kept) + int(self._predecessor is not None))


class CommandEventTimeline(Timeline):
    """The only transport hook: successful controller ingest -> observer."""
    def ingest(self, channel, sample):
        accepted = super().ingest(channel, sample)
        if accepted and channel == 0:
            callback = getattr(self.observer, 'receive_command', None)
            if callback is not None:
                callback(sample)
        return accepted

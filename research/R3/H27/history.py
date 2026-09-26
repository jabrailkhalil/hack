"""Non-intervening, causal H27 foundation monitor (stdlib only)."""
from collections import deque
from statistics import median
import math

LAGS = (.2, .4)


def command_mode(command, t, c):
    if (command is None or not math.isfinite(command.t) or not math.isfinite(command.value)
            or not 0 <= t-command.t <= c.command_timeout_s or abs(command.value) > 1.000001):
        return None
    return 1 if command.value > c.command_deadband else -1 if command.value < -c.command_deadband else 0


class History:
    """At most sixteen received d snapshots in a one-second source-time window.

    This class only records proposals. It never writes observer state or output.
    Event/trace accumulation belongs to the offline caller, not this bounded state.
    """
    def __init__(self):
        self.samples = deque(maxlen=16)
        self.mode = None
        self.episode = None
        self.peak = 0

    def checkpoint(self, t, d, lag, threshold):
        if not self.samples or t-self.samples[-1][0] > .35+1e-9:
            return dict(eligible=False, reason='no_recent_history')
        end = self.samples[-1][0]-lag
        chosen = [x for x in self.samples if end-.2-1e-9 <= x[0] <= end+1e-9]
        if len(chosen) < 3 or chosen[-1][0]-chosen[0][0] < .10-1e-9:
            return dict(eligible=False, reason='insufficient_window', n=len(chosen))
        ds = [x[1] for x in chosen]
        center = median(ds)
        mad = median([abs(x-center) for x in ds])
        delta = center-d
        stable = mad <= threshold/2
        return dict(eligible=stable and abs(delta) > threshold,
                    reason='proposed' if stable and abs(delta) > threshold else 'unstable' if not stable else 'below_threshold',
                    checkpoint=center, delta_d=delta, mad=mad, n=len(chosen), start=chosen[0][0], end=chosen[-1][0])

    def observe(self, t, command, front, rear, estimate, old_pair, old_d, c, threshold):
        """Return (closed_episode, residual_increment_or_None, opened_episode).

        Call once AFTER canonical step. old_pair/d are snapshots from before it.
        No GNSS/reference/fault metadata is accepted by this API.
        """
        closed = opened = None
        residual = None
        mode = command_mode(command, t, c)
        mode_changed = mode is None or (self.mode is not None and self.mode != mode)
        if mode_changed:
            if self.episode is not None:
                closed = dict(self.episode, end=t, end_reason='command_invalid_or_changed')
                self.episode = None
            self.samples.clear()
        self.mode = mode
        while self.samples and t-self.samples[0][0] > 1.0+1e-9:
            self.samples.popleft()
        statuses = (estimate.front_status, estimate.rear_status)
        is_loss = (estimate.mode == 'MODEL_ONLY' and mode is not None
                   and any(s != 'DUPLICATE_OR_OLD' for s in statuses))
        if estimate.mode != 'MODEL_ONLY' and self.episode is not None:
            closed = dict(self.episode, end=t, end_reason=estimate.mode)
            self.episode = None
        if is_loss and self.episode is None:
            proposals = {str(lag): self.checkpoint(t, estimate.disturbance, lag, threshold) for lag in LAGS}
            self.episode = dict(start=t, d_entry=estimate.disturbance, command_mode=mode,
                                statuses=statuses, history=list(self.samples), proposals=proposals, ticks=0)
            opened = self.episode
        if self.episode is not None and estimate.mode == 'MODEL_ONLY' and mode is not None:
            self.episode['ticks'] += 1
        # A failed wheel clears saved trust after the entry has been inspected.
        if any(s not in ('ACCEPTED', 'DUPLICATE_OR_OLD') for s in statuses):
            self.samples.clear()
        if (estimate.mode == 'FUSED' and not estimate.command_stale and mode is not None
                and all(s == 'ACCEPTED' for s in statuses) and old_pair is not None
                and front is not None and rear is not None
                and 0 <= t-front.t <= .20+1e-9 and 0 <= t-rear.t <= .20+1e-9
                and abs(front.t-rear.t) <= .05+1e-9 and abs(front.value-rear.value) <= .15):
            tz = (front.t+rear.t)*.5
            z = (front.value+rear.value)*.5
            dt = tz-old_pair.t
            if .05 <= dt <= c.max_age_s and abs(z) > .5 and abs((z-old_pair.value)/dt) <= c.max_accel_mps2:
                if self.samples and .05-1e-9 <= t-self.samples[-1][0] <= c.max_age_s+1e-9:
                    residual = estimate.disturbance-old_d
                self.samples.append((t, estimate.disturbance))
                self.peak = max(self.peak, len(self.samples))
        if estimate.mode in ('STOPPED', 'WAITING_FOR_INITIALIZATION', 'INITIALIZED'):
            self.samples.clear()
        return closed, residual, opened

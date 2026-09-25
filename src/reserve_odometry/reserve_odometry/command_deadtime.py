"""H17: opt-in causal command dead time, over the unchanged guarded v7.

Only drive_target receives the delayed command. The original command/stamp
still controls freshness, stop, sign and readout guards in the inherited core.
No extra input callbacks, output wait, scientific libraries or sensor replay.
"""
from collections import deque
import math
from .core import clip
from .guarded_readout import GuardedReadoutObserver


class CommandDeadtimeObserver(GuardedReadoutObserver):
    """History: at most .25 s plus one predecessor, at most 64 samples.

    Samples are only those actually observed by step(), not hidden Timeline
    inputs. Missing history uses neutral target; it does not fabricate a stamp.
    L=0 directly delegates to canonical v7, including its floating arithmetic.
    """
    def __init__(self, config=None, *, readout=None, delay_s=0.0):
        if not math.isfinite(delay_s) or not 0.0 <= delay_s <= .20:
            raise ValueError('delay_s must be finite and in [0, .20]')
        self.delay_s = float(delay_s)
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self.command_history = deque(maxlen=64)
        self.command_last_seen = None
        self.delayed_command = 0.0
        self.delayed_stamp = None
        self.delay_status = 'OFF' if self.delay_s == 0 else 'NO_HISTORY'
        self.delay_changed_ticks = 0
        self.delay_selected_ticks = 0
        self.delay_fallback_ticks = 0
        self.delay_invalid_ticks = 0
        self.command_history_peak = 0
        self._drive_command = None

    def _select_command(self, t, command):
        history = self.command_history
        # Keep one predecessor older than the time window, never an old list.
        cutoff = t - .25
        while len(history) > 1 and history[1].t < cutoff:
            history.popleft()
        while history and t - history[0].t > self.c.command_timeout_s:
            history.popleft()
        valid = (self._valid(command, t, self.c.command_timeout_s)
                 and command.t <= t and abs(command.value) <= 1.000001)
        self.delayed_stamp = None
        self.delayed_command = 0.0
        if not valid:
            self.delay_invalid_ticks += 1
            self.delay_status = 'CURRENT_INVALID'
            return
        if self.command_last_seen is None or command.t > self.command_last_seen:
            history.append(command)
            self.command_last_seen = command.t
        # A fresh append can replace the old predecessor; prune again.
        while len(history) > 1 and history[1].t < cutoff:
            history.popleft()
        self.command_history_peak = max(self.command_history_peak, len(history))
        target_t = t - self.delay_s
        chosen = next((s for s in reversed(history) if s.t <= target_t), None)
        if chosen is None or t - chosen.t > self.c.command_timeout_s:
            self.delay_fallback_ticks += 1
            self.delay_status = 'NO_HISTORY'
        else:
            self.delayed_command = clip(chosen.value, -1.0, 1.0)
            self.delayed_stamp = chosen.t
            self.delay_selected_ticks += 1
            self.delay_status = 'DELAYED'
        if self.delayed_command != clip(command.value, -1.0, 1.0):
            self.delay_changed_ticks += 1

    def drive_target(self, u, v):
        # Outside a step, retain the ordinary public drive_target behaviour.
        effective = u if self._drive_command is None else self._drive_command
        return super().drive_target(effective, v)

    def step(self, t, command=None, front=None, rear=None):
        if self.delay_s == 0.0:
            return super().step(t, command, front, rear)
        # Reject invalid time BEFORE changing history; same contract as core.
        if not math.isfinite(t):
            raise ValueError('Nonfinite time')
        if self.t is not None and t <= self.t:
            raise ValueError('Time must increase; reset after a clock jump')
        if self.t is not None and t - self.t > self.c.max_step_s + 1e-9:
            raise ValueError('Time gap exceeds max_step_s; explicit reset required')
        self._select_command(t, command)
        self._drive_command = self.delayed_command
        try:
            return super().step(t, command, front, rear)
        finally:
            self._drive_command = None

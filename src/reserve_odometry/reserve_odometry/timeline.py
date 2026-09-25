"""Bounded causal timestamp alignment shared by ROS and offline replay."""
import bisect
import math
from .core import Observer, Sample


class Timeline:
    def __init__(self, observer=None, rate_hz=20.0, delay_s=0.06):
        self.observer = observer or Observer()
        if not math.isfinite(rate_hz) or not 10 <= rate_hz <= 100:
            raise ValueError('rate_hz must be between 10 and 100')
        if not math.isfinite(delay_s) or not 0 <= delay_s <= .1:
            raise ValueError('delay_s must be between 0 and 0.1')
        self.dt = 1 / rate_hz
        self.delay = delay_s
        self.reset()

    def reset(self):
        self.observer.reset()
        self.queues = [[], [], []]  # command, front, rear
        self.held = [None, None, None]
        self.latest = None
        self.next_tick = None
        self.dropped = 0
        self.resets = 0

    def ingest(self, channel, sample):
        if channel not in (0, 1, 2):
            raise ValueError('Unknown input channel')
        if not math.isfinite(sample.t) or not math.isfinite(sample.value):
            self.dropped += 1
            return False
        if self.latest is None:
            self.next_tick = sample.t
            self.latest = sample.t
        else:
            self.latest = max(self.latest, sample.t)
        held = self.held[channel]
        if held is not None and sample.t <= held.t:
            self.dropped += 1
            return False
        q = self.queues[channel]
        stamps = [s.t for s in q]
        pos = bisect.bisect_left(stamps, sample.t)
        if pos < len(q) and q[pos].t == sample.t:
            self.dropped += 1
            return False
        q.insert(pos, sample)
        if len(q) > 128:
            q.pop(0)
            self.dropped += 1
        return True

    def advance(self, now=None):
        """Yield (estimate, held_input_tuple), never use samples beyond estimate.t.

        Without a ROS clock, only the newest received INPUT stamp advances time.
        In clock mode 'now' is ROS simulation time. Output time is now-delay.
        Large discontinuities open a new relative-odometry segment, not fake motion.
        """
        if self.latest is None:
            return
        source_now = self.latest if now is None else now
        if not math.isfinite(source_now):
            raise ValueError('Nonfinite clock')
        target = source_now - self.delay
        if self.observer.t is not None and target < self.observer.t - 1.0:
            self.reset()
            return
        if target - self.next_tick > 0.5:
            self.observer.reset()
            self.held = [None, None, None]
            self.next_tick = target
            self.resets += 1
        steps = 0
        while self.next_tick <= target + 1e-9 and steps < 16:
            t = self.next_tick
            for i, q in enumerate(self.queues):
                while q and q[0].t <= t + 1e-9:
                    self.held[i] = q.pop(0)
            estimate = self.observer.step(t, *self.held)
            yield estimate, tuple(self.held)
            self.next_tick += self.dt
            steps += 1

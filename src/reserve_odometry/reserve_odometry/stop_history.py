"""H09: bounded causal stop confirmations with a conservative hysteresis latch.

Only model-accepted wheel samples can contribute new evidence. Repeated held
samples may sustain a latch, but cannot enter it. This is not an independent
motion sensor: a sufficiently plausible common-mode wheel lock is unobservable.
"""
import math


class StopHistory:
    """Constant-size history; fixed H09 parameters, not a fitted detector."""

    ENTER_SPEED_MPS = 0.02
    EXIT_SPEED_MPS = 0.05
    ENTRY_MODEL_SPEED_MPS = 0.10
    MIN_PAIRS = 3
    MIN_SPAN_S = 0.20
    __slots__ = ('trusted', 'consumed', 'since', 'last_pair_t', 'count', 'stopped')

    def __init__(self):
        self.reset()

    def reset(self):
        self.trusted = [None, None]
        self.consumed = [None, None]
        self.since = None
        self.last_pair_t = None
        self.count = 0
        self.stopped = False

    def _clear_confirmation(self):
        # Do not clear consumed timestamps: held inputs must not become new votes.
        self.since = None
        self.last_pair_t = None
        self.count = 0
        self.stopped = False

    def update(self, *, t, u, predicted, command_stale, wheels, statuses, config):
        """Return whether a stop is supported at this output tick, without waiting."""
        exit_speed = min(self.EXIT_SPEED_MPS, config.stop_speed_mps)
        safe = (not command_stale and u <= config.command_deadband and
                math.isfinite(predicted) and abs(predicted) < config.stop_model_speed_mps and
                all(x is not None and math.isfinite(x.t) and math.isfinite(x.value) and
                    -1e-9 <= t - x.t <= config.max_age_s and abs(x.value) < exit_speed
                    for x in wheels))
        if not safe or abs(wheels[0].t - wheels[1].t) > config.pair_skew_s:
            self.reset()
            return False

        for i, (sample, status) in enumerate(zip(wheels, statuses)):
            if status == 'ACCEPTED':
                self.trusted[i] = sample
            elif status != 'DUPLICATE_OR_OLD':
                self.reset()
                return False
        # An asynchronous partner can arrive on the next tick. Never pretend a
        # held sample rejected earlier has become trustworthy just by waiting.
        if any(x is None for x in self.trusted):
            return False
        if any(a != b for a, b in zip(self.trusted, wheels)):
            self.reset()
            return False
        if self.stopped:
            return True

        enter_speed = min(self.ENTER_SPEED_MPS, exit_speed)
        model_entry = min(self.ENTRY_MODEL_SPEED_MPS, config.stop_model_speed_mps)
        if abs(predicted) >= model_entry or any(abs(x.value) >= enter_speed for x in wheels):
            self._clear_confirmation()
            return False
        if any(old is not None and x.t <= old for x, old in zip(wheels, self.consumed)):
            if self.last_pair_t is not None and t - self.last_pair_t > config.max_age_s:
                self._clear_confirmation()
            return False

        pair_t = max(x.t for x in wheels)
        if self.last_pair_t is not None and pair_t - self.last_pair_t > config.max_age_s:
            self._clear_confirmation()
        if self.since is None:
            self.since = pair_t
        self.last_pair_t = pair_t
        self.consumed = [x.t for x in wheels]
        self.count = min(self.count + 1, self.MIN_PAIRS)
        self.stopped = (self.count == self.MIN_PAIRS and
                        pair_t - self.since + 1e-9 >= self.MIN_SPAN_S)
        return self.stopped

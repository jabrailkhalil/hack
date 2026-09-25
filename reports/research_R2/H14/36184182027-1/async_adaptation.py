"""Opt-in R2-H14: unique accepted asynchronous pairs for disturbance only.

Apply research/R2_H14/adaptation-hook.patch first. No velocity measurement,
noise, covariance, readout, recovery, stop or Timeline equation is replaced.
"""
from typing import Optional
from .core import Config, Sample
from .guarded_readout import GuardedReadoutObserver, ReadoutConfig


class AsyncAdaptationObserver(GuardedReadoutObserver):
    def __init__(self, config: Optional[Config] = None, *,
                 readout: Optional[ReadoutConfig] = None, enabled: bool = True):
        if not hasattr(GuardedReadoutObserver, '_adapt_disturbance'):
            raise RuntimeError('Apply research/R2_H14/adaptation-hook.patch before H14 use')
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be bool')
        self._h14_enabled = enabled
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._h14_pending = [None, None]
        self._h14_last_pair_t = None
        self._h14_last_consumed = [None, None]
        self._h14_counts = dict(pairs=0, async_pairs=0, updates=0,
                               async_updates=0, hard_clears=0,
                               expired_clears=0, recheck_rejections=0)
        self._h14_last_pair = None  # fixed-size diagnostic, never used in inference
        self._h14_updated = False

    def _h14_count(self, key):
        self._h14_counts[key] = min(2**63 - 1, self._h14_counts[key] + 1)

    def _h14_clear(self):
        self._h14_pending = [None, None]
        self.adapt_previous = None

    def _adapt_disturbance(self, t, command_stale, samples, statuses, mode, predicted, gate):
        if not self._h14_enabled:
            return super()._adapt_disturbance(
                t, command_stale, samples, statuses, mode, predicted, gate)
        self._h14_updated = False
        self._h14_last_pair = None
        c = self.c
        if command_stale or any(s not in ('ACCEPTED', 'DUPLICATE_OR_OLD') for s in statuses):
            self._h14_count('hard_clears')
            self._h14_clear()
            return
        if any(s is not None and not self._valid(s, t, c.max_age_s)
               for s in self._h14_pending):
            self._h14_count('expired_clears')
            self._h14_clear()
        # Only new samples that already passed scalar velocity gates can enter.
        for i, (sample, status) in enumerate(zip(samples, statuses)):
            if sample is not None and status == 'ACCEPTED':
                consumed = self._h14_last_consumed[i]
                if consumed is None or sample.t > consumed:
                    self._h14_pending[i] = sample
        if any(s is None for s in self._h14_pending):
            return
        front, rear = self._h14_pending
        if abs(front.t - rear.t) > c.pair_skew_s:
            self._h14_pending[0 if front.t < rear.t else 1] = None
            return
        # Recheck the originally accepted values at COMPLETION time. Do not
        # project them or count their agreement as independent information.
        if (any(not self._valid(s, t, c.max_age_s) or abs(s.value) > c.max_speed_mps
                or abs(s.value - predicted) > gate for s in (front, rear))
                or abs(front.value - rear.value) > c.disagreement_mps
                or (abs(front.value) < c.stop_speed_mps
                    and abs(rear.value) < c.stop_speed_mps
                    and abs(predicted) > c.stop_model_speed_mps)):
            self._h14_count('recheck_rejections')
            self._h14_clear()
            return
        tz = (front.t + rear.t) * 0.5
        self._h14_pending = [None, None]  # consumed once, also if derivative fails
        self._h14_last_consumed = [front.t, rear.t]
        if self._h14_last_pair_t is not None and tz <= self._h14_last_pair_t:
            self.adapt_previous = None
            return
        self._h14_last_pair_t = tz
        asynchronous = mode != 'FUSED'
        self._h14_count('pairs')
        if asynchronous:
            self._h14_count('async_pairs')
        z = (front.value + rear.value) * 0.5
        old = self.adapt_previous
        update = (old is not None and 0.05 <= tz - old.t <= c.max_age_s
                  and abs((z - old.value) / (tz - old.t)) <= c.max_accel_mps2
                  and abs(z) > 0.5)
        if update:
            self._h14_count('updates')
            if asynchronous:
                self._h14_count('async_updates')
        self._h14_updated = update
        self._h14_last_pair = (front.t, rear.t, tz, t, asynchronous)
        # Reuse the EXACT derivative, tau, clipping and scalar EMA from core.
        # 'FUSED' here only selects adaptation: no speed or covariance update.
        super()._adapt_disturbance(t, False, (front, rear),
                                  ('ACCEPTED', 'ACCEPTED'), 'FUSED', predicted, gate)

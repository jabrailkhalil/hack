"""H19: bounded, causal sequential evidence; not a certified fault isolator.

Requires research/R2/H19/core.patch, applied by the isolated research factory.
No reference data, file identity, injection flags, or scientific dependencies.
"""
from dataclasses import dataclass
import math
from .core import clip
from .guarded_readout import GuardedReadoutObserver


@dataclass(frozen=True)
class SequentialConfig:
    enabled: bool = True
    threshold_s: float = 0.3
    monitor_only: bool = False
    tau_s: float = 2.0
    cap_s: float = 2.0
    reference_drift: float = 0.25
    evidence_clip: float = 3.0
    evidence_ttl_s: float = 4.0
    suspect_weight: float = 0.25

    def __post_init__(self):
        if not isinstance(self.enabled, bool) or not isinstance(self.monitor_only, bool):
            raise ValueError('enabled and monitor_only must be bool')
        for key in ('threshold_s', 'tau_s', 'cap_s', 'reference_drift',
                    'evidence_clip', 'evidence_ttl_s', 'suspect_weight'):
            value = getattr(self, key)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(key + ' must be finite and positive')
        if self.threshold_s > self.cap_s or self.suspect_weight > 1:
            raise ValueError('Invalid threshold or weight')


class SequentialEvidence:
    """Fixed slots; four CUSUM scalars, two last accepted samples, bounded age.

    C is measured in seconds; innovations and reference_drift are dimensionless.
    No independence/calibrated false-alarm probability is asserted.
    """
    __slots__ = ('options', 'positive', 'negative', 'peers', 'last_stamp',
                 'last_positive', 'suspect', 'weights', 'attribution',
                 'new_sample', 'evidence', 'epoch')

    def __init__(self, options):
        self.options = options
        self.reset()

    def reset(self):
        self.positive = [0.0, 0.0]
        self.negative = [0.0, 0.0]
        self.peers = [None, None]
        self.last_stamp = [None, None]
        self.last_positive = [None, None]
        self.epoch = [None, None]
        self.suspect = [False, False]
        self.weights = [1.0, 1.0]
        self.attribution = [False, False]
        self.new_sample = [False, False]
        self.evidence = [0.0, 0.0]

    def clear(self, i):
        self.positive[i] = self.negative[i] = 0.0
        self.suspect[i] = False
        self.last_positive[i] = None
        self.epoch[i] = None

    def update(self, t, c, samples, statuses, accepted, predicted, p_prior, command_stale):
        o = self.options
        self.weights = [1.0, 1.0]
        self.attribution = [False, False]
        self.new_sample = [False, False]
        self.evidence = [0.0, 0.0]
        if not o.enabled:
            return self.weights
        # Install both NEW hard-gate-passing candidates before looking at peers.
        # Held peers are context, never assimilated again or counted as new.
        for i in range(2):
            if i in accepted:
                self.peers[i] = samples[i]
            elif statuses[i] != 'DUPLICATE_OR_OLD':
                self.peers[i] = None
                self.last_stamp[i] = None
                self.clear(i)
            peer = self.peers[i]
            if peer is not None and not (0 <= t - peer.t <= c.max_age_s):
                self.peers[i] = None
                self.last_stamp[i] = None
                self.clear(i)
            epoch = self.epoch[i]
            if epoch is not None and t - epoch >= o.evidence_ttl_s:
                self.clear(i)
                self.last_stamp[i] = None
            last = self.last_positive[i]
            if last is not None and t - last > o.evidence_ttl_s:
                self.clear(i)
        usable = (not command_stale and all(x is not None for x in self.peers))
        if usable:
            f, r = self.peers
            skew = abs(f.t-r.t)
            usable = skew <= c.pair_skew_s and min(abs(f.value), abs(r.value)) > 0.5
        if usable:
            norms = [math.sqrt(p_prior+c.wheel_sigma_mps**2 +
                               c.process_noise_v*max(0.0, t-x.t)) for x in self.peers]
            innovations = [(x.value-predicted)/scale for x, scale in zip(self.peers, norms)]
            pair_scale = math.sqrt(2*c.wheel_sigma_mps**2+(c.max_accel_mps2*skew)**2)
            difference = (f.value-r.value)/pair_scale
            for i in range(2):
                ri, rj = innovations[i], innovations[1-i]
                di = difference if i == 0 else -difference
                self.attribution[i] = (abs(ri) >= abs(rj)+0.5 and abs(rj) <= 1.0
                                       and ri*di > 0.0 and abs(di) > 0.5)
                if self.attribution[i]:
                    self.evidence[i] = math.copysign(min(abs(ri), abs(di), o.evidence_clip), ri)
        for i in accepted:
            sample = samples[i]
            old = self.last_stamp[i]
            # Guard against duplicate/held samples even when called directly.
            if old is not None and sample.t <= old:
                continue
            self.new_sample[i] = True
            self.last_stamp[i] = sample.t
            if old is None or sample.t-old > c.max_age_s:
                self.clear(i)
                dt = 0.0
            else:
                dt = sample.t-old
            if self.epoch[i] is None:
                self.epoch[i] = sample.t
            evidence = self.evidence[i]
            decay = math.exp(-dt/o.tau_s)
            self.positive[i] = clip(decay*self.positive[i] + dt*(evidence-o.reference_drift), 0.0, o.cap_s)
            self.negative[i] = clip(decay*self.negative[i] + dt*(-evidence-o.reference_drift), 0.0, o.cap_s)
            if dt > 0 and abs(evidence) > o.reference_drift:
                self.last_positive[i] = sample.t
            level = max(self.positive[i], self.negative[i])
            if level >= o.threshold_s:
                self.suspect[i] = True
            elif level <= o.threshold_s/4:
                self.suspect[i] = False
        # A remembered alarm NEVER resolves a currently ambiguous pair.
        flagged = [i for i in range(2) if self.suspect[i]]
        if len(flagged) == 1 and usable and not o.monitor_only:
            i = flagged[0]
            if self.attribution[i]:
                self.weights[i] = o.suspect_weight
        return self.weights


class SequentialFaultObserver(GuardedReadoutObserver):
    """Guarded v7 + optional H19; readout/hard gates/stop/recovery unchanged."""
    def __init__(self, config=None, *, readout=None, sequential=None):
        self.sequential = sequential or SequentialConfig()
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._h19_detector = SequentialEvidence(self.sequential)

    def _h19_weights(self, t, samples, statuses, accepted, predicted, p_prior, command_stale):
        return self._h19_detector.update(t, self.c, samples, statuses, accepted,
                                         predicted, p_prior, command_stale)

"""H2: bounded replay of already received measurements at their measurement times.

No published historical output is rewritten. Public distance integrates public
velocity, so H2 does not silently include the separate H8 path-correction idea.
"""
from copy import deepcopy
from dataclasses import replace
from tram_lab.types import VEHICLE_TOPICS, Estimate
from tram_lab.hypotheses.concept_b import AdaptiveEKF
from .core import checked_positive


class Estimator:
    def __init__(self, config=None):
        self.reset(config or {})

    def reset(self, config):
        self.config = dict(config)
        self.window_ns = round(checked_positive(config,"history_s",.5)*1e9)
        if not 250_000_000 <= self.window_ns <= 1_000_000_000:
            raise ValueError("history must be 0.25 to 1 second")
        self.anchor_ns = self.last_ns = None
        self.anchor = AdaptiveEKF(config)
        self.events, self.snapshots = [], {}
        self.new_keys = set()
        self.dropped = self.max_buffer = 0
        self.s = 0.; self.v = None

    def update(self, event):
        if event.topic not in VEHICLE_TOPICS:
            raise ValueError("external measurements forbidden")
        if self.anchor_ns is not None and event.stamp_ns <= self.anchor_ns:
            self.dropped += 1
            return
        if len(self.events) >= 10000:
            raise ValueError("bounded history overflow")
        self.events.append(event)
        self.new_keys.add((event.topic,event.sequence))

    def predict(self, now):
        if self.last_ns is not None and now < self.last_ns:
            raise ValueError("clock rollback requires reset")
        if self.last_ns == now:
            return self.output
        if any(e.received_ns > now for e in self.events):
            raise ValueError("future receipt")
        if self.anchor_ns is None:
            self.anchor_ns = now-50_000_000
        target_anchor = max(self.anchor_ns,now-self.window_ns)
        eligible = [stamp for stamp in self.snapshots if stamp <= target_anchor]
        if eligible:
            self.anchor_ns = max(eligible)
            self.anchor = self.snapshots[self.anchor_ns]
        self.dropped += sum(e.stamp_ns <= self.anchor_ns and (e.topic,e.sequence) in self.new_keys for e in self.events)
        self.events = [e for e in self.events if e.stamp_ns > self.anchor_ns]
        self.new_keys.clear()
        self.max_buffer = max(self.max_buffer,len(self.events))
        inner = deepcopy(self.anchor)
        tick = self.anchor_ns+50_000_000
        snapshots = {}
        result = None
        def step(t):
            result = inner.predict(t)
            snapshots[t] = deepcopy(inner)
            return result
        for event in sorted((e for e in self.events if e.stamp_ns <= now),key=lambda e:(e.stamp_ns,e.sequence)):
            while tick < event.stamp_ns:
                result = step(tick); tick += 50_000_000
            # This pseudo-receipt is internal retrospective replay, AFTER actual delivery.
            inner.update(replace(event,received_ns=event.stamp_ns))
        while tick <= now:
            result = step(tick); tick += 50_000_000
        self.snapshots = snapshots
        if result is None:
            raise ValueError("H2 requires the common 50 ms publication grid")
        if result.velocity is not None:
            if self.last_ns is not None and self.v is not None:
                self.s += (now-self.last_ns)/1e9*.5*(self.v+result.velocity)
            self.v = result.velocity
        self.last_ns = now
        self.output = Estimate(now,result.velocity,self.s if result.velocity is not None else None,result.status,
                               {**result.diagnostics,"late_dropped":self.dropped,"history_events":len(self.events),
                                "history_snapshots":len(self.snapshots)})
        return self.output

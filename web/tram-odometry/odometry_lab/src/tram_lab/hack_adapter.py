"""Pinned hack kernels on the lab receipt clock; no reference inputs."""
from dataclasses import asdict
from pathlib import Path
import json
import math

from .types import COMMAND, FRONT, REAR, VEHICLE_TOPICS, Estimate
from .vendor.hack.core import Config, Observer, Sample
from .vendor.hack.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from .vendor.hack.timeline import Timeline

PROFILES = dict(hack_v5='adaptive_v5', hack_v6='time_aligned_v6',
                hack_v7='guarded_readout_v7', hack_v8='champion_v8_extracted')


def profile(name):
    return json.loads((Path(__file__).parent / 'vendor/hack/config' / (PROFILES[name] + '.json')).read_text())


class HackEstimator:
    def reset(self, config):
        document = profile(config.get('profile', 'hack_v8'))
        values = {**document['config'], **config.get('core', {})}
        core = Config(**values)
        readout = {**document.get('readout', {}), **config.get('readout', {})}
        self.observer = (GuardedReadoutObserver(core, readout=ReadoutConfig(**readout))
                         if config.get('profile', 'hack_v8') in ('hack_v7', 'hack_v8') else Observer(core))
        self.timeline = Timeline(self.observer, rate_hz=20, delay_s=0)
        self.scale = float(config.get('wheel_scale', 1 / 3.6))
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError('wheel_scale must be finite and positive')
        self.origin = self.last_ns = None
        self.pending = []
        self.latest = {}

    def update(self, event):
        if event.topic not in VEHICLE_TOPICS:
            raise ValueError('only vehicle inputs are permitted')
        self.pending.append(event)

    def predict(self, time_ns):
        if self.last_ns is not None and time_ns <= self.last_ns:
            raise ValueError('clock must increase; reset before a new episode')
        if self.origin is None:
            self.origin = time_ns
        for event in self.pending:
            if event.received_ns > time_ns:
                raise ValueError('future receipt')
            channel = (COMMAND, FRONT, REAR).index(event.topic)
            value = float(event.data['position' if channel == 0 else 'velocity'])
            sample = Sample((event.stamp_ns - self.origin) / 1e9,
                            value / 15 if channel == 0 else value * self.scale)
            if self.timeline.ingest(channel, sample):
                self.latest[event.topic] = event
        self.pending.clear()
        now = (time_ns - self.origin) / 1e9
        for i, queue in enumerate(self.timeline.queues):
            while queue and queue[0].t <= now:
                self.timeline.held[i] = queue.pop(0)
        result = self.observer.step(now, *self.timeline.held)
        self.last_ns = time_ns
        diag = asdict(result)
        diag['rejected_values'] = self.timeline.dropped
        wheels = [self.latest[t] for t in (FRONT, REAR) if t in self.latest]
        if wheels:
            diag['age_s'] = max(time_ns - e.received_ns for e in wheels) / 1e9
            diag['measurement_age_s'] = max(time_ns - e.stamp_ns for e in wheels) / 1e9
        if result.mode == 'WAITING_FOR_INITIALIZATION':
            return Estimate(time_ns, None, None, 'unavailable', diag)
        return Estimate(time_ns, result.v, result.s,
                        'model' if result.mode == 'MODEL_ONLY' else 'ok', diag)

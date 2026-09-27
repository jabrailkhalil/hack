"""Invented plant, not a substitute for the official tram data.

Truth uses a different drive law and time constant from the estimators. Only
wheel/controller events reach an estimator. Seeds separate whole train/test
trips; absolute timestamps and the true plant parameters are never features.
"""
from dataclasses import replace
import math
import numpy as np
from tram_lab.types import Event, FRONT, REAR, COMMAND

BASE_NS = 1_750_000_000_000_000_000
DURATION_S = 160
SCENARIOS = {
    "clean": None,
    "front_drop_1s": (FRONT, "drop", 30, 31, 0),
    "front_drop_74s": (FRONT, "drop", 20, 94, 0),
    "both_drop_20s": ("both", "drop", 30, 50, 0),
    "front_spike_2s": (FRONT, "spike", 25, 27, 7),
    "front_freeze_8s": (FRONT, "freeze", 25, 33, 0),
    "common_slip_4s": ("both", "spike", 22, 26, 2),
    "common_lock_3s": ("both", "zero", 45, 48, 0),
    "rear_scale_10pct": (REAR, "scale", 25, 45, 1.1),
    "front_delay_250ms": (FRONT, "delay", 25, 35, .25),
    "command_drop_50s": (COMMAND, "drop", 15, 65, 0),
    "plant_gain_change": None,
}
TRAIN_SEEDS = (1, 2, 3, 4)
VALIDATION_SEEDS = (51, 52)
TEST_SEEDS = (101, 102, 103, 104)


def generate(seed, scenario="clean"):
    rng = np.random.default_rng(seed)
    dt = .01
    t = np.arange(round(DURATION_S / dt) + 1) * dt
    command = np.zeros(len(t))
    schedule = [(7, 0), (27, .75), (7, 0), (17, -.7), (7, 0),
                (27, .95), (9, 0), (18, -.8), (8, 0), (25, .6), (20, -1)]
    boundary = 0
    for duration, level in schedule:
        stop = boundary + int(round((duration + rng.uniform(-1.5, 1.5)) / dt))
        u = int(np.clip(round(level * 15 + (rng.uniform(-1, 1) if level else 0)), -15, 15))
        command[boundary:stop] = u / 15
        boundary = stop
    velocity, distance = np.zeros(len(t)), np.zeros(len(t))
    drive = 0.
    kt, kb = 1.75 * rng.uniform(.92, 1.08), 2.7 * rng.uniform(.92, 1.08)
    for i in range(1, len(t)):
        v, u = velocity[i-1], command[i-1]
        gain = 1.25 if scenario == "plant_gain_change" and t[i] >= 75 else 1.
        target = gain * (kt * max(u, 0) / math.sqrt(1 + (v / 17) ** 2) +
                         kb * min(u, 0) * math.tanh(v / .25))
        tau = .55 if u >= 0 else .25
        drive += -math.expm1(-dt / tau) * (target - drive)
        drag = .055 * math.tanh(v / .25) + .004 * v + .00035 * v * v
        perturbation = .035 * math.sin(t[i] / 19 + seed) + .05 * u * abs(u) * v / (v + 3)
        a = drive - drag + perturbation
        velocity[i] = max(0, v + dt * a)
        if v < .03 and u <= 0:
            velocity[i] = 0.
        distance[i] = distance[i-1] + .5 * dt * (v + velocity[i])
    events = []
    for index in range(0, len(t), 5):
        stamp = BASE_NS + index * 10_000_000
        events.append(Event(COMMAND, stamp, stamp + 1_000_000, len(events),
                            {"position": int(round(command[index] * 15))}))
    for topic, offset, scale in ((FRONT, 0, 1.0015), (REAR, 3, .9985)):
        for index in range(offset, len(t), 10):
            stamp = BASE_NS + index * 10_000_000
            value = max(0., velocity[index] * scale + rng.normal(0, .015))
            latency = max(0, round((.048 + rng.normal(0, .006)) * 1e9))
            events.append(Event(topic, stamp, stamp + latency, len(events), {"velocity": value * 3.6}))
    events.sort(key=lambda e: (e.received_ns, e.sequence))
    fault = SCENARIOS[scenario]
    if fault is not None:
        target, kind, start, end, amplitude = fault
        altered, frozen = [], {}
        for event in events:
            elapsed = (event.received_ns - BASE_NS) / 1e9
            affected = event.topic == target or (target == "both" and event.topic in (FRONT, REAR))
            if affected and start <= elapsed < end:
                if kind == "drop":
                    continue
                if kind == "delay":
                    event = replace(event, received_ns=event.received_ns + round(amplitude * 1e9))
                else:
                    data = dict(event.data)
                    if kind == "freeze":
                        data["velocity"] = frozen.get(event.topic, data["velocity"])
                    elif kind == "zero":
                        data["velocity"] = 0.
                    elif kind == "scale":
                        data["velocity"] *= amplitude
                    else:
                        data["velocity"] += amplitude * 3.6
                    event = replace(event, data=data)
            elif event.topic in (FRONT, REAR):
                frozen[event.topic] = event.data["velocity"]
            altered.append(event)
        events = sorted(altered, key=lambda e: (e.received_ns, e.sequence))
    return events, t, velocity, distance, command


def held_inputs(events, query_ns):
    """Causal zero-order-held wheels/controller, also used for train labels.

This function does not receive truth. Future wheel values may be training
TARGETS only; the fitting code never applies it across split boundaries.
"""
    values = np.full((len(query_ns), 3), np.nan)
    fresh = np.zeros(len(query_ns), dtype=bool)
    index, latest = 0, {}
    for row, time_ns in enumerate(query_ns):
        while index < len(events) and events[index].received_ns <= time_ns:
            event = events[index]
            latest[event.topic] = event
            index += 1
        for col, topic in enumerate((FRONT, REAR, COMMAND)):
            event = latest.get(topic)
            if event:
                value = event.data["position" if topic == COMMAND else "velocity"]
                values[row, col] = value / (15 if topic == COMMAND else 3.6)
        fresh[row] = all(topic in latest and max(time_ns - latest[topic].received_ns,
                          time_ns - latest[topic].stamp_ns) <= 250_000_000
                         for topic in (FRONT, REAR, COMMAND))
    return values, fresh

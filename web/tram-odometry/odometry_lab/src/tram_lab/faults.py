from dataclasses import replace
import math
import numpy as np
from .types import FRONT, REAR, VEHICLE_TOPICS


def inject_faults(events, faults=(), seed=0, start_ns=None):
    """Explicit bounded offline schedule of corrupted input deliveries.

    Order is preserved except for configured delivery delays. Header stamps are
    unchanged; the replay still only sees each event at its new arrival time.
    GNSS objects pass through unchanged. Ranges are [start_s, end_s).
    """
    rng = np.random.default_rng(seed)
    faults = list(faults)
    for f in faults:
        if f.get("kind") not in {"drop", "delay", "spike", "freeze", "scale"}:
            raise ValueError("unknown fault kind")
        topics = f.get("topics", [FRONT, REAR])
        if not topics or not set(topics) <= VEHICLE_TOPICS:
            raise ValueError("faults may only target vehicle topics")
        if f.get("end_s", math.inf) <= f.get("start_s", 0):
            raise ValueError("fault end must be after its start")
        if not 0 <= f.get("probability", 1) <= 1:
            raise ValueError("probability must be in [0,1]")
        if f.get("delay_s", 0) < 0:
            raise ValueError("delivery delays must be nonnegative")
    if not faults:
        yield from events
        return
    frozen, last_values, result = {}, {}, []
    for event in events:
        if start_ns is None:
            start_ns = event.received_ns
        if event.topic not in VEHICLE_TOPICS:
            result.append(event)
            continue
        original = event
        elapsed = (event.received_ns - start_ns) / 1e9
        field = "velocity" if event.topic in (FRONT, REAR) else "position"
        drop = False
        for i, fault in enumerate(faults):
            if event.topic not in fault.get("topics", [FRONT, REAR]):
                continue
            if not fault.get("start_s", 0) <= elapsed < fault.get("end_s", math.inf):
                continue
            if rng.random() >= fault.get("probability", 1):
                continue
            kind = fault["kind"]
            if kind == "drop":
                drop = True
                break
            if kind == "delay":
                event = replace(event, received_ns=event.received_ns + round(fault.get("delay_s", 0.2) * 1e9))
                continue
            data = dict(event.data)
            if kind == "scale":
                data[field] *= fault.get("factor", 1.1)
            elif kind == "spike":
                data[field] += fault.get("amplitude", 10.0)
            elif kind == "freeze":
                key = (i, event.topic)
                frozen.setdefault(key, last_values.get(event.topic, data[field]))
                data[field] = frozen[key]
            event = replace(event, data=data)
        last_values[original.topic] = original.data[field]
        if not drop:
            result.append(event)
    yield from sorted(result, key=lambda e: (e.received_ns, e.sequence))

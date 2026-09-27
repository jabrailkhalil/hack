"""Message conversion with no ROS imports; shared by ROS and adapter parity tests."""
import math
from .types import Event, FRONT, REAR, COMMAND, VEHICLE_TOPICS


def event_from_message(topic, message, received_ns, sequence):
    if topic not in VEHICLE_TOPICS:
        raise ValueError("only vehicle inputs are allowed")
    stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
    data = {"position": int(message.position)} if topic == COMMAND else {"velocity": float(message.velocity)}
    return Event(topic, int(stamp), int(received_ns), int(sequence), data, message.header.frame_id)


def trace_safe(value):
    """Keep malformed input floats in strict JSON as strings accepted by float()."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: trace_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [trace_safe(item) for item in value]
    return value

from .types import VEHICLE_TOPICS


class EventClock:
    """Shared deterministic scheduler; inputs at a tick are processed before that tick.

    push() flushes strictly earlier ticks. advance() closes the current time boundary.
    The ROS adapter uses the same interface with its actual callback arrival trace.
    """

    def __init__(self, estimator, start_ns, period_ns=50_000_000):
        if period_ns <= 0:
            raise ValueError("period must be positive")
        self.estimator = estimator
        self.period_ns = int(period_ns)
        self.next_ns = int(start_ns)
        self.last_boundary_ns = int(start_ns)

    def advance(self, time_ns, inclusive=True):
        if time_ns < self.last_boundary_ns:
            raise ValueError("receipt clock rollback requires reset")
        self.last_boundary_ns = time_ns
        while self.next_ns < time_ns or (inclusive and self.next_ns == time_ns):
            yield self.estimator.predict(self.next_ns)
            self.next_ns += self.period_ns

    def push(self, event):
        yield from self.advance(event.received_ns, inclusive=False)
        if event.topic in VEHICLE_TOPICS:
            self.estimator.update(event)


def replay(events, estimator, start_ns, end_ns, period_ns=50_000_000):
    clock = EventClock(estimator, start_ns, period_ns)
    previous_key = None
    for event in events:
        key = (event.received_ns, event.sequence)
        if previous_key is not None and key < previous_key:
            raise ValueError("events must be ordered by receipt timestamp and sequence")
        previous_key = key
        if event.received_ns > end_ns:
            break
        yield from clock.push(event)
    yield from clock.advance(end_ns)

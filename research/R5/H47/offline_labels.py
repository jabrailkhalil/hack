"""Offline-only H47 label interface. Does not read, clean, or regenerate H42.

Horizontal teacher magnitudes never supply signed speed or an online feature.
This pure interface has only synthetic tests until producer payloads are verified.
"""
from dataclasses import dataclass
import math
from typing import Iterable, Optional
from reserve_odometry.core import Sample


@dataclass(frozen=True)
class TeacherPoint:
    t: float
    speed_magnitude: float
    accepted: bool


def unique_nearest(points: Iterable[TeacherPoint], t: float) -> Optional[TeacherPoint]:
    if not math.isfinite(t):
        return None
    candidates = [p for p in points if p.accepted and math.isfinite(p.t)
                  and math.isfinite(p.speed_magnitude) and p.speed_magnitude >= 0
                  and abs(p.t - t) <= .05]
    if not candidates:
        return None
    candidates.sort(key=lambda p: abs(p.t - t))
    if len(candidates) > 1 and math.isclose(abs(candidates[0].t - t),
            abs(candidates[1].t - t), rel_tol=0., abs_tol=1e-12):
        return None  # includes duplicate timestamps, not an arbitrary tie-break
    return candidates[0]


def proxy_pair_labels(front: Sample, rear: Sample,
                      front_teacher: Optional[TeacherPoint],
                      rear_teacher: Optional[TeacherPoint], *, features_ready: bool):
    """Returns (front_label,rear_label), where 1 means faulty PROXY, or None.

    Frozen H42 acceptance is necessary, not proof of physical sensor health.
    Ambiguous/common-mode pairs abstain. No teacher source time is shifted.
    """
    if not features_ready:
        return None
    for wheel, target in ((front, front_teacher), (rear, rear_teacher)):
        if (target is None or not target.accepted
                or not all(math.isfinite(v) for v in
                           (wheel.t, wheel.value, target.t, target.speed_magnitude))
                or target.speed_magnitude < 1.0 or abs(wheel.value) < 1.0
                or abs(target.t - wheel.t) > .05):
            return None
    errors = (abs(abs(front.value) - front_teacher.speed_magnitude),
              abs(abs(rear.value) - rear_teacher.speed_magnitude))
    clean = tuple(e <= .20 for e in errors)
    bad = tuple(e >= .50 for e in errors)
    if all(clean):
        return (0, 0)
    if bad[0] and clean[1]:
        return (1, 0)
    if bad[1] and clean[0]:
        return (0, 1)
    return None

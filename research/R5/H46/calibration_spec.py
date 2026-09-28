"""Bounded, untrained H46 optimization primitives. No data loader or optimizer.

Test invocations are not real-data fitting. Complete fitting remains blocked by
missing native-verified teacher/atlas payloads and is not claimed implemented.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from runtime_profile import ForceParameters, LABELS

SHRINKAGE = 0.1
MAX_NFEV = 80
MAX_RESIDUAL_CALLS = 1000


def joint_vectors(theta: list[float]) -> tuple[ForceParameters, dict[str, ForceParameters]]:
    if len(theta) != 6:
        raise ValueError('Joint model has exactly two three-parameter vectors')
    a, b = ForceParameters(*theta[:3]), ForceParameters(*theta[3:])
    center = ForceParameters(*(0.5*(x+y) for x,y in zip(theta[:3],theta[3:])))
    return center, {LABELS[0]: a, LABELS[1]: b}


def shrinkage_residuals(theta: list[float], scales: list[float]) -> list[float]:
    """Shared-vector elimination for equal quadratic shrinkage, not data weighting."""
    center, _ = joint_vectors(theta)
    if len(scales) != 3 or any(not math.isfinite(x) or x <= 0 for x in scales):
        raise ValueError('Three positive finite normalization scales required')
    common = (center.force_per_mass, center.power_per_mass, center.brake_per_mass)
    return [math.sqrt(SHRINKAGE)*(theta[j+i]-common[i])/scales[i]
            for j in (0, 3) for i in range(3)]


def soft_l1_residual(error: float, scale: float = .2) -> float:
    """Signed residual whose square is 2*(sqrt(1+(error/scale)^2)-1).

    Allows a linear least-squares solver loss to robustify only data residuals,
    leaving appended shrinkage terms genuinely quadratic. Stable near zero.
    """
    if not math.isfinite(error) or not math.isfinite(scale) or scale <= 0:
        raise ValueError('Finite error and positive scale required')
    x = error / scale
    if not math.isfinite(x):
        raise ValueError('Normalized residual overflow')
    return x * math.sqrt(2. / (math.hypot(1., x) + 1.))


@dataclass
class ObjectiveBudget:
    """One shared counter for joint and control, increment before every call."""
    calls: int = 0

    def invoke(self, fn, *args, **kwargs):
        if self.calls >= MAX_RESIDUAL_CALLS:
            raise RuntimeError('H46 fixed residual-call budget exhausted')
        self.calls += 1  # failures and finite-difference calls consume the budget
        return fn(*args, **kwargs)

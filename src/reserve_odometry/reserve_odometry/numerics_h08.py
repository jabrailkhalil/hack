"""H08 opt-in predictor. No sensors, history, adaptive loops or external packages."""
import math
from typing import Callable, Tuple


def _mean_fraction(x: float) -> float:
    """1 - (1 - exp(-x))/x, including its continuous value at zero."""
    if x < 1e-4:
        return x * (0.5 + x * (-1.0 / 6 + x * (1.0 / 24 +
                    x * (-1.0 / 120 + x / 720))))
    return 1.0 + math.expm1(-x) / x


def predict(dt: float, tau: float, drive: float, velocity: float,
            target: float, disturbance: float, resistance: Callable[[float], float],
            max_accel: float, max_speed: float) -> Tuple[float, float]:
    """Return (end drive acceleration, predicted speed) at a held drive target.

    The exponential drive integral is exact for that held target. Resistance is
    evaluated at a predicted midpoint. This is not an exact nonlinear solution:
    target depends on the *starting* speed; clipping reduces the formal order.
    Sign-reversal protection remains in Observer, shared with the legacy path.
    """
    if not math.isfinite(dt) or dt < 0 or not math.isfinite(tau) or tau <= 0:
        raise ValueError('Expected finite dt >= 0 and finite tau > 0')
    if dt == 0:
        return drive, velocity
    change = target - drive
    x = dt / tau
    mean_half = drive + change * _mean_fraction(0.5 * x)
    half_accel = max(-max_accel, min(max_accel,
                     mean_half - resistance(velocity) + disturbance))
    midpoint = max(-max_speed, min(max_speed, velocity + 0.5 * dt * half_accel))
    mean_drive = drive + change * _mean_fraction(x)
    acceleration = max(-max_accel, min(max_accel,
                       mean_drive - resistance(midpoint) + disturbance))
    end_drive = drive - math.expm1(-x) * change
    predicted = max(-max_speed, min(max_speed, velocity + dt * acceleration))
    return end_drive, predicted

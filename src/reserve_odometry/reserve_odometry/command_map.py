"""R3-H24 opt-in static command map. Dynamics and all v8 guards are inherited."""
from dataclasses import dataclass
import math
from .guarded_readout import GuardedReadoutObserver


@dataclass(frozen=True)
class CommandMap:
    traction: tuple
    braking: tuple
    enabled: bool = True

    def __post_init__(self):
        if not isinstance(self.enabled, bool):
            raise ValueError('enabled must be a bool')
        for name in ('traction', 'braking'):
            values = tuple(float(x) for x in getattr(self, name))
            if len(values) != 3 or not all(math.isfinite(x) for x in values):
                raise ValueError('map requires three finite internal ordinates')
            if not 0.0 <= values[0] <= values[1] <= values[2] <= 1.0:
                raise ValueError('map ordinates must be monotone within [0,1]')
            object.__setattr__(self, name, values)

    def value(self, x, traction):
        if not math.isfinite(x):
            raise ValueError('nonfinite normalized command')
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        knots = (0.0, *(self.traction if traction else self.braking), 1.0)
        scaled = 4.0 * x
        j = min(3, int(scaled))
        return knots[j] + (scaled - j) * (knots[j + 1] - knots[j])


class CommandMapObserver(GuardedReadoutObserver):
    """Only drive_target differs when enabled; two immutable three-value tuples."""
    def __init__(self, config=None, *, readout=None, command_map=None):
        self.command_map = command_map
        super().__init__(config, readout=readout)

    def drive_target(self, u, v):
        if self.command_map is None or not self.command_map.enabled:
            # Exact original power-law arithmetic, never a table approximation.
            return super().drive_target(u, v)
        c = self.c
        x = max(0.0, min(1.0, (abs(u) - c.command_deadband) / (1.0 - c.command_deadband)))
        q = self.command_map.value(x, u >= 0.0)
        if u >= 0.0:
            force = min(c.efficiency * c.gear_ratio * c.total_motor_torque_nm /
                        c.wheel_radius_m, c.max_power_w / max(abs(v), 1.0))
            return c.travel_direction * q * force / c.mass_kg
        return -math.tanh(v / 0.20) * q * c.max_brake_force_n / c.mass_kg

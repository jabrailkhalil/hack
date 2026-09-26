"""R4-H37: opt-in force-command interpretation under an unchanged power cap.

This is a competing command interpretation, not a manufacturer specification.
Only drive_target's nonnegative traction branch changes. Runtime is stdlib-only;
no new history, labels, measurement timing, or feedback/adaptation rules.
"""
from .guarded_readout import GuardedReadoutObserver


class TractionPowerObserver(GuardedReadoutObserver):
    def __init__(self, config=None, *, readout=None, enabled=False):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be bool'):
        self._h37_enabled = enabled
        super().__init__(config, readout=readout)

    def drive_target(self, u, v):
        if not self._h37_enabled or u <= 0.0:
            return super().drive_target(u, v)
        c = self.c
        q = max(0.0, (abs(u) - c.command_deadband) / (1 - c.command_deadband))
        q = min(1.0, q) ** c.command_exponent
        force = c.efficiency * c.gear_ratio * c.total_motor_torque_nm / c.wheel_radius_m
        power_force = c.max_power_w / max(abs(v), 1.0)
        if force <= power_force:
            # Preserve baseline arithmetic where the two interpretations coincide.
            return c.travel_direction * q * force / c.mass_kg
        return c.travel_direction * min(q * force, power_force) / c.mass_kg

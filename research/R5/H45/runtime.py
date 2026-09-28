"""R5-H45 uncalibrated research prototype. Inputs already use SI units.

No teacher, fitting, NumPy or new ROS default. Positive frozen multiplicative
factors are applied consistently to core and guarded readout. The original raw
wheel gate is also run so downscaling cannot rescue an invalid input. Values in
unit tests are fixtures, not fitted candidate parameters.
"""
from dataclasses import dataclass
import math
from typing import Optional

from reserve_odometry.core import Config, Estimate, Observer, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig


@dataclass(frozen=True)
class ResidualScale:
    front: float = 1.0
    rear: float = 1.0
    enabled: bool = False

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError('enabled must be a boolean')
        for name in ('front', 'rear'):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (float, int))
                    or not math.isfinite(value) or not 0.97 <= value <= 1.03):
                raise ValueError(f'{name} residual factor must be finite in [0.97, 1.03]')

    @property
    def active(self):
        return self.enabled and (self.front != 1.0 or self.rear != 1.0)


class _RawWheelGate:
    """Only the five bounded fields consumed by the canonical raw wheel gate.

    This is NOT an Observer instance or a second motion model. Executing the
    unbound canonical methods avoids maintaining a subtly different gate copy.
    """
    __slots__ = ('c', 'used', 'raw_previous', 'rate_anomaly_times',
                 'reacquire_blocked_until')
    _valid = Observer._valid

    def __init__(self, config):
        self.c = config
        self.used = [None, None]
        self.raw_previous = [None, None]
        self.rate_anomaly_times = [None, None]
        self.reacquire_blocked_until = -math.inf


class ResidualScaleObserver(GuardedReadoutObserver):
    """Fixed residual scale; no learned values are shipped with this prototype.

    All inherited states use calibrated SI measurements. Five extra raw-gate
    fields plus two ephemeral input references are bounded independently of
    stream length. Enabled identity and disabled operation delegate exactly to
    the full v8 observer; no scalar gain or output integral is approximated.
    """
    def __init__(self, config: Config, *, calibration: ResidualScale,
                 readout: ReadoutConfig):
        if not isinstance(config, Config) or not isinstance(readout, ReadoutConfig):
            raise TypeError('Explicit Config and ReadoutConfig are required')
        if not isinstance(calibration, ResidualScale):
            raise TypeError('Explicit ResidualScale is required')
        self._calibration = calibration
        super().__init__(config, readout=readout)

    @property
    def calibration(self):
        return self._calibration

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self._raw_gate = _RawWheelGate(self.c)
        self._raw_inputs = None

    def _scale(self, sample: Optional[Sample], factor: float):
        # Invalid/out-of-range raw samples remain invalid in the inner gates.
        # In particular, avoid overflow while multiplying already invalid data.
        if (sample is None or not math.isfinite(sample.value)
                or abs(sample.value) > self.c.max_speed_mps or factor == 1.0):
            return sample
        return Sample(sample.t, sample.value * factor)

    def _wheel(self, index, sample, t):
        if not self._calibration.active:
            return Observer._wheel(self, index, sample, t)
        if self._raw_inputs is None:
            raise RuntimeError('Raw gate must be evaluated inside step()')
        raw, raw_status = Observer._wheel(self._raw_gate, index,
                                         self._raw_inputs[index], t)
        corrected, corrected_status = Observer._wheel(self, index, sample, t)
        self.reacquire_blocked_until = max(self.reacquire_blocked_until,
                                           self._raw_gate.reacquire_blocked_until)
        if raw_status not in ('CANDIDATE', 'DUPLICATE_OR_OLD'):
            return None, raw_status
        if corrected is None:
            return None, corrected_status
        if raw is None:
            return None, raw_status
        return corrected, corrected_status

    def step(self, t: float, command: Optional[Sample] = None,
             front: Optional[Sample] = None, rear: Optional[Sample] = None) -> Estimate:
        if not self._calibration.active:
            return super().step(t, command, front, rear)
        self._raw_inputs = (front, rear)
        try:
            return super().step(t, command,
                                self._scale(front, self._calibration.front),
                                self._scale(rear, self._calibration.rear))
        finally:
            self._raw_inputs = None

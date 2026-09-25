"""Explicit H13 activation, preserving canonical Config and guarded readout."""
from .guarded_readout import GuardedReadoutObserver


class IntervalReadoutObserver(GuardedReadoutObserver):
    def __init__(self, config=None, *, readout=None, enabled=True, endpoint_control=False):
        if type(enabled) is not bool or type(endpoint_control) is not bool:
            raise ValueError('H13 enable/control switches must be bool')
        self._interval_enabled = enabled
        self._interval_endpoint_control = endpoint_control
        super().__init__(config, readout=readout)

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        if self._interval_history is not None:
            self._interval_history.endpoint_control = self._interval_endpoint_control

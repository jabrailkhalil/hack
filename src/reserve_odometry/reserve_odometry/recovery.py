"""H06: opt-in, bounded evidence-based reacquisition (research, not default).

Only controller/front/rear samples are accepted. This policy does not provide
an independent anchor: a dynamically consistent common-mode bias is ambiguous.
"""
from dataclasses import dataclass

from .core import Config, Observer, clip


@dataclass
class RecoveryConfig(Config):
    """Type tag for the paired research runner; no changed physical parameters."""


class RecoveryObserver(Observer):
    """One preregistered policy; O(1) extra state and O(1) work per fresh pair."""

    EVIDENCE_CAP_S = 0.4
    MIN_DWELL_S = 0.4
    EXTRA_STEP_FACTOR = 0.5
    MIN_EXCITATION_MPS2 = 0.15
    ACCEL_MISMATCH_MPS2 = 0.35
    PAIR_DISAGREEMENT_MPS = 0.2

    def reset(self, *, velocity=None, position=0.0):
        super().reset(velocity=velocity, position=position)
        self.recovery_evidence_s = 0.0
        self._recovery_previous_v = self.v
        self._recovery_command_valid = False

    def _clear_reacquire(self):
        super()._clear_reacquire()
        self.recovery_evidence_s = 0.0

    def step(self, t, command=None, front=None, rear=None):
        # Capture the pre-prediction state. In the policy hook drive_a has
        # already been updated by core.step; corrected output acceleration is
        # deliberately NOT used as model evidence.
        self._recovery_previous_v = self.v
        self._recovery_command_valid = (
            self._valid(command, t, self.c.command_timeout_s)
            and abs(command.value) <= 1.000001
        )
        return super().step(t, command, front, rear)

    def _reacquire_dwell(self, samples, previous):
        # Called only after ALL original pair/residual/zero-lock hard gates.
        current = self.reacquire_previous
        if previous is None:
            self.recovery_evidence_s = 0.0
        else:
            dt_pair = current.t - previous.t
            if not 0.05 <= dt_pair <= self.c.max_age_s:
                self.recovery_evidence_s = 0.0
            else:
                wheel_a = (current.value - previous.value) / dt_pair
                model_a = clip(
                    self.drive_a - self.resistance(self._recovery_previous_v)
                    + self.disturbance,
                    -self.c.max_accel_mps2, self.c.max_accel_mps2,
                )
                good = (
                    self._recovery_command_valid
                    and abs(samples[0].value - samples[1].value)
                    <= min(self.c.disagreement_mps, self.PAIR_DISAGREEMENT_MPS)
                    and abs(wheel_a) >= self.MIN_EXCITATION_MPS2
                    and abs(model_a) >= self.MIN_EXCITATION_MPS2
                    and wheel_a * model_a > 0.0
                    and abs(wheel_a - model_a) <= self.ACCEL_MISMATCH_MPS2
                )
                delta = dt_pair if good else -2.0 * dt_pair
                self.recovery_evidence_s = clip(
                    self.recovery_evidence_s + delta, 0.0, self.EVIDENCE_CAP_S,
                )
        q = self.recovery_evidence_s / self.EVIDENCE_CAP_S
        floor = min(self.c.reacquire_dwell_s, self.MIN_DWELL_S)
        return self.c.reacquire_dwell_s - (self.c.reacquire_dwell_s - floor) * q

    def _reacquire_limit(self, pair_dt):
        q = self.recovery_evidence_s / self.EVIDENCE_CAP_S
        return super()._reacquire_limit(pair_dt) * (1.0 + self.EXTRA_STEP_FACTOR * q)

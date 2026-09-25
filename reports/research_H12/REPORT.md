# H12 slow common-mode residual-slew guard — rejected before validation

Base: champion v8 `e3b0c9c039d2953fbfcda51231263d38ef9f1024`.

## Result

**Rejected at mechanism/unit stage. Validation was not opened for model
selection and the candidate must not be merged.**

The preregistered idea watched only mutually agreeing wheel pairs that had
already failed the model innovation gate. A slow common-mode ramp can be
assimilated by ordinary fusion while its instantaneous innovation is still
inside the gate. The observer therefore follows the biased wheels gradually and
the proposed rejected-pair residual-slew detector never receives the evidence it
needs.

The intended synthetic ramp test failed with
`reacquire_blocked_until == -inf`: the quarantine was never armed. That is a
mechanism failure, not a tuning failure, so the fixed thresholds were **not**
retuned after seeing the result.

## What remains valid

- The plan was committed before implementation:
  `research/H12_SLOW_COMMON_MODE_PLAN.md`.
- The implementation is opt-in; champion v8 main is unchanged.
- Long-dropout recovery and disabled-behavior tests passed in the same run.
- Research-integrity/ROS/offline jobs were not used to claim accuracy for this
  rejected candidate.
- No merge/auto-merge is allowed from this branch.

## Why the next hypothesis changes layer

A detector for slow common-mode drift has to observe **accepted innovations /
model disagreement over time**, not only rejected pairs. The next round will
therefore test a bounded cumulative same-sign innovation budget under stable
controller input, while leaving ordinary isolated innovations untouched.

This is a negative research result and should stay outside main.

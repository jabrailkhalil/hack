# H11 / v8: quarantine after simultaneous wheel jumps

Status: preregistered before implementation or measurement.

Base main: `65bba39ed05c781f3f69a65c02f69931152cbfd9` (champion v7 + low-speed zero-lock guard).

## Problem

The current reacquisition path deliberately accepts a persistent pair of mutually
agreeing wheels after model divergence. H06 showed why simply shortening that
dwell is unsafe: a short common-mode false-speed episode can look like a valid
pair and pull the estimate away from the model.

## Single candidate

Track the timestamp of a fresh `RATE_ANOMALY` independently for front/rear. If
both channels produce a rate anomaly within the existing pair-skew window, mark
a **common-mode jump quarantine** for 1.5 s of source time.

During quarantine:
- ordinary valid model-consistent wheel fusion remains unchanged;
- single-wheel fallback remains unchanged;
- stop/zero-lock logic remains unchanged;
- only the **common-mode REACQUIRING path** is blocked;
- no GNSS/IMU/future sample is used;
- state remains O(1).

Rationale: an abrupt physically implausible jump in both wheels is direct evidence
from the allowed inputs that the pair should not immediately become the new
anchor. A genuine return after a long dropout does not trigger the existing
rate-anomaly check because the previous sample is older than max_age_s, so this
mechanism should not delay that recovery.

Fixed parameter before measurement: `common_mode_quarantine_s = 1.5`.
No parameter sweep is allowed in this round.

## Evaluation

1. Exact regression on clean validation and the established original fault suite:
   candidate must preserve schedule/coverage/causality and must not regress clean,
   fault-event, distance, false-stop or unrecovered aggregates by more than
   numerical tolerance (target: exact equality because the new path should be
   inactive there).
2. Dedicated deterministic common-mode suite, selected from vehicle data without
   GNSS/error search: inject the same +5 m/s offset into both wheel channels for
   0.7 s and 1.2 s at a moving anchor. Reference is used only after inference.
3. Synthetic mechanism tests:
   - abrupt +5 m/s common-mode false episode must not enter REACQUIRING;
   - genuine post-dropout wheel return must still reacquire on the original
     timing;
   - persistent non-abrupt model drift retains baseline reacquisition;
   - zero-lock protection and true stop remain unchanged.

## Acceptance

Promote only if all are true:
- zero new causal errors/resets/coverage loss;
- clean and original-fault aggregate regression <= 0.1%;
- no extra false stops or unrecovered original faults;
- dedicated common-mode event RMSE improves >= 20% and erroneous REACQUIRING
  events decrease;
- genuine recovery synthetic timing worsens by <= 0.1 s;
- full unit/research ROS/offline 2 CPU / 500 MB checks pass.

This is reused validation plus injected diagnostics, not an independent final
test. Historical v4/v5/v7 evidence must remain unchanged. Failed outcomes are
kept and are not merged.

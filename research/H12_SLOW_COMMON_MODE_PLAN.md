# H12 / v9: slow common-mode residual-slew guard

Status: preregistered before implementation or measurement.

Base main: `e3b0c9c039d2953fbfcda51231263d38ef9f1024` (champion v8).

## Problem

Champion v8 protects reacquisition after an abrupt simultaneous RATE_ANOMALY.
A slower common-mode wheel bias can stay below the raw wheel rate gate, remain
mutually consistent, and later look like a plausible new anchor.

## Single fixed candidate

Track only **pairs already rejected by the model gate** and mutually agreeing.
For consecutive rejected pairs:

- pair speed z = mean(front,rear);
- model residual r = z - predicted;
- residual slew = |r[k]-r[k-1]| / dt_pair;
- controller must be fresh and stable: |u[k]-u[k-1]| <= 0.05;
- dt_pair must be in [0.05, 0.25] s.

If residual slew exceeds **1.25 m/s² on two consecutive rejected pairs** while
|residual| >= 0.8 m/s, block only common-mode REACQUIRING for **1.5 s** source
time. One suspicious pair only arms the detector; it does not block.

Fixed parameters before measurement:
- common_mode_slew_threshold_mps2 = 1.25
- common_mode_slew_required_pairs = 2
- common_mode_slew_quarantine_s = 1.5
- stable_command_delta = 0.05
- minimum residual = innovation_floor_mps (existing 0.8)

No grid search / post-validation retuning in this round.

## Invariants

- no GNSS/IMU/future input inside runtime;
- ordinary model-consistent fusion unchanged;
- single-wheel fallback unchanged;
- v8 abrupt-jump quarantine unchanged;
- low-speed zero-lock protection unchanged;
- long-dropout recovery with no recent rejected-pair history unchanged;
- O(1) additional state;
- disabled parameters reproduce champion v8 exactly.

## Evaluation

A. Existing clean validation + existing original fault suite:
- schedule, matching masks, coverage and causality identical;
- clean/fault/distance aggregate regression <=0.1%;
- no extra false stops or unrecovered cases.

B. Existing H11 abrupt common-mode suite:
- no worse than v8 by >0.1%.

C. New deterministic slow-ramp common-mode suite:
- anchors chosen from vehicle data only, before reference scoring;
- both wheels receive a ramp 0→+5 m/s over 3.0 s, then +5 m/s for 1.0 s;
- also a gentler ramp 0→+4 m/s over 4.0 s, then +4 m/s for 1.0 s;
- event + recovery window is scored against GNSS only after inference.

Acceptance:
- >=20% group-macro event-RMSE improvement on the new slow-ramp suite;
- erroneous REACQUIRING ticks decrease;
- no increase in false stops/unrecovered;
- genuine long-dropout recovery synthetic timing regression <=0.1 s;
- all unit/research/ROS/offline 2 CPU / 500 MB tests pass.

This is reused validation plus injected diagnostics, not an independent final
test or official score. Failed results remain in Git and are not merged.

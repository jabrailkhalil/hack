# H13 / v10: neutral-command common acceleration guard

Status: preregistered before implementation or measurement.

Base main: `e3b0c9c039d2953fbfcda51231263d38ef9f1024` (champion v8).

## Motivation

H12 failed before validation because a slow common-mode wheel bias can remain
inside the instantaneous innovation gate and be assimilated by ordinary fusion.
The next candidate must therefore inspect fresh agreeing wheel-pair dynamics
**before** normal fusion, not only rejected pairs.

## Single candidate

Maintain the previous fresh agreeing pair mean `z_pair` and its timestamp.
Before wheel fusion, mark a pair suspicious only when all conditions hold:

- both current wheel samples are fresh and mutually agreeing;
- controller is fresh and near neutral: `|u| <= 0.05`;
- controller changed by <=0.05 since the previous agreeing pair;
- pair dt is 0.05..0.25 s;
- apparent pair acceleration `|dz/dt| > 1.0 m/s²`;
- model acceleration magnitude `|a_model| < 0.50 m/s²`;
- model residual magnitude `|z_pair - predicted| > 0.30 m/s`;
- the acceleration/model mismatch has the same sign for **two consecutive
  fresh pairs**.

On the second consecutive suspicious pair:
- block ordinary two-wheel fusion and common-mode reacquisition for **1.0 s**
  source time;
- do NOT block a healthy single-wheel fallback if only one wheel is accepted;
- do NOT alter low-speed zero-lock logic;
- clear evidence on stale/invalid pair, non-neutral command, reset or after
  model-consistent fusion.

Fixed constants before measurement:
- neutral_u_max=0.05
- stable_command_delta=0.05
- wheel_accel_threshold=1.0 m/s²
- model_accel_max=0.5 m/s²
- residual_min=0.30 m/s
- consecutive_pairs=2
- quarantine=1.0 s

No parameter sweep in this round.

## Required checks

1. Existing clean validation + original fault suite:
   - aggregate clean/fault/distance regression <=0.1%;
   - zero coverage loss, causal errors, new false stops or unrecovered faults.
2. H11 abrupt common-mode suite:
   - no regression >0.1% vs champion v8.
3. Slow common-mode suite:
   - both wheels ramp 0→+5 m/s over 3 s then hold 1 s;
   - both wheels ramp 0→+4 m/s over 4 s then hold 1 s;
   - anchors require near-neutral stable controller and vehicle speed >2 m/s,
     selected using vehicle data only before GNSS scoring.
4. Acceptance on slow suite:
   - event group-macro RMSE improvement >=20%;
   - erroneous REACQUIRING and FUSED exposure during injected ramp decrease;
   - no added false stops/unrecovered.
5. Genuine neutral downhill/coasting behavior is not assumed safe a priori:
   clean validation is the guard against this false-positive risk.
6. Full unit/research/ROS/offline 2 CPU / 500 MB tests must pass before any
   promotion.

This uses reused validation and injected faults, not an independent final test.
Failure stays on the research branch and is never merged.

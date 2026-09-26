# R3-H28: prospective protocol

Round R3-v8-fixed. Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024. Canonical GuardedReadoutObserver, full champion_v8.yaml, published Estimate.v/s, 20 Hz, delay 0, readout gain 1/holdoff .5, common_mode_quarantine 1.5. No moving-main changes.

## Foundation before an intervention patch

Read PR27 at 097fcfa09afdd435fd86ff1aa9b3535e709dcbd5 (NOT R2-H13), and R2-H21 REPORT at 0c6c4c85bcbb4235ae7601ebdcbf6f0895da7096. PR27 local innovation failed to expose accumulating drift; H21 interval computation did not imply veto coverage.

A passive 2-second shadow probe was run on the lexicographically first train bag of EACH of the 27 original train groups, whole duration. This is foundation measurement, not candidate accuracy selection. There were 8,341 clean eligible pairs; 46 deterministic injected +/-0.6 m/s^2 drift scenarios. In 18 original groups, 452 pairs had age-padded shadow discrepancy >.30 m/s while absolute local innovation <=.30 m/s. No development/validation was used for this probe. The .30 diagnostic is the historical PR27 residual threshold, not a tuned H28 alarm threshold. Complete probe/source hashes will be retained.

The mechanism therefore warrants a detectability check. It does NOT establish faulty-wheel attribution. For v'=f(v,u)+d and y=v+b, changing v to v+k, b to b-k and d to d+k'+f(v,u)-f(v+k,u) leaves the observed histories identical. Need explicit load/grade/resistance counterexamples before any veto. Wolfram returned zero for the observation and dynamics identities; limit computations generated warnings which will be preserved and independently checked locally.

## Fixed mechanism and budget

Exactly two horizons: 1.0 and 2.0 s. At most FOUR scalar shadow states per variant, anchors spaced by H/4. Each freezes its accepted past inner velocity, drive acceleration and d. It uses the unchanged causal drive/resistance equations, but never assimilates later tested wheels or relearns d from them. Expire after H; clear on stale/invalid or changed command. Scope is unchanged neutral command |u|<=deadband; anchor after >=.5 s neutral with an agreeing accepted pair and |v|>1.0 m/s. Oldest shadow aged H/2..H supplies the residual; never select by error magnitude or reference.

Compare two fresh, distinct, mutually consistent held samples against current shadow, with per-channel max_accel*age padding. Score = max(0,min(|front-shadow|-A*age_front,|rear-shadow|-A*age_rear)), only when both residuals have the same sign. Two new agreeing exceedances no farther apart than max_age confirm model disagreement. No reuse of held samples as new confirmations. No future inputs, no oracle arguments. Source-state predictions and the four-shadow bound are tested.

A model-disagreement alarm is NOT a sensor fault. The bounded supervisor rule for this study is mandatory canonical fallback under attribution ambiguity: diagnostic AMBIGUOUS_MODEL_OR_WHEELS, no wheel veto, no d freeze, no replacement by shadow speed, no change to published v/s. We do not invent a stronger nuisance bound to authorize rejection. The goal of this foundation-stage candidate is to determine whether an accuracy-changing supervisor can be justified. If the required distinguishability is absent, report INCONCLUSIVE and do NOT pretend that unchanged trajectories constitute an accuracy improvement. A later intervention rule would be a separate authorized hypothesis, not an extra hidden variant here.

## Train-only calibration, fixed before development

Load ALL 64 train bags, vehicle-only, original split. Sort original group IDs; groups with index modulo 5 == 0 are held out as train-check; others are fitting groups. Original clean, accepted pairs with spread<.15 m/s supply wheel-pseudo-labelled healthy forecast scores. Keep full grouping; each fitting group has total weight 1. For each H, threshold=max(3*baseline wheel_sigma, group-balanced weighted empirical .995 quantile of score). The weighted quantile is the first sorted value reaching cumulative .995. No upper clipping, no optimization, no refitting on train-check/development. Record missing groups and empirical exceedances; do not call pseudo-labels truth. Publish calibration JSON/hash before ANY development comparison.

## Development and separate suites

Use all 17 original development bags/all 7 groups. Reuse unchanged evaluate.score/replay/match/metrics/distance, original fault_windows and group aggregation through separate factory. Direct canonical, driver baseline, enabled diagnostic shadow and feature-off must have equal schedules, masks, counters and outputs. Prove inner-state identity each tick on edge cases. Both receivers retained; missing references never become zero errors.

Original bias5/dropout5/dropout10/lock3 suites are separate from (a) existing low-speed lock suite and (b) exact H11 common +5 m/s .7/1.2 s suite. Additional slow drift at first vehicle-selected stable-neutral anchor: +/-0.2 and +/-0.6 m/s^2 ramp for 4 s, hold 2 s, then restoration; use same injected events for all methods. Anchors use only causal vehicle history, not candidate/GNSS error. A changed later command produces canonical fallback, not post-hoc exclusion. Record clean/original/diagnostic cohorts separately.

Counterexamples: identical-input twins with honest common velocity change versus common wheel bias, slopes +/-0.2 and +/-0.5 m/s^2 (within configured d range for the ideal coast example), and +/-1.5 as a wider physical stress case; positive/negative load steps, coasting resistance changes, and true stop. Numeric model force compensation provides an exact unobserved load explanation. On real clean development, report alarms where both references support wheels within .25 m/s as a healthy-wheel proxy (not certified load labels). No new sensor-fault attributions, false wheel vetoes, false stops or individual unrecovered cases are permitted on these counterexamples.

## Prospective decision and validation economy

Detector coverage: >=20 confirmed alarm pairs across >=2 original groups on slow-drift diagnostics. Useful supervisor coverage: >=20 justified wheel-veto ticks across >=2 groups, without a healthy-input twin veto. Count forecasts, alarms, attributions and actual interventions separately. No distinguishability or insufficient intervention coverage => INCONCLUSIVE. Do not lower thresholds after seeing results.

Validation admission requires ALL R3 conditions: sufficient useful mechanism coverage; >=2% clean macro gain OR >=5% original fault-event macro gain; clean/fault/pooled regression <=.5%; scalar distance <=1%; per-bag/receiver clean <=base+max(.005 m/s,5% baseline); equal coverage/masks/schedule; no new false stops, individual unrecovered, causality/reset errors. Existing low-speed and abrupt-common event macro <=.5% regression and no new false stops/unrecovered. New-suite gains do not replace original gains. If development fails, validation/final-test remain closed; no validation freeze is fabricated.

## Execution, evidence and cost

Dependency-free runtime module only. Existing core/readout/Timeline/guards/profile unchanged; no new runtime dependencies. Unit/build/integrity, exact-off, prefix/future/stale/duplicate/reset, fixed memory and independent symbolic/numeric checks required. Benchmark step and full replay with equal collectors after 10 s warmup; AB/BA repeated three times on the first development bag, fixed threads. Compare also an isolated scalar innovation-only diagnostic cost. RSS of research process is not node RSS. No wall-clock latency claims from offline schedule.

No installed enabled ROS latency benchmark is needed after an INCONCLUSIVE/failed accuracy admission; mark NOT_RUN_AFTER_NON_ADMISSION, not environment failure or a passing runtime certificate. Record all actually executed stages, commands and source hashes. Git gets compact PLAN/calibration/report/metrics/provenance; compressed traces remain artifacts, no raw bags in Git. One draft PR only. No merge/auto-merge, no changes to any other branch. Known Consensus/Scite monthly quota stops will not be retried; saved and public primary-source material may support motivation, not claimed accuracy.

# R5-H46 — preregistration / blocked before fitting

## Identity and current stage

Baseline `b2783206000091ab11a1c11ac3ff79082188a4fb`, complete tree `973d50d288e050325ee1c71a90fa8d81f2a099af`.
Canonical GuardedReadoutObserver, champion_v8.yaml, returned Estimate.v/s, 20 Hz, delay 0.
Scope is only H46. Do not reuse H36 parameters or the outcomes of other wave-2 candidates.
The launch package and full source snapshot have been verified. The original dataset is available.
H42/H43 Library records have been located, but the Files materialization attempt reports no authorized raw-byte path for both. GitHub contains publication receipts, explicitly not the component payloads. No fit is authorized before native verification and the fold bridge. Do not rebuild the producers to fill this gap.

## Hypothesis and interpretation

One compromised global F/P/B calibration may mix the dynamics of labels 30618 and 30639. Compare one regularized pair of label-level F/P/B vectors with one matched global-only control. This is a prospective hypothesis, not an observed improvement.
Labels are metadata, not a confirmed mapping to physical vehicle IDs or known passenger mass. Configuration is explicit; no runtime bag-name, future trajectory or GNSS-based selection. Unknown/missing/disabled profile returns exact canonical v8. Known profile without a complete fitted artifact fails visibly rather than silently inventing parameters. Evaluation is CONDITIONAL_ON_CONFIG until an operational mapping is confirmed. Wrong known profile is a required counterexample, not automatically detectable by this task.

## Bounded model and budget (fixed before measurements)

Only effective F=efficiency*gear*torque/(radius*mass), P=power/mass, B=brake_force/mass change. Bounds: F in [0.05,5], P in [1,100], B in [0.05,5], inherited from the original physical identification. Rolling, drag, actuator tau, exponent, wheel scaling, d adaptation, readout, low-speed and common-mode guards remain identical.
One joint global/per-label fit, one non-selectable matched global-only control, one start each at v8; max_nfev=80 each, <=1000 total real residual invocations including Jacobian evaluations; no restarts. Fixed shrinkage lambda=0.1. Normalize parameter deviations by the baseline effective F/P/B. The joint criterion has data residuals under each label vector plus lambda times the sum of the squared normalized deviations from a shared vector. The shared vector can be eliminated analytically as the arithmetic mean of the two label vectors, reducing 9 variables to 6 without a new hypothesis. The global-only control has 3 variables and exactly the same data windows/weights/teacher.
Robust data loss: soft_l1 of dimensionless speed residuals with fixed speed scale 0.2 m/s. Shrinkage remains quadratic; do not robustify the prior by accident. Per-label equal weights, then equal source-group weights within label, then equal windows within group, then equal available horizons within window. Wire-duplicate bags are represented once; both receivers are not independent groups.

## Dependencies, roles and windows

Teacher/atlas pins, their producer-native folds and exact native-verifier commands are those in WAVE2_ADDENDUM.md. Run both native payload verifiers and the fold bridge before creating a new DEPENDENCIES.lock.json. Expected pins, receipts and coordinator bridge files are not the lock. Teacher magnitude and noncausal quality are offline target information only. Atlas is a development diagnostic, not fitting or threshold-selection data.
Use the original R5 folds: fit 17/3 groups and check 5/2 groups by the two labels. Do not transfer missing-reference groups between folds. For future fitting use vehicle-derived anchor times 10,30,50,... s, excluding anchors without 5 s valid command/wheel warmup, |mean wheel speed|>0.5, pair disagreement<=0.15 m/s. Max 32 anchors per bag selected by fixed SHA256('R5-H46:'+bag+':'+anchor) order, not reference quality or error. At each selected anchor use horizons 0.5,2,5 s; pair each target using the frozen teacher policy and nearest accepted time within 0.05 s. Apply the same resulting target intersection to joint/global control. Matching here defines training targets only, never the canonical scorer.
Every theta obtains its own causal 5 s observer warmup. During the open-loop horizon the predictor sees only commands and its own v,drive,d. Future teacher magnitudes are loss targets only; no target-derived d, initialization, direction, gate or intervention time. Compare predicted speed magnitude with the magnitude teacher, preserving causal signed state internally. Train GNSS decoding is unnecessary when the verified teacher arrays are available; never regenerate them locally.

## Foundation and check

Before optimization require at least 2 fitting and 2 check source groups per label with usable targets, at least 30 fitting and 10 check windows per label, and data-only F/P/B Jacobian rank 3 for each label, with smallest/largest singular value >=1e-4 after baseline-parameter scaling. Ridge is not evidence of rank. Failure means INCONCLUSIVE without parameters fabricated from priors.
Check all held-out groups, traction/coast/braking, startup, horizon errors, signed velocity bias (where defined) and speed-magnitude bias. Mass 27.5 t is contextual Q&A, not a replacement for the fixed parameter gauge. Mandatory diagnostics include true load changes, swapped known profiles and unknown fallback. No extra parameter choice from check/development. Only the joint candidate is selectable; control cannot become a second candidate.

## Contract L unchanged

Development: all 17 bags, original faults, complete faulted bags, pinned low-speed/common-mode suites. At least 3 changed reference-bearing groups and >=2% clean or >=5% original fault gain. Main clean/fault/pooled aggregate regression<=0.5%, clean/full-faulted distance<=1%, per-bag clean<=baseline+max(0.005 m/s,5%). Additionally, for each label every principal aggregate regression<=0.5% (including distance; stricter than overall distance). Equal schedule/masks/coverage; no new false stops, individual unrecovered, causal errors or unexpected resets. Supplemental event regression<=0.5%, no new safety failures. All missing references remain null. Report whole-bag delta_s at recovery+10 s and at end, signed bias, per-label/group/fault metrics and leave-one-group-out sensitivity without changing the primary score.
Wrong-profile measurements are separately marked conditional counterexamples, not used for fitting. They cannot establish automatic identification. Unknown-profile exact fallback is a hard implementation check.
Only after positive development and all prerequisites: publish a distinct frozen candidate/dependency/source/data/evaluator commit before one reused validation. No validation in the current blocked stage. Final/test payloads never decoded. Enabled ROS both clock modes, offline 2 CPU/500000000 bytes, actual parameters/import hashes and measured latency/RSS are required for promotion, not inferred from unit tests.

## Current permitted work and stop

This pass may implement configuration selection, bounded coefficient/regularization helpers and tests, verify all 320 baseline files and 81 allowed DB hashes, and run a baseline-only development reproduction. Those measurements cannot select lambda, windows or parameters. Synthetic parameter fixtures are marked test-only and never exported as fitted candidate models.
No completed training or development-candidate runner is claimed while upstream payloads are unavailable. No candidate coefficient JSON, candidate SHA, validation freeze or improved metric may be invented. Save DEPENDENCY_PENDING / NOT_EVALUATED and exact remaining stage. Default runtime/setup/launch/evaluator remain unchanged. Publish a draft research checkpoint, not a merge-ready change.

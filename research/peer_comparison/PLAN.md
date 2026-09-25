# Comparison with godknows1337/tram-odometry

Status: protocol fixed before numerical comparison. No model changes, no merges.

Pinned versions:
- ours: jabrailkhalil/hack @ e3b0c9c039d2953fbfcda51231263d38ef9f1024, actual canonical champion_v8 JSON + GuardedReadoutObserver;
- peer: godknows1337/tram-odometry @ 0148c0563a781da18b1e25b57bd6e6ba15f45742, WheelEstimator front/rear/mean; ExponentialMeanEstimator is explicitly an optional example, evaluated separately at its published 0.15 s default.

The peer source is private and remains read-only. Only comparison scripts, source blob identifiers, measurements and the report are saved here, not a vendored copy of peer code. Local exact copies are verified against Git blob SHA before execution.

## Questions

1. What is implemented vs only planned? Audit control input use, physical prediction, wheel faults, stale values, time and coordinates.
2. Why are README RMSE and latency numbers not directly comparable? Check bags, reference choice, clocks, masks, aggregation, and latency endpoints.
3. On the same inputs and output grid, which estimator is better for ordinary data, injected faults and scalar distance?

## Fixed evaluation

Use all 19 existing validation bags; do not train, retune or read final-test measurement payloads. Retain both GNSS receivers with nearest source-stamp tolerance 50 ms. Reproduce the current v8 baseline (0.114549861 clean group-macro RMSE) before claiming comparison results.

Primary experiment is an estimator comparison under identical causal scheduling: our existing timestamp alignment produces a common sequence of held raw observations and 20 Hz ticks. Each peer estimator is fed only newly released observations and queried at the same ticks. Unit conversion is identical. Initial predictions unavailable in either implementation are explicitly counted; speed comparisons use common finite masks. Stale peer estimates remain scored, not removed from fault windows. This isolates estimator behavior; it is NOT an end-to-end comparison of the two ROS adapters or an evaluation of the peer's native receipt-clock replay.

Original fault suite: front +5 m/s for 5 s; both-wheel dropout 5 s and 10 s; both-wheel zero lock 3 s. Use the same pre-existing vehicle-data-only anchors and warm-up/recovery windows for every model. Additional abrupt common-mode and slow-ramp suites use their already published definitions and are reported separately, never pooled into an unlabeled score.

Report group-macro and pooled RMSE, MAE/bias, identical-mask coverage, scalar reanchored-span distance (NOT xyz), and per-kind event RMSE. Keep per-bag/receiver regressions. No automatic winner promotion and no main write.

Additional synthetic causal checks may illustrate behavior during neutral/traction commands, missing wheels, locked wheels and stale inputs. Any result on a constructed trace must be labeled synthetic. Peer README/runtime numbers remain author-reported unless reproduced with identical endpoints and environment.
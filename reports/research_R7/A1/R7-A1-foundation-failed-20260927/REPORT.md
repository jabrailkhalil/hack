# R7-A1 — Causal Robust MHE vs canonical v8

## Final status

**ARCHITECTURE_FOUNDATION_FAILED.**

The preregistered moving-horizon architecture was implemented and executed on the frozen train-check replay, but none of the four frozen variants passed admission. No development, validation or final/test data were opened.

This is a completed negative result for the tested implementation. It does **not** establish that all MHE architectures are unsuitable.

## Architecture under test

State:
`[v, a_drive, d]`

Optimization:
- 10 Hz MHE solve grid
- 20 Hz published estimate
- frozen v8 physical coefficients
- no GNSS/IMU/fault labels/group IDs/future samples at runtime
- robust pseudo-Huber wheel residuals
- no hard rejection solely because a wheel disagrees with model velocity

Frozen variants:

| Variant | Horizon | sigma_d | Max variables |
| --- | ---: | ---: | ---: |
| V1 | 3.0 s | 0.01 | 93 |
| V2 | 3.0 s | 0.03 | 93 |
| V3 | 3.0 s | 0.10 | 93 |
| V4 | 1.5 s | 0.03 | 48 |

Solver:
`scipy.optimize.least_squares`, TRF, numerical Jacobian, `max_nfev=20`, no hidden restart.

## Frozen train-check

- 12 wire-representative train-check records
- 7 source groups
- 34 frozen anchors
- 68 dropout events
- both-wheel dropout: 5 s or 10 s
- followed by 10 s of real recovery
- 18 events in 4 groups had full integral reference
- H42 was used only as an unsigned offline scorer proxy

## Aggregate results

| Algorithm | J ↓ | J change | RMS E_v, m/s ↓ | RMS E_s, m ↓ | Clean RMSE, m/s ↓ |
| --- | ---: | ---: | ---: | ---: | ---: |
| v8 / B0 | 1.000000 | — | 1.353786 | 19.693422 | 0.028584 |
| V1 | 0.083857 | +91.614% improvement | 0.501140 | 3.449624 | 0.499421 |
| V2 | 1.678337 | -67.834% | 1.956382 | 22.178539 | 0.529566 |
| V3 | 0.083671 | +91.633% improvement | 0.500984 | 3.433465 | 0.499351 |
| V4 | 0.082469 | +91.753% improvement | 0.493515 | 3.525384 | 0.510562 |

V4 is only the numerical minimum of the aggregate train-check objective, not an admitted candidate.

V1/V3/V4 fail the preregistered gates:
- insufficient number of improving independent groups;
- source-group regression exceeds the 10% limit;
- clean proxy RMSE regression is far above the 1% limit.

V2 also worsens the aggregate objective.

## Concentration of the apparent gain

One source group, `bc1e4cbe924a90ce`, contributes approximately 99.78% of the v8 aggregate J.

For V4:

| Group | v8 J | V4 J | Change |
| --- | ---: | ---: | ---: |
| 6090ff2c1bc8dee6 | 0.003683 | 0.003805 | +3.30% |
| bc1e4cbe924a90ce | 3.991209 | 0.314886 | -92.11% |
| dc785decbed3d7ce | 0.004964 | 0.010672 | +115.00% |
| eeabf7d118bbcdac | 0.000145 | 0.000514 | +255.60% |

If the strongly improved group is descriptively excluded, V4 worsens J by 70.52%.

Therefore the 91.75% aggregate improvement is not a portable cross-group improvement.

## Local positive and negative examples

Strong local improvement:
- record `30639_4285f2bc`
- braking dropout 10 s
- speed error: 3.796 -> 1.323 m/s
- integral error: 55.538 -> 9.228 m

Strong local regression:
- record `30618_22c1c589`
- analogous dropout
- speed error: 0.046 -> 0.444 m/s
- integral error: 0.342 -> 5.480 m

This is direct evidence that the architecture has a materially different error profile, but not a uniformly better one.

## Clean-record solver failure

A critical counterexample appears on clean record `30639_4285f2bc` near t≈761 s.

Observed values:
- front wheel: 7.340859 m/s
- rear wheel: 7.385436 m/s
- H42 proxy: 7.380336 m/s
- v8: 7.329204 m/s
- MHE V4: 0.000000563 m/s

The wheel pair is mutually consistent and passes raw checks.

On the 750–780 s diagnostic interval, 219 of 300 MHE solves are unsuccessful. The solver reaches `nfev=20`, returns status 0, and the preregistered causal model fallback is used. The estimator therefore remains near the previous almost-zero state despite valid wheel measurements.

This means that allowing measurements into the robust objective is not sufficient: the optimization must also produce an accepted solution quickly enough.

The experiment did not isolate whether the dominant cause is local nonsmoothness, initialization, constraints, weights or the solve budget.

## Solver telemetry

Total MHE solves: 578,552, 144,638 per variant.

| Variant | p50 ms | p95 ms | p99 ms | Fallback |
| --- | ---: | ---: | ---: | ---: |
| V1 | 5.588 | 24.072 | 45.213 | 5.194% |
| V2 | 5.495 | 23.808 | 44.877 | 5.272% |
| V3 | 5.470 | 23.450 | 44.731 | 5.236% |
| V4 | 2.762 | 10.916 | 19.072 | 5.362% |

Maximum individual V4 solve time: 508.5 ms.
Continuous unsuccessful-solve streaks reached 21–23 s.

These are offline solver timings, not ROS real-time certification.

## Verification

Before measurement:
- 161 canonical tests PASS
- 43 research-integrity tests PASS
- 36 MHE/runner tests PASS

Independent result audit reported:
- 60 job receipts checked
- 520 result hashes checked
- 400 traces checked
- all 578,552 solve records checked
- max recomputed E_s difference: 7.11e-15 m
- max J difference: 1.39e-17
- no coverage loss
- no new continuous missing/invalid-output episode

Formal development unrecovered/low-speed/common-mode suites and Contract L were not evaluated because no variant was admitted.

## Versions

- baseline: `b2783206000091ab11a1c11ac3ff79082188a4fb`
- preregistration: `7f1e1ad6b38198ea046af74eb77c5299e8636e0f`
- executed MHE implementation: `4db82cbcc41c0859c86742dbc74eb78d754d26ed`
- branch: `research/R7-A1`
- permanent claim: `claims/R7-A1`

The canonical runtime was not changed or promoted.

## Scientific conclusion

Keep canonical v8.

Do not promote V1–V4.

The tested MHE family shows genuine local fault-case gains, so the architecture is not scientifically empty. However, the fixed implementation is dominated by severe clean-record regression and prolonged solver fallback episodes.

The most informative next MHE experiment, if continued, should isolate **solver/fallback robustness on the clean counterexample** before any new development comparison or wider parameter sweep.

## Publication repair note

This report was published by the coordinator from the final agent result after the original execution environment lacked Drive/GitHub write actions.

The original full evidence ZIP and compact ZIP bytes were not present in the coordinator runtime and therefore were **not reconstructed or re-uploaded**. This publication does not claim byte-level re-verification of those unavailable archives. It records the completed numerical result, exact executed implementation commit, and final scientific status without fabricating missing evidence.

# R6-H61 — train-only optimization audit

**TRAIN_OBJECTIVE_OPTIMIZABLE_BUT_NOT_TRANSFERABLE**. This is an optimization audit, not an accuracy candidate.
No H54 check/development outcomes or other forbidden evidence were used.

## Ownership, provenance and exact computation

Existing claims/R6-H61 and research/R6-H61 refs were verified at canonical
b2783206000091ab11a1c11ac3ff79082188a4fb before execution; receipt owner
LOCAL_AGENT_H61. Claim ref is retained. Canonical tree
973d50d288e050325ee1c71a90fa8d81f2a099af, all 320 files/modes verified.
Full champion_v8 YAML and runtime unchanged. PLAN d77b7ea precedes all physical
evaluations; code 63b86d8. Exact allowed H54 sources/contract/lock and H44
window hashes verified; H42 archive hash bound and verified. DEPENDENCIES.lock
records Drive IDs and hashes. No canonical dataset or atlas is opened.

141 original H44 fit windows, 15 source groups. The archived container includes
both roles; only fold=fit rows are exposed to the predictor/objective, as in H54.
No check predictions/metrics or measurement DB are opened. Exact H44 Predictor,
own-config 101-tick local warmup and 100-tick command-only forecast, H42 unsigned
proxy targets, horizons/scales and H54 six()/Objective are reused unchanged.
Offline group IDs/targets are never observer inputs. H54 import path bindings
point at canonical source; no upstream prepare()/fit()/confirm() entrypoint runs.

Rg=Lg/max(Lg0,eps) with the frozen H54 denominators. Lg retains equal-bag and
equal-window weights within each group. For each selected subset S:
J1=.5 mean(Rg)+.5 mean(top ceil(|S|/2) Rg)+.01 mean(log(theta/theta0)^2).
Stable lexicographic ordering resolves ties. No smoothing or new regularizer.
All saved objectives were independently recomputed from losses; max delta
8.88e-16. Each call stores predictions/residuals/losses and fingerprints.

## A — reproduction

Baseline J1: **1.0000000000000000**; frozen C0 witness:
**0.9919358040775982**. Both repeat calls are byte-identical in prediction,
six-residual, group loss and full residual fingerprints. Gate A PASS.

## B — fixed line scan

Exactly 21 alpha=i/20 points between baseline and C0 in log-space, with passive
branch/clipping counters in LINE_SCAN.csv and per-window evidence. Both endpoint
fingerprints equal the uninstrumented reproduction calls. Minimum on this
diagnostic line: alpha=0.65, J1=0.9863360315797670.
This point is not a selected start or optimizer result. Every Powell starts at zero.

## C — single full-fit Powell

method=Powell; x=log(theta/theta0); bounds from H54 [.05,1,.05]..[5,100,5];
x0=zeros(3), xtol=1e-6, ftol=1e-8, maxfev=130. No restarts or alternative solver.
Returned J1: **0.9842489831862532**; gain **1.575102%**.
Returned theta: [1.2066694112813927, 8.658625800083431, 1.1911636080264076]. Evaluations 130;
solver success=False; termination: Maximum number of function evaluations has been exceeded..
The returned point is retained even if another evaluated point is better.
Gate B (True): J1<=.9920 AND J1<=J1(C0)+1e-4.
Two final physical repeats exactly verify the returned point. A budget exit is
reported as such; neither a global optimum nor numerical convergence is claimed.

## D — five-fold group transfer within train-fit

Groups sorted lexicographically; fold=index mod5, frozen before optimization.
Each optimizer receives only 12 training groups and the same fixed settings.
All five returned points are frozen before any held-out score is evaluated.
Held-out triples use data-only H with their actual recomputed baseline; no prior.

| Fold | Baseline H | Returned H | Gain | Powell calls | Solver success |
|---|---:|---:|---:|---:|---|
| 0 | 1.000000000000 | 1.040362735984 | -4.036274% | 130 | False |
| 1 | 1.000000000000 | 0.990373051480 | +0.962695% | 130 | False |
| 2 | 1.000000000000 | 1.020827431657 | -2.082743% | 130 | False |
| 3 | 1.000000000000 | 0.990635989040 | +0.936401% | 130 | False |
| 4 | 1.000000000000 | 1.099280054997 | -9.928005% | 130 | False |

Improved: **2/5**; median gain
**-2.082743%**; worst regression
**9.928005%**. Gate C=False.
These folds are inside train-fit; they are not the historical train-check split.
They also are not untouched external evidence: H54's fixed normalizers and prior
protocol already exist. The result measures transfer of this fixed procedure,
not unbiased official accuracy. No fold was selected or removed.

## Parameter stability — descriptive only

| Parameter | Minimum across fold fits | Maximum across fold fits |
|---|---:|---:|
| F/m | 1.188434266 | 1.23676336 |
| P/m | 8.391538847 | 12.8161586 |
| B/m | 1.139380991 | 1.238670668 |

Maximum pairwise log-parameter distance: 0.42349276.
Full pairwise distances, fold standard deviations and distance to each bound
are saved. Active worst-half groups are retained in every call and final repeat.
ACTIVE_SET_STABILITY.json records consecutive membership changes and group
inclusion counts by context; these are diagnostic counts, not frequency estimates.
None of these diagnostics changes starts, solver, gates or reported fits.

## Integrity, budget and conclusion

Gate D PASS: finite outputs, bounds, repeat fingerprints, exact windows and
subset coverage, independent objective arithmetic and frozen dependencies.
214 tests PASS (161 canonical, 43 research-integrity, 10 H61). Call ledger and
saved evidence match: **832 physical aggregate evaluations**,
hard cap 900; no cached evaluations hidden from accounting. Physical objective
wall time 903.70 s. One process, native Apple Silicon,
Python 3.12.14, NumPy 2.3.5; thread limits one.
Only Stage B uses detailed passive tracing. No unused-budget exploration.

Gates: {'A': True, 'B': True, 'C': False, 'D': True}. Final status: **TRAIN_OBJECTIVE_OPTIMIZABLE_BUT_NOT_TRANSFERABLE**.
H54 historical verdict remains unchanged. This audit says only whether this
one registered solver recovers known train descent and whether its direction
transfers across fit groups. It never establishes accuracy or a runtime fix.
No candidate.patch, accuracy candidate, check/development/validation/final run.
Any future accuracy stage requires a separate preregistration and still-unopened
evidence; H61 does not authorize reopening H54 check/development.

The compact ZIP includes all call metrics/fingerprints, contracts, code, logs,
line-scan arrays and reproduction/final/held-out repeat arrays. Intermediate
Powell prediction arrays remain locally in evidence/call_*.npz; their hashes
are listed in LOCAL_ONLY_INTERMEDIATE_ARRAYS.json inside the ZIP. The compact
export is not a complete copy of all intermediate arrays.

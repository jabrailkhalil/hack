R6-H61 — Train-only optimization audit of the frozen H54 robust objective


Role
You are the designated local research agent for R6-H61.
This is an optimization audit, not an accuracy candidate search.


Ownership
The execution is already atomically reserved:
claim ref: claims/R6-H61
research branch: research/R6-H61
owner token: LOCAL_AGENT_H61
baseline: b2783206000091ab11a1c11ac3ff79082188a4fb


Do not create a second claim or second execution. Verify the existing claim and receipt before any expensive work.


Workspace
Google Drive folder:
https://drive.google.com/drive/folders/19S0NiATO_hsIIdu2wkFqdgkeE1wY7yWW


Main question
H54 returned its robust C1 at canonical v8 with J1=1.0, yet a frozen train-only feasible point already exists with lower robust objective:
J1(C0) = 0.9919358040775982.


Therefore H54 did not establish that the group-robust objective is useless; it established that the registered local optimizer did not reliably minimize it.


H61 asks only:
Can the exact frozen H54 robust train objective J1 be optimized below baseline reproducibly, and does the resulting train-only direction transfer across held-out source groups inside train-fit?


H61 must NOT use H54 check or development outcomes for optimization, solver selection, thresholds, stopping, candidate selection or interpretation.


Frozen baseline
commit:
b2783206000091ab11a1c11ac3ff79082188a4fb


tree:
973d50d288e050325ee1c71a90fa8d81f2a099af


Observer/profile:
GuardedReadoutObserver
champion_v8.yaml


Frozen H54 train artifacts
H54 workspace:
https://drive.google.com/drive/folders/1087tRHb09j71ZIrIjQ5G4aNLTd9z3TGg


Allowed H54 artifacts:
R6-H54_PLAN.md — Drive ID 1n2gwI79rOcLXu3kVoIBIeaDW0hfR_DBu
DEPENDENCIES.lock — Drive ID 1Pa4lKV5NHtFgZUQbM-JodPmzkCT_da27
OBJECTIVE_CONTRACT.json — Drive ID 1TU1vTVhcWIXrb29AcPIrPvam6EwQ2Db4
GROUP_LOSS_BASELINE.csv — Drive ID 1hfwEOxX-Y6hGScn3T7rT95Bt26Uzg38H
CONTROL_FIT.json — Drive ID 1NdLDef1JU74Xku_VHTdb4DFdU5MjyuP9
study.py — Drive ID 1gGoTkXNJqgTIHPYSlaH9DZP1RzWUoYDi


Do not open H54 CHECK_RESULTS.csv, DEVELOPMENT.csv, PER_GROUP development output, H54 check predictions, or validation/final data during H61.


Allowed prior facts
You may use these already frozen train-only facts:
- 141 H44 fit windows.
- 15 fit source groups.
- theta0 = canonical v8.
- H54 robust full-train objective J1(theta0)=1.0.
- H54 frozen C0 is a feasible witness with J1=0.9919358040775982.
- H56 found the underlying H44 objective deterministic, full-rank and moderately conditioned, with local nonsmoothness explained by real branch/clipping changes.
These facts may define the audit but must not be used to introduce extra candidate families.


Exact H54 objective
Reuse the exact H54 OBJECTIVE_CONTRACT.


For each source group g:
Lg(theta) = frozen group-balanced H44 data loss.
Rg(theta) = Lg(theta) / max(Lg0, eps).


For a set of groups S:
J1_S(theta) =
0.5 * mean_g_in_S(Rg)
+ 0.5 * mean(top ceil(|S|/2) Rg)
+ 0.01 * mean(log(theta/theta0)^2).


Keep:
F/m, P/m, B/m only.
Same absolute parameter bounds as H54.
Same H44 windows, teacher, warmup, residuals, group/bag/window weighting and prior.
No runtime changes.


Strict firewall
Do NOT:
- open H54 check/development results;
- open validation or final/test;
- use H43 development error atlas;
- use H53/H57 candidate metrics;
- use B01/A0/A1/A2 witnesses;
- change the robust objective;
- smooth the top-half term;
- tune thresholds after results;
- add per-group or per-vehicle runtime parameters;
- create an accuracy candidate or candidate.patch.


Preflight
Before scientific calls:
1. Verify claim ref and research branch.
2. Verify canonical source/tree.
3. Verify H54 PLAN, dependency lock, objective contract and allowed source hashes.
4. Verify exact H44 fit windows referenced by H54.
5. Create a new immutable H61 DEPENDENCIES.lock that references H54 artifacts by ID/hash.
6. Create and commit R6-H61_PLAN.md before objective evaluations.


Stage A — objective reproduction
Using only train-fit:
- reproduce J1(theta0)=1.0 within 1e-12;
- reproduce J1(C0)=0.9919358040775982 within 1e-9;
- repeat identical theta evaluations and require byte-identical residual/group-loss fingerprints when the environment is identical.


If reproduction fails:
INVALID_OBJECTIVE_REPRODUCTION
Stop. No optimizer audit.


Stage B — frozen landscape probe
Before optimization, evaluate exactly 21 equally spaced points in log-parameter space on the line:
theta(alpha) = exp((1-alpha)*log(theta0) + alpha*log(theta_C0))
for alpha = 0, 0.05, ..., 1.


Record:
alpha
J1
mean(Rg)
worst-half mean
prior
active top-half groups
branch/clipping counters if available.


This is diagnostic only. Do not select a new start from the line scan.


Stage C — one preregistered derivative-free optimizer
Use exactly one solver family:


scipy.optimize.minimize
method = Powell
x = log(theta/theta0)
x0 = [0,0,0]
bounded by the same absolute theta bounds as H54
xtol = 1e-6
ftol = 1e-8
maxfev = 130


No restarts.
No alternative solver.
No starting from C0.
No changing tolerances after seeing results.


Run one optimization on all 15 fit groups.


Count every physical objective evaluation.


Stage D — deterministic five-fold source-group transfer
Before any fold optimization:
- sort the 15 source-group IDs lexicographically;
- assign fold = index mod 5;
- freeze FOLDS.json.


For each of 5 folds:
- train on the other 12 groups using the same J1 formula restricted to training groups;
- start at theta0 only;
- use the exact same Powell settings;
- maxfev=130;
- freeze the returned theta before evaluating held-out groups.


Held-out score is data-only:
H_holdout(theta) =
0.5 * mean(Rg)
+ 0.5 * mean(top ceil(H/2) Rg)
over held-out groups.
No prior in held-out transfer score.
Baseline held-out score is exactly 1.0 by construction only if the group normalization arithmetic confirms it; report the actual recomputed value and do not force it.


No fold may see another fold's held-out results before its optimizer configuration is already frozen.


Hard compute budget
Maximum 900 aggregate physical objective evaluations for all H61 work.
This includes:
- reproduction calls;
- 21-point line scan;
- one full optimization;
- five fold optimizations;
- exact final-point repeat checks.


Do not spend unused budget on extra starts or solvers.


Primary audit gates


Gate A — exact reproduction
PASS only if Stage A passes.


Gate B — full-train optimization
PASS only if the returned full-fit point satisfies both:
J1_full <= 0.9920
and
J1_full <= J1(C0) + 1e-4.


This tests whether the new solver can at least recover the already-known train-only descent rather than remaining at baseline.


Gate C — held-out source-group transfer
PASS only if:
- at least 4 of 5 held-out folds improve their frozen data-only robust score versus baseline;
- median held-out improvement >= 0.5%;
- no held-out fold regresses by more than 5%.


Gate D — integrity
PASS only if:
- no nonfinite output;
- no parameter bound violation;
- objective fingerprints deterministic;
- exact group/window coverage preserved;
- no forbidden split/outcome opened.


Parameter stability is diagnostic, not a selection gate.
Report fold-to-fold logtheta distances, bound proximity and active worst-half group changes without selecting a nicer fold.


Scientific statuses


TRAIN_OPTIMIZATION_AUDIT_PASSED
Gate A + B + C + D pass.
Meaning: the frozen H54 train robust objective is optimizable and its direction has train-only cross-group support.
This is NOT an accuracy candidate and does not authorize H54 check/development reuse.


TRAIN_OBJECTIVE_OPTIMIZABLE_BUT_NOT_TRANSFERABLE
A+B+D pass, C fails.
Meaning: full train J1 can be lowered, but the direction does not reliably transfer across held-out train groups.


SOLVER_FAILED_TO_REPRODUCE_KNOWN_DESCENT
A+D pass, B fails.
Meaning: even the preregistered derivative-free protocol cannot reliably recover the known feasible descent from baseline.


INVALID_OBJECTIVE_REPRODUCTION
A fails.


INTEGRITY_FAILED
Forbidden data access, nondeterminism, broken coverage or invalid numerical state.


Required outputs
research/R6/H61/R6-H61_PLAN.md
DEPENDENCIES.lock
OBJECTIVE_REPRODUCTION.json
LINE_SCAN.csv
FOLDS.json
FULL_OPTIMIZATION.json
FOLD_OPTIMIZATIONS.json
HELDOUT_TRANSFER.csv
PARAMETER_STABILITY.csv
CALL_LEDGER.jsonl
INTEGRITY.json
SUMMARY.json
REPORT.md


No candidate.patch.
No development.csv.
No check/validation/final metrics.


Testing
Run canonical and research-integrity tests plus H61 tests for:
- exact H54 objective reproduction;
- group subset arithmetic;
- top-half stable ordering;
- Powell bound transform/input handling;
- deterministic fingerprints;
- fold isolation;
- data firewall;
- call-budget enforcement.


Drive finalization
Use the existing H61 workspace.
Store task/lock in 00_TASK, checkpoints in 01_CHECKPOINTS, compact results in 02_RESULTS, heavy evidence in 03_EVIDENCE, REPORT/manifest in 04_DELIVERY and handoff in 05_HANDOFF.
Do not duplicate canonical source/dataset/H42/H43/H44.


Registry
After claim verification, set H61 to RUNNING.
At completion update only H61 and the Claims row.
Do not modify H54 verdict.


If H61 passes
Do NOT immediately evaluate the H61 theta on already-revealed H54 check/development.
Recommend a separately preregistered next-stage protocol using still-unopened evidence only.


Final response
Return:
H61 status
claim verified YES/NO
objective reproduction
J1 baseline
J1 C0 witness
J1 full Powell
full gain
held-out folds improved / 5
median held-out gain
worst held-out regression
fold parameter spread
actual evaluation count
forbidden data opened YES/NO
development/check/validation/final opened NO
branch/commit
REPORT link
evidence ZIP/receipt
Drive workspace


Main principle
H61 is not allowed to prove that a particular F/P/B configuration is accurate.
It is allowed only to answer whether the frozen H54 group-robust train objective can be optimized reproducibly and whether that train-only direction transfers between source groups.

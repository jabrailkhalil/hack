# R6-H61 — train-only optimization audit, frozen before scientific calls

Owner LOCAL_AGENT_H61; existing GitHub refs claims/R6-H61 and research/R6-H61
both verified at b2783206000091ab11a1c11ac3ff79082188a4fb before worktree creation.
CLAIM_RECEIPT.md and PROMPT.md preserve the native Drive documents. No second
claim or execution. Canonical tree 973d50d288e050325ee1c71a90fa8d81f2a099af:
320 files/content/modes checked. Full champion_v8 YAML, unchanged runtime.

## Dependencies and firewall
Only six explicitly allowed H54 files are downloaded. Contract hashes bind
PLAN, study.py, H44 source, config, core, readout and timeline. H54 lock binds
exact H44 windows/metadata/window lock. New DEPENDENCIES.lock records all bytes.
H44 sample container includes both folds; loader exposes only original fold=fit
rows (141 windows, 15 groups) exactly as H54. No check target/prediction evaluation,
no DB opening, no H43 error atlas, no other hypotheses or safety witnesses.
H42 is an unsigned offline proxy. It never enters runtime inputs.

## Objective and environment
Reuse exact H44 Predictor/errors and exact H54 six()/Objective methods, including
within-group equal-bag/equal-window weighting and stable lexicographic tie order.
Use frozen H54 denominators, never renormalize on candidate losses. For subset S:
J=.5 mean(Rg)+.5 mean(top ceil(|S|/2) Rg)+.01 mean(x*x).
x=log(theta/theta0); theta=F/m,P/m,B/m; bounds [.05,1,.05]..[5,100,5].
Subset weighting recomputed by exact H54 Objective on that subset only.
Single native float64 process, BLAS/OMP/VECLIB/NUMEXPR one thread. No cache hiding
physical calls. Every predictor invocation on aggregate windows is journalled
before execution and counted; exceptions count too. Hard cap 900.

## Fixed sequence
A: two physical repetitions each of baseline and frozen C0. Require identical
prediction, six-residual and group-loss fingerprints. Baseline J tolerance 1e-12;
C0 witness .9919358040775982 tolerance 1e-9. Failure stops optimization.
B: exactly 21 alpha=i/20 points, x=alpha*xC0. Passive branch/clip counters;
alpha0/1 residuals must exactly match A. These points cannot select starts.
C: exactly one scipy.optimize.minimize(method='Powell') from zeros, original
log bounds, xtol=1e-6, ftol=1e-8, maxfev=130. Default other options unchanged.
Freeze returned x/status before later evaluations. Do not replace returned x
by best line-scan point or a nicer intermediate evaluation. Report budget exit.
D: FOLDS.json committed before any optimization: lexicographic group index mod5.
Exactly five Powell runs, each only 12 training groups, same settings/start.
Freeze ALL five returned x before any held-out score is calculated. Then evaluate
each disjoint 3-group held-out subset at baseline and twice at its frozen x.
Held-out H excludes prior. Actual baseline arithmetic retained, not forced to1.
Two final full-fit repeated evaluations and two repeated training-subset evaluations
per fold verify frozen returned points. No restart, alternative solver, or tuning.
Maximum planned calls: 4+21+6*130+2+5*2+5*3=832 <=900. Remaining calls unused.

## Gates and outputs
A exact reproduction. B full J<=.9920 AND <=J(C0)+1e-4.
C >=4/5 held-out gains>0, median gain>=.5%, worst regression<=5%.
D all finite/bounded, exact repeats, same windows/groups, no forbidden access.
No convergence-success gate beyond these user-defined gates; solver termination
is disclosed, never treated as proof of global optimum. A failure => INVALID_OBJECTIVE_REPRODUCTION;
integrity failure => INTEGRITY_FAILED; A+D with B fail => SOLVER_FAILED_TO_REPRODUCE_KNOWN_DESCENT;
A+B+D,C fail => TRAIN_OBJECTIVE_OPTIMIZABLE_BUT_NOT_TRANSFERABLE;
all pass => TRAIN_OPTIMIZATION_AUDIT_PASSED. No accuracy claim in any case.
Parameter stability: fold theta min/max/std, log-distance matrix, bound proximity,
and active worst-half groups, diagnostic only. No selection using these values.

Canonical/integrity tests and H61 synthetic arithmetic/ties/bounds/fold/firewall/
budget/fingerprint tests precede expensive execution; they do not invoke physical
H44 objectives. All final evidence is train-fit-only. No candidate.patch or
check/development/validation/final evaluation. Commit and publish only H61;
preserve claim ref, main and historical verdicts. Export report, compact results,
evidence, receipt, handoff and chat record to existing Drive workspace and update
only H61 Registry/Claims. Stop after audit; no downstream accuracy stage.

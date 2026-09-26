# R3-H22 / R3-v8-fixed: PLAN before fitting

## Identity and premise

Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024, actual GuardedReadoutObserver with champion_v8.yaml, canonical guarded executable. Keep 20 Hz/delay0/readout1/holdoff0.5/adaptation0.5/time_compensation0/quarantine1.5 and all source runtime, split, scorer, matching and historical guards unchanged. This branch is research/R3-H22; exact scientific-ID branch/PR searches were empty before creation. No moving main, merge, auto-merge, H23, ACL/secrets changes or paid resources.

This PLAN is published AFTER the separately preregistered baseline-only premise probe and BEFORE any fitting/comparison of A/B. Probe source 9d469305eb7c1fa4f00fbbf9357eb3486aeb3430; checkpoint 7ed10fa23dff2bf264edb93652359f9728fdad88; run36220031909. On all64 train bags, 175 eligible windows in24groups; 153 windows/24groups have |prefix error at5s|>=0.1m. Full101-point vectorized/canonical parity max1.7763568394002505e-15m/s. These are errors against a dependent wheel proxy, not ground truth, beneficial interventions or accuracy evidence. The original DIAGNOSIS_PLAN thresholds were passed unchanged.

R2-H16 report at476ffef5d4135377dc0215572cdabed520b6acfa and source9b382e352ea6037a71182bedd98bbc34c4b3098f are motivation: fault aggregate improved but distance and long-coast/group errors regressed. No H16 refit or third selectable model here.

## Frozen data and initialization

Use exactly the same input-only window rule and train fitting/check group assignment as DIAGNOSIS_PLAN. Exact lists are in train_groups.json, reproduced by the probe. Sorted linked train groups at positions0,4,8,... are check (7metadata groups,5with windows); the remaining20 are fitting (19with windows). Actual fitting145/check30 windows, phases traction58/coast58/braking59. All64 train bags retained in access/inventory; no train GNSS. No role changes. Development means all17 original development bags with both receivers in the external evaluator, never validation relabelled as development.

For EVERY theta use5s canonical causal warmup; then5s recursive model-only forecast with legal commands. Resistance and power limitation use recursively predicted velocity, never wheel target. Retain the pre-window readout during held-wheel freshness; no future target affects initial state. Evaluate published velocity at0.5/2/5s. Prefix integral includes all101 source-grid values from anchor; trapezoidal integration uses actual output dt. Future wheel proxy values occur only in offline target/loss. Full forecast parity against actual observer is required at1e-10m/s for baseline and both fitted configurations.

## Two dimensionless objectives, no tuning of their scales

h=(0.5,2,5)s; sigma_v(h)=0.1+0.2*h m/s = (0.2,0.5,1.1)m/s. sigma_s(h)=h*sigma_v(h) = (0.1,1,5.5)m. Let e_v be predicted minus wheel-proxy velocity, e_s(h) the trapezoidal prefix integral of e_v. rho(x)=2*(sqrt(1+x*x)-1), evaluated by a numerically stable equivalent.

L_v = mean over fitting groups, then their windows, then3 horizons of rho(e_v/sigma_v).
L_s = the same grouping of rho(e_s/sigma_s).
A minimizes L_v + lambda_s*L_s, lambda_s=1.0.

For each nonempty fitting group/anchor-phase cell c, C_c(theta)=mean over windows/horizons of rho(e_v/sigma_v)+lambda_s*rho(e_s/sigma_s). C_c(theta0) is computed once on FITTING ONLY. With T=0.1:
P(theta)=T*log(1 + mean_c exp((C_c(theta)-C_c(theta0))/T)).
B minimizes L_v+lambda_s*L_s+lambda_w*P, lambda_w=1.0. Use stable logsumexp/logaddexp. This smooth worst-cell regression proxy is not a hard guarantee; P(theta0)=T*log2, not zero. Empty cells are reported as missing, not fabricated zero loss. No per-group refits or data-dependent scale fitting.

The least-squares residual is sign(x)*sqrt(rho(x)) with exact group weights; do NOT robustify the weighted residual again. The B penalty is one sqrt(lambda_w*P) residual. Report all component losses separately before/after, including unpenalized velocity/prefix and P; pooled windows are not independent trials.

## Physical gauge, bounds and strict budget

Only seven effective coefficients may change: force/mass, power/mass, brake/mass, rolling/mass, quadratic/mass, command exponent, actuator tau. Mass40000kg, radius0.33m, gear6, efficiency0.9 and wheel scale remain fixed. Original bounds LOW=(.05,1,.05,0,0,.3,.05), HIGH=(5,100,5,.4,.005,3,3). Start each fit once at exact v8 effective theta0. x_scale=max(abs(theta0),.1*(HIGH-LOW)). No numerical-predictor changes or new runtime histories.

Exactly fits A and B, in that order. scipy least_squares(method=trf,jac=2-point,loss=linear,max_nfev=80,ftol=xtol=gtol=1e-8). HARD combined limit1600 actual residual calls, including finite-difference Jacobian calls. Count immediately before every evaluation; save trace/calls/status. On exhausted budget discard an incomplete fit, no restart or increased budget. max_nfev and actual calls reported separately. Nonconverged/invalid candidates cannot be admitted. Sensitivity SVD is of the executed objective Jacobian (B includes penalty), not proof of independent physical identifiability.

## Train-check selection fixed BEFORE development

After both fits, compute the same losses on the untouched check groups, using check baseline cell losses only for evaluation. Veto a fit if not converged/finite/in bounds, full rollout parity fails, or either check L_v/L_s regresses >0.5% (+1e-12 numerical allowance). Additional machine veto: for EACH check group and EACH anchor phase at EACH horizon, velocity RMSE must not exceed baseline+max(0.02m/s,10%baseline), and absolute signed prefix-integral bias must not exceed |baseline|+max(0.02m,10%|baseline|). These proxy safeguards supplement, never weaken, the R3 development gates.

Rank eligible A/B by check L_v+L_s+P (same ranking for both), tie-break A. Commit selected configuration and selection evidence to this research's checkpoint BEFORE development measurement. Neither development reference nor another agent's validation chooses the variant. If both fail train-check veto but at least one finite fit exists, fix the same minimum-rank fit for ONE explicitly diagnostic-only full observer development evaluation; carry all train-check vetoes forward permanently, validation remains forbidden. This diagnostic evaluation measures the actual consequence rather than relabelling proxy improvement as accuracy. No switch to the other fit after development. If no completed fit: INCONCLUSIVE, no development/validation.

## Actual intervention and prospective R3 admission

Development activation requires >=1000 clean returned-velocity ticks changed by >1e-6m/s in >=3 original source groups, with original schedule maintained. Coefficients merely fitted or loss evaluated is not activation. Report phase counts and worst group/phase/horizon velocity, signed bias and integral bias including coast. Inadequate coverage => INCONCLUSIVE.

The ONE preselected candidate is eligible for validation only if ALL below pass on all17 development bags:
- train-check veto list empty; sufficient activation;
- >=2% clean group-macro RMSE gain OR >=5% ORIGINAL fault-event group-macro RMSE gain;
- clean/fault/pooled aggregates regression <=0.5%; scalar-span distance <=1%; clean per-bag/receiver RMSE <=baseline+max(.005m/s,5%baseline);
- identical per-comparison n/coverage/masks/output timestamps, no new false stops or INDIVIDUAL new unrecovered cases, no causal/reset errors;
- low-speed and abrupt common-mode suites below each event group-macro regression<=0.5%, no new individual false-stop/unrecovered cases.
Use absolute delta<=1e-12 if an aggregate baseline is zero; no division by zero. Missing necessary reference/suite coverage => INCONCLUSIVE, not PASS. Rejection at development => NO validation IO, no validation freeze. No threshold changes after numbers.

Original fault_windows/scorer/aggregation remain baseline definitions. Supplemental low-speed construction is the existing PR13 low_speed.py at f10e3cfc0689ecbd7894575945897a6696db3e72: first valid agreeing wheel mean1..2m/s, u>=0, t>max(25,.1*duration), t<duration-25; lock3/5s; warmup20s, after10.1s. Apply to genuine DEVELOPMENT only. Common-mode construction/injection directly uses fixed-v8 tools/research_h11/compare.py: original first valid agreeing mean>2 anchor, t<duration-35, +5m/s to both for0.7/1.2s. Their gains never replace original-suite gain. Both algorithms get identical arrivals/injections; no runtime fault oracle.

Report worst-group table, all per-bag/receiver/fault metrics, MAE/signed bias/recovery and before/during/after dropout state traces. Diagnostics do not authorize another fit. Baseline problems never authorize added failures.

## Tests, cost and publication

Run unchanged runtime/research-integrity suites, H22 numerical loss/budget/target-isolation/rollout tests, feature-off exact canonical-v8 equality, causal prefixes, duplicate/future/stale/reset/bounds, low-speed zero-lock and H11 quarantine. Verify returned s/v consistency, all unchanged Config fields and bounded runtime state. Scorer baseline independently reproduced by canonical guarded driver with same explicit v8 profile (not its stale historical models() pins). Save immutable source/split/data fingerprints.

CPU cost on first development stream30618_0652866c: warmup10s plus60s measurement, six AB/BA pairs per step/replay, threads1, same output collectors, no audit in timed path. Save CPU/wall and repeated-output fingerprints. One research-process high-water RSS is NOT node RSS. No timing-based selection. If accuracy fails, enabled installed ROS benchmark is NOT_RUN_AFTER_REJECTION. If it passes, fresh installed enabled ROS replay in both clock modes offline2CPU/500000000bytes and actual parameter/import hashes is mandatory before merge readiness.

Validation, if admitted, requires a separate published FREEZE commit binding selected source/config/evaluator/split/data hashes BEFORE first IO, then exactly one all-validation original-suite comparison. There is no hidden push-triggered validation in this fitting workflow. Old validation remains reused, not independent final test. Final/test payloads never decoded/evaluated.

Compact REPORT/SUMMARY/coefficients/CSV/manifests in Git; large traces only compressed Actions artifact with30day retention and SHA256. Preserve failed stages, source candidate SHA distinct from later report SHA. One Russian draft PR R3-H22 with verdict, never merge/auto-merge. Separate mechanism_status, coverage_status, scientific_verdict, accuracy_contract_passed, runtime_verified, ready_to_merge.

Known Consensus/Scite quota stop is not bypassed. Primary DOI10.1002/acs.1203 metadata/abstract serves as motivation only; Wolfram worksheet with actual output/warnings checks normalization, b*h and acceleration-bias accumulation, gauge invariance and robust-residual identity, not global stability or accuracy.

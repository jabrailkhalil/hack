# R4-H38: Student-t-like bounded measurement update

Status: preregistered BEFORE train innovation diagnostics or candidate measurements.
Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024; full tree eae49a504bc59b5c9b408445150bef32e111956f. User ZIP SHA256 a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2, 301 project files verified. Branch research/R4-H38. Local snapshot Git ancestry is not remote baseline ancestry.

## Existing evidence and scope
H02 PR15, H05 PR17 and R2-H20 PR35 were read. Their negative heuristic weights are counterexamples, NOT mathematical rejection of a Student-t likelihood. H20 exposed a both-sign trade-off; collect both signs and impose the explicit diagnostic veto below. R3-H28 is another unfinished scientific ID, not this experiment; do not restart it or import its mechanism. Existing canonical v8 is GuardedReadoutObserver with complete champion_v8.yaml: readout 1/.5, adaptation .5, wheel_time_compensation=0, common-mode quarantine 1.5, output 20 Hz/delay0. Compare returned Estimate.v/s.

Potential defect: legacy R inflation is linear in a pre-update residual above 3*wheel_sigma and has no heavy-tail likelihood interpretation. There may be sub-hard-gate extremes for which a bounded heavy-tail update gives better velocity estimation. This is a hypothesis; innovations include dynamics, timing and reference-independent model error, not pure sensor noise. New weighting can suppress genuine acceleration or increase confidence in false common-mode values after dropout.

## Fixed mathematics and budget
Exactly two prospective candidates: nu=4 and nu=8; no other nu/Q/R/physics/adaptation sweeps. Initial measurement variance floor R0=sigma_wheel^2 times existing confidence (1 for two agreeing accepted wheels, otherwise4). Never divide by number of wheels.
Student-t scale S=R0*(nu-2)/nu, so the UNBOUNDED t likelihood variance is R0. Gaussian prior is N(m,P). Lambda mixing prior Gamma(nu/2,nu/2). Initialize e=r=z-m, C=P. Repeat exactly THREE deterministic coordinate updates:
  Rraw=((nu-2)*R0+e^2+C)/(nu+1) = S/E[lambda]
  Reff=clip(Rraw,R0,100*R0)
  K=P/(P+Reff)
  e=(1-K)*r
  C=(1-K)^2*P+K^2*Reff
Every iteration uses the SAME original prior and measurement, NOT successive re-assimilation. Last Reff drives the ordinary single Joseph correction; posterior floor 1e-8 is retained. Any nonfinite intermediate/invalid numerical result falls back to the exact legacy soft inflation for that update. Neither the original residual penalty nor an extra learned outlier frequency is composed with Reff. Fixed clipping and three iterations make this an engineering approximation, NOT the exact published VB algorithm or exact Student-t posterior covariance. Large-nu limit is the confidence-floor Gaussian update, not the legacy residual-inflated model.

Implementation after foundation: isolated subclass/private copy of the FULL verified Observer.step generated programmatically, with only the soft R line delegated to the new rule. Canonical core/readout/config/Timeline/ROS default/evaluator remain unchanged. No new runtime input or unbounded history. Existing d learning, stop/recovery and hard gates retain their formulas; changed velocity may affect their subsequent numerical state. Readout may retain its reconstruction ONLY after checking its equality to actual final Joseph K/P; otherwise pass actual values explicitly without changing the correction rule. Exact feature-off equivalence includes all original v8 fields and returned Estimate.

## Foundation BEFORE enabled observer
All 64 original train bags, vehicle channels only; zero GNSS train queries. A baseline-only probe records accepted pre-update innovations, actual prior, confidence floor, sample age, command mode, command-stable duration and model acceleration. Save per-group and mode/age/acceleration strata, raw/centered quantiles and tail counts; no IID significance claim.
Foundation is sufficient only with >=100 accepted sub-hard-gate cases with abs(residual)>3*sqrt(R0), age<=.1s, valid controller and unchanged command for >=.5s, across >=3 source groups. Both prospective scalar rules must change Reff relative to legacy R by >=1% on >=100 of these cases across >=3 groups. Compute these scalar prospective weights offline without feeding them into baseline. Group-stratified centered tails remain descriptive; they cannot establish pure measurement-noise origin. Insufficient foundation -> INCONCLUSIVE, no enabled runtime candidate, no validation; do not lower thresholds.

## Sanity / executable safety counterexamples
Baseline unit and research-integrity first. Enabled tests cover finite/PSD/Joseph, scale versus variance, exactly3 iterations, lower/upper R bounds, symmetric signs, small residual, nu->infinity, fallback, actual gain/readout parity, causal prefix, held duplicates, stale/future, reset, constant state size, and feature-off exact v8.
Synthetic actual acceleration (both signs, healthy two wheels, no GNSS runtime), genuine dropout/recovery, one-wheel positive/negative sub-hard outlier, low-speed common lock and abrupt common jumps are compared. True-motion RMSE tolerance is baseline+max(.005m/s,.005*baseline); no extra false STOPPED samples at true speed>1, and no new failure to recover within10s. These checks veto validation; a failing check is a counterexample, not a reason to redefine the test.

## Data and measurement
Pinned dataset ZIP and every extracted bag SHA256 plus immutable split verified. A separate data-export Actions job may transfer only64 train+17 development raw databases; no SQLite decoding in that export. Test/validation DBs not extracted in this stage. Store enforces actual train/development role BEFORE any IO; read-only SQL decoder/order/origin/scales match legacy. Baseline-only and candidate receive the same events.
Use unchanged tools/finalization/evaluate.py score/replay/match/distance and tools/research_v6/compare.py aggregation. Factory adaptation only; no scoring changes. Development exactly17 original bags/7 groups. Canonical baseline expected clean .09266814298282507, fault .2375486120563008, pooled .1293056944774334, distance5.310295004801444, n394221. Reproduce by execution before claims. Feature-off/direct canonical equality must also hold at full outputs and all original states on real development.

## Registered development suites and gates
Original clean + exact original bias5/dropout5/dropout10/lock3 anchors/cropped warmup/recovery unchanged.
Pinned low-speed suite: first valid grid point with 1<mean wheel speed<2, abs(front-rear)<.15, u>=0, t>max(25,.1*T), t<T-25; lock3 and5, 20s warmup/10s recovery, as baseline LOW_SPEED_REPORT.
Pinned abrupt common-mode suite: import exact H11 common_fault_windows; +5m/s for .7 and1.2s. No quarantine changes.
Additional diagnostics, original vehicle-selected moving anchor: front and rear separately, signed +/-0.8m/s bias for5s with 1s linear rise; also dropout5s followed by common +/-2m/s for1s. Inputs corrupted externally, no oracle passed to algorithm. Each sign/suite is reported separately. No extra false-stop/individual unrecovered and <=.5% event group-macro regression for each diagnostic sign/suite; no newly accepted channels during a common false-pair interval relative to baseline. These diagnostic gains do NOT replace original gain.
Full-faulted-bag replay for every original fault: score full continuous distance spans, save delta_s at recovery horizon and final timestamp. Require full-faulted distance macro <=1% regression, same schedule/reference coverage. Residual delta_s is descriptive, not erased at recovery.
Admission requires ALL: >=2% original clean OR >=5% original event-fault gain; clean/fault/pooled <=.5% regression; clean distance<=1%; per-bag/receiver clean<=baseline+max(.005,5% baseline); identical schedule/coverage and zero additional false stops, individual unrecovered, causal errors/resets; low-speed/common-mode each<=.5% regression/no new safety failures; all prerequisites and diagnostic vetoes above; >=100 changed accepted gains and >=100 changed outputs (abs(delta_v)>1e-6) across>=3 development groups. Preserve all two variants.
Choose eligible candidate with smallest original fault RMSE, then clean RMSE, then nu8 for an exact tie. If none eligible -> REJECTED for active covered candidates, validation NOT RUN. Foundation/activation shortage -> INCONCLUSIVE unless an actual safety counterexample independently rejects the tested rule.

## Freeze / validation / runtime
Only after positive development: freeze ONE candidate, hashes/code/config/PLAN/development decision, externally commit/push BEFORE validation. Publication failure -> checkpoint, no validation. Then exactly one full19-bag original validation plus registered safety checks; no retuning. Reused validation is not independent final test. Final/test payloads never opened.
Enabled installed ROS under2CPU/500000000bytes, both clocks, real development replay/latency/RSS required only after positive accuracy; otherwise NOT_RUN_AFTER_REJECTION. Offline CPU measured on first full development bag, one warmup then AB/BA/AB/BA, identical collectors/threads; step and replay separate, active and healthy costs separate. Whole process RSS is not node RSS.

## Artifacts and status
New reports/research_R4/H38/<execution-id>/ only. Keep SOURCE_RECEIPT, PLAN, hashes, imports/factory/config, raw compact per-bag/per-group/per-scenario results, tails/activation, all variants, commands, logs, math and source-reading scope. Large traces compressed separately, no dataset committed. measured_source_sha/report_sha/checkpoint_sha separate. Draft PR in Russian with exact ID/verdict, not ready to merge for negative/incomplete work. Never merge, auto-merge or force-push.

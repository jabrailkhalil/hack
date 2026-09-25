# H06 — preregistration before experiments

Baseline: `984fdf2fc4faf05325249215d6b8541c0e68209a`, active profile `adaptive_v5` (adaptation_tau_s=0.5). Branch: `research/parallel-H06`. No merge, auto-merge, main writes, other research branch writes, or published report rewrites.

## Mechanism and search budget

Exactly ONE candidate, `H06_evidence_04s_15x`; no parameter sweep and no changes after looking at validation. This is a research runtime implementation, not promotion of the ROS default.

Keep the existing causal pairing, hard anomaly rejection, residual cap, zero-lock exclusion, disturbance adaptation, physical coefficients and timeline. Add bounded evidence of recovery ONLY when two distinct fresh agreeing wheel observations have dynamic acceleration consistent with the model and a valid controller command. This does not mistake front/rear agreement for two independent observations.

After the baseline hard checks, accumulate at most 0.4 seconds of evidence from pair intervals in [0.05, max_age_s]. A good interval requires front/rear disagreement <= min(disagreement_mps,0.2), absolute wheel acceleration >=0.15 m/s^2, absolute model acceleration >=0.15 m/s^2, same acceleration sign, and acceleration mismatch <=0.35 m/s^2. Valid controller command is required. Add interval duration on good evidence; on bad evidence subtract twice the interval duration, clamped at zero. Invalid pair intervals or baseline hard rejection clear evidence. Model acceleration is the same clipped model prediction used by the observer, not an acceleration reconstructed from corrected outputs.

Let q = accumulated_evidence_s / 0.4, clipped to [0,1]. Required dwell becomes 0.8 - 0.4*q seconds for the fixed baseline profile; the bounded correction step becomes the original per-pair step multiplied by 1 + 0.5*q (maximum 0.225 m/s per nominal 0.1 second fresh pair). Keep the existing pair_dt scaling; no more corrections on prediction-only ticks. q=0 reproduces the original dwell and step. Hard failures and normal accepted-wheel fusion reset evidence. Constant common-mode false speed cannot earn dynamic evidence, but a dynamically consistent common-mode offset is fundamentally ambiguous with these inputs; explicitly test and disclose this limitation.

Implementation may refactor baseline recovery dwell/limit into overridable hooks whose default arithmetic is unchanged. Candidate is an opt-in Observer subclass. The baseline and all metric/fault/split files remain available for source-hash and output-equivalence checks.

## Data roles and freeze

Use the existing `Store.load(bag, 'train')` for train checks; it excludes reference topics. Train checks are execution/invariant checks, not ground-truth accuracy evidence. Do not weaken this loader to obtain training GNSS. Parameters above are fixed a priori and will not be tuned on validation. Commit implementation/tests and record their SHA256 plus baseline, evaluator and plan hashes in a candidate freeze BEFORE any validation measurement IO. Only this one candidate may be compared on the reused validation. Do not instantiate FinalStore or open final-test measurements/results for selection.

Baseline and candidate must use the same unmodified `tools/finalization/evaluate.py` score/replay/match/metric functions, 20 Hz / zero alignment delay, timestamps, reference masks, both receivers, fault anchors and fault windows. Observer factory injection in the experiment runner may select baseline or candidate class; it must not change scoring. Reproduce the v6 baseline fault scenarios: front bias +5 m/s for 5 seconds, two-wheel dropout for 5/10 seconds, and two-wheel zero lock for 3 seconds at the existing deterministic anchor. Keep group-macro, pooled and per-bag/receiver outputs, including missing references as missing, never zero error.

## Falsification and fixed acceptance gates

At least 2% clean group-macro RMSE improvement OR 5% fault-event group-macro RMSE improvement versus adaptive_v5. Each primary aggregated metric (including pooled speed RMSE) may regress at most 0.5%; distance surrogate at most 1%. Every clean bag/receiver RMSE regression <= max(0.005 m/s, 5% of baseline). No lost coverage, extra false stops (also per bag/receiver), extra non-recovery, causality errors or unexpected resets. Preserve the published v6 gate implementation and add the explicitly required pooled-RMSE gate; never relax a gate. No post-hoc tuning or replacing fault-window RMSE with a favorable recovery metric. Recovery time is secondary descriptive evidence.

A gain below threshold or a gate violation rejects the candidate. Missing real validation or runtime evidence means insufficient data, never a fabricated pass. Common-mode stress and unit/synthetic tests are safety/invariant probes, not proof of real-recording improvement. Reused validation is not an independent final test. Full ROS latency/resource measurements of v4/v5 cannot be attributed to H06.

## Evidence and execution boundaries

Save fresh results under `reports/research_H06/runs/<run_id>-<run_attempt>/` on a new `checkpoint/H06-<run_id>-<run_attempt>` branch; never overwrite existing runs. Save raw per-bag clean/fault results, aggregate decision, access journal, source/config hashes, commands and actual test logs. Publish a Russian draft PR. Without confirmed improvement label it as an unconfirmed/negative research result, not ready to merge.

Initial environment observation: GitHub connector reads succeed; local container `git ls-remote https://github.com/jabrailkhalil/hack.git HEAD` fails with DNS resolution error. No experiment has run at preregistration. Prior evidence reviewed: reports/research_v6/REPORT.md, reports/research_v5/REPORT.md, baseline core and v6 comparison runner. Historical multirate reacquisition is already included in this baseline and is not counted as an H06 innovation.

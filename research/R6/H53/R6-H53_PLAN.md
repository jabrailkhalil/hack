# R6-H53 — preregistration before window outcomes or fitting

## Identity and locked inputs

Only R6-H53, branch research/R6-H53. Baseline b2783206000091ab11a1c11ac3ff79082188a4fb, tree 973d50d288e050325ee1c71a90fa8d81f2a099af, all 320 source paths/bytes/modes verified. Runtime GuardedReadoutObserver with every field from champion_v8.yaml; 20 Hz, delay 0. No moving main, merge, auto-merge, force push or changes to historical research. The explicit R6 wave launch governs the round; shared CURRENT STATE still says R5 with the same baseline.

New local DEPENDENCIES.lock.json SHA256: 9c81220fe4e7c9cab70aaeaa1d497aabc3f1319f4b2a5275b6b618ca0cd82e20. Verified actual source, dataset, H42, H43, H44 evidence bytes and original native handoff verifiers (85/53 files). All 64 fold assignments match. Lexicographically first representative per exact vehicle-wire hash gives 36 fit and 12 check representatives; duplicates remain in inventory, not independent weight. Lock precedes SQL, teacher array decoding and all replay. Only these 48 train DBs extracted; no development/validation/test extraction. H44 measured source 0ca93500d4d305c21c998bfd8d2a2e78c98b90ad is evidence, not a promoted candidate.

## Scope and controls

Change only the offline objective and its training windows. Same canonical F/m, P/m, B/m parameterization for C0 and C1, using the original torque/power/brake Config fields. No change to d adaptation, readout, R/Q, gates, stop, recovery, zero-lock, quarantine, Timeline, timestamp matching, scorer or signed s. No H52 initialization experiment, H54/H57 mechanism, H59 residual or A0 safety-witness fitting. Five-second local warmup remains fixed. Every residual evaluation executes the real scalar observer under its own theta during warmup and subsequent prediction/recovery. No copied baseline d/drive_a, no vectorized surrogate.

C0: matched short H44-style GNSS objective on the SAME long-eligible anchors, including its existing prefix-integral terms.
C1: that same short objective plus the fixed full-cycle terms below. Only C1 is selectable. Exactly two fits, no G/W factorial, no alternative objective weights, durations or recovery horizons.

## Prospective anchor and availability rule

Build an input-only transport table with the unchanged Timeline in original event order, at 20 Hz/delay0. It records held controller/front/rear samples, not model prediction outcomes. Consider every 100th output tick (5 s), starting index100, with 100 prior ticks and 401 future ticks available. For each bag retain at most the first two eligible anchors per command phase (traction u>deadband, braking u<-deadband, otherwise coast), in time order. No ranking by baseline error, GNSS value or atlas error. Require continuous grid, finite and fresh in-range controller and two wheels throughout the 5 s warmup and longest cycle; source skew and wheel disagreement within the existing canonical limits. Require some motion abs(mean wheels)>.5 m/s in the first10 s. Rejections and all source groups retained in coverage.

Let t0 be the last healthy output (anchor index). Actual virtual fault interval is [a,a+D), a=t0+.05, D in {5,10} s. Recovery terminates at a+D+10. Warmup uses the101 held tuples from t0-5 through t0. Wheel events, not observer state, are withheld by the same source-time predicate as the canonical evaluator. Command continues and old held wheels age naturally. For each chosen window verify its captured fault input tuples against a fresh unchanged Timeline traversal with the actual withheld events. Every optimization uses those exact tuples. Metrics use returned Estimate.v/s. Event velocity samples satisfy a<=t<a+D; endpoint integrals are evaluated at a+D and a+D+10, with origin t0. Short terms use the10 s dropout's outputs at a+.5,a+2,a+5, all still inside that outage. This avoids counting two identical short prefixes as independent evidence.

Require accepted H42 coverage at EVERY output timestamp from t0 through a+20. Use an exact accepted row or the immediately adjacent two accepted native rows with gap<=.2 s; no masked-row removal, bridging, extrapolation or wheel substitution. Check-role prefit IO is LIMITED to deterministic vehicle input/anchor construction and teacher stamp/accepted fields for the explicitly required coverage gate; no check speed_mps decoding, predictions, loss or parameter selection before C0/C1 freeze. Accepted finite-target consistency is checked when authorized targets are decoded; inconsistency stops, never repairs masks. Fit targets are unsigned speed_mps; use abs(predicted v) only offline. Runtime s stays signed and is neither reset nor replaced by a magnitude integral.

Coverage gate: >=3 fit source groups and >=2 check source groups each with at least one eligible long-cycle anchor. Also require >=1 eligible anchor overall per fold (implied). No extra posthoc phase/group minimum. If insufficient, FOUNDATION_FAILED, zero fits. Phase/vehicle and counts are reported, not silently discarded.

## Exact objective, units and weights

q(t)=abs(returned Estimate.v(t)); y(t)=unsigned H42 target. I(h)=trapezoidal integral of q-y from t0 to the specified output h, in meters. sigma_v(h)=.1+.2*h m/s, h in seconds.

Short loss per anchor L0 = mean over h={.5,2,5} of the SIX squared residuals: (q(a+h)-y(a+h))/sigma_v(h), and I(a+h)/((h+.05)*sigma_v(h)). This preserves the H44 velocity+prefix-integral structure, accounting explicitly for the .05 s interval from last healthy t0 to fault start a.

For each duration D, define V_D as the MEAN squared (q(t)-y(t))/sigma_v(t-a) over all event outputs a<=t<a+D. Define S_D=(D+.05)*sigma_v(D) meters. E_D=[I(a+D)/S_D]^2, R_D=[I(a+D+10)/S_D]^2. Recovery uses the SAME path scale S_D as event end so accumulated area is not discounted by a larger denominator after recovery. Full-cycle loss L1 = L0 + mean over D={5,10} of (V_D+E_D+R_D)/3. Existing short terms are not renormalized away when adding long terms.

Average anchor losses equally within a bag, then bags equally within source group, then source groups equally. Durations are not extra independent anchors. Both fits add the SAME prior .01*mean(log(theta/theta0)^2). C0 minimizes L0+prior; C1 minimizes L1+prior. Report data and prior losses separately. Check uses L1 without prior as the PRIMARY full-cycle criterion, plus all components in normalized and SI units, biases and recovery diagnostics.

## Fixed optimizer and budget

Theta=(F/m,P/m,B/m), initial theta0 from complete canonical YAML, log ratios start at(0,0,0). SI bounds lower(.05,1,.05), upper(5,100,5), same as H44. SciPy least_squares TRF, jac=2-point, loss=linear, x_scale=1, ftol=xtol=gtol=1e-8, max_nfev80 each, no restarts. Count and journal EVERY actual residual call including finite differences; hard total cap1000. Failure/budget exhaustion is not permission for another fit. Final artifacts retain exact Config and readout fields, source hashes and used windows.

## Freeze and gates

After both fits and tests, freeze exact C0/C1/source/input/evaluator/anchor hashes in a published commit before decoding check speeds or executing check predictions. One fixed confirmation of v8/C0/C1 on those prebuilt check anchors, no retuning or alternative candidate. Numerical reproducibility audit of saved outputs is not another selection pass.

Check admission is conjunctive: C1 primary group-balanced L1 improves >=5% versus C0; no check source group L1 worsens >5% (tolerance1e-12); at least two-thirds of represented groups strictly improve; deleting ANY one group from the fixed check results preserves positive aggregate gain. Also C1 primary L1 must not regress versus canonical v8 by >.5%. No new individual failure to recover within10 s (20 consecutive outputs within.25m/s of unsigned teacher) or false-stop sample with teacher>1. Loss/safety absence is null, not0. Full component/LOGO diagnostics retained; failed prerequisite prevents development. Effect only on one group is not admitted.

Only admitted C1 gets at most ONE full17-bag development comparison v8/C0/C1. Use unchanged original scorer/masks/fault anchors/grid/group aggregation. Contract L vs v8: >=2% clean OR >=5% original fault-event RMSE gain; clean/fault/pooled principal speed regression<=.5%; clean/full-faulted distance<=1%; clean per-bag <=baseline+max(.005m/s,5%baseline); low-speed/H11 common-mode event regression<=.5%; no new false stops, individual unrecovered/safety failures, coverage loss, causality/reset failures. Require>=100 changed outputs in>=3 reference groups. Full faulted distance and delta_s after recovery,+10 and terminal must be reported without erasure. C0 and rejected H44 G cannot replace canonical baseline. Validation needs a SEPARATE explicit admission decision; final/test prohibited. No validation in this execution.

## Tests and publication

Before fitting: canonical tests, source/hash/native checks, input-only transport parity, withheld-event tuple equality, no future samples, exact theta0/full Config parity, parameters-only bounds, masked teacher/no interpolation over gaps, group weights, objective formula and signed integral identity. Before check: actual fitted C0/C1 causal prefix/reset/duplicates/zero-lock/common-mode and deterministic output tests. Record all failed attempts and corrective code-only changes; no data-driven changes to registered rules. No installed-runtime certification claimed from unit or offline CPU.

On rejection/foundation failure stop subsequent stages and preserve evidence, not another fit. Export PLAN/lock/LONG_CYCLE_COVERAGE/ANCHORS/OBJECTIVE_CONTRACT/fits if any/CHECK_RESULTS/PER_GROUP/RECOVERY_RESULTS/SUMMARY/REPORT and exact research source. candidate.patch only if fitted configuration exists. Large logs/traces compressed in H53 workspace; canonical dependencies only referenced. No rewriting H44/H59 results or copying blocked H59 source. Final report and registry distinguish scientific result, source publication, missing stages and merge readiness. All computations local unless an actual Actions execution is recorded.

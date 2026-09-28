# R3-H27: prospective accuracy PLAN

Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024, actual GuardedReadoutObserver/champion_v8.yaml. This PLAN follows the preregistered foundation, before any candidate accuracy comparison. No validation or test IO has occurred.

## Foundation retained, not retuned

Foundation source9a36b9c216fc9be5783079ba50b4c6f483dd1ff6; run36220511208/1. Train-scale commit70e17cd736175752ad27858401f999116d86a5b5 published before development IO. SCALE SHA256 fd6cc4152626c6b71f1c34d8d9a429d4f2df0fd816fe252937690bd3fb437847; threshold=0.0823180344240239 m/s². The two budgets remain lag0.2/0.4s; no other parameter choices or fitting.

0.2s:14 proposed entries/4groups/14potential ticks, insufficient ticks. 0.4s:15entries/3groups/164ticks, passes the written foundation threshold. Of the latter,12 natural entries are single-tick events;3 original-fault entries provide152ticks in one source group. This is concentrated coverage, not fifteen independent outages or proof of true contamination. All17 development bags/7 original groups were inspected; no reference used in foundation. Both lag values will be measured as the fixed two-variant budget;0.2 cannot be admitted to validation without the same actual coverage threshold. No choosing a new history/threshold after accuracy results.

## Runtime mechanism fixed before implementation comparisons

Add a stdlib-only CommittedDisturbanceObserver subclass; native core, guarded readout, parameters and every native state field remain canonical v8. Reuse the exact foundation History rules in a separately packaged stdlib module: max16 snapshots/1s, availability-time stamps, actual trusted FUSED derivative updates only, same-mode requirement,0.2s median window ending lag before latest trusted update, >=3points/span>=.1s/latest_age<=.35s/MAD<=theta/2/difference>theta. No labels, filenames, fault flags, future samples, independent-wheel assumption or new runtime sensor.

On the first causally observed MODEL_ONLY loss after canonical step, latch checkpoint d if eligible. A duplicate-only MODEL_ONLY tick does not create a loss but continues it. The current tick has all its input evidence available; output-only correction for that same bounded interval is permitted. No backdating of history or waiting for future samples.

Let old_v,old_d be native pre-step values and g=updated native drive_a-resistance(old_v). While the loss is active with unchanged valid command mode:

    delta_a = clip(g+d_checkpoint, +/-max_accel)-clip(g+old_d, +/-max_accel)
    delta_v += dt*delta_a

Native prediction, fusion, stop/reacquisition/quarantine and healthy d updates are never recomputed using delta_v. This is an isolated first-order additive prediction correction, not a second nonlinear physical observer. Effective acceleration is clipped, velocity is clipped to existing max_speed. If corrected speed would cross zero relative to the canonical published speed, use canonical speed instead. This prevents the readout creating a new stop/sign reversal.

At accepted FUSED/SINGLE_WHEEL recovery, reduce delta_v by (1-K), where K=clip(1-native_pv/p_prior,0,1) and p_prior is the native pre-step variance plus the existing process increment. At REACQUIRING, move delta_v toward zero by no more than the native reacquire_step scaled by the actual pair interval; at STOPPED set delta_v=0. These rules add no tuned recovery times. Ending/changing command mode cancels the latched d for subsequent predictions; a previously accumulated velocity error is held until recovery, not silently erased. No decay of d toward zero.

    delta_s += .5*(old_delta_v+new_delta_v)*dt
    output_v=canonical_Estimate.v+delta_v
    output_s=canonical_Estimate.s+delta_s
    output_a=canonical_Estimate.a+(new_delta_v-old_delta_v)/dt

Never reset delta_s at recovery, mode change or stop; only explicit observer.reset resets it. Preserve native Estimate.disturbance and statuses. Conservative additional variance_v=delta_v² and distance sigma envelope integral|delta_v| are diagnostic envelopes, not calibrated probabilities. With enabled=False delegate directly, including exact Estimate. Before any intervention with zero corrections return the native Estimate unchanged.

## Immutable measuring contract

All17 full original development bags; both external reference receivers. Train threshold remains vehicle-only. VehicleStore role/hash guard before read-only SQL; no validation/test CLI for this stage. Same source order/timestamps/scales, official evaluate.score/replay/match/distance and original fault_windows, group-macro summary from unchanged research_v6. Research factories substitute only Observer, with explicit legacy alias mapping to full v8 (not old v5). Compare published Estimate.v/s. Verify off and every original inner field versus an independent canonical v8; baseline replay fingerprints must match foundation for identical natural/original inputs. No altered masks/ground truth or historical metrics copied instead of replay.

Actual activation counts require nonzero applied delta_a AND changed published velocity, not merely a median or a retained recovery offset. Per variant >=10 qualifying effective entry episodes in>=3 source groups and>=100 applied model-only ticks on natural+original suite. Report groups with and without reference separately. Same foundation threshold, now checked against actual interventions. Coverage failure => INCONCLUSIVE for that variant.

Admission requires every R3 rule: >=2% clean OR>=5% original-fault group-macro RMSE gain; clean/fault/pooled regression<=.5%, distance<=1%; clean bag/receiver<=baseline+max(.005m/s,5%baseline). Equal schedule/n/coverage/reference masks; no new false stops, individual unrecovered, causal errors or resets. At baseline zero use absolute tolerance1e-6m/s, never divide by zero. Missing required evidence prevents admission. Among passing variants choose minimum original fault RMSE then clean RMSE then smaller lag; otherwise no validation. If passed, publish separate FREEZE commit before validation. No hidden validation trigger is installed now.

## Separate fixed safety and counterexample suites

These never replace original gain. Every family must have event-macro error<=baseline*1.005 (baseline zero tolerance1e-6m/s), no new per-case false stops/unrecovered or causal/reset/mask errors. Show all individual/regression cases and activation, even if aggregate passes.

1. Existing low-speed lock selector transcribed unchanged from PR13 source f10e3cfc0689ecbd7894575945897a6696db3e72 tools/research_lock/low_speed.py: first grid point valid,abs(front-rear)<.15,mean wheels strictly1..2m/s,u>=0,t>max(25,.1*end),t<end-25; lock3/5s;20s warmup,10.1s tail. Apply to development membership only.
2. Existing v8 abrupt common-mode suite uses baseline tools/research_h11/compare.py common_fault_windows/inject_common unchanged: +5m/s both wheels,.7/1.2s, its original first vehicle-only anchor. Official scorer receives pre-injected streams, native observers see only ordinary samples.
3. Command-transition loss: first eligible grid transition to each new mode(-1,0,+1) with old mode distinct, t>25 and t<end-15, valid agreeing moving wheels>1. Drop both wheels5s starting .3s after transition. Warmup20s; current command mode/history fallback remains active. No reference-error-driven anchor.
4. Common slow wheel drift: at each original first anchor, add a fixed linear common drift over the preceding2s, slopes +.15/- .15m/s², then original both-wheel dropout5s. Return pristine wheel stream after dropout; reference unchanged. Separate family from abrupt common jumps.
5. Genuine load change / late correct update: deterministic synthetic plant with exactly the baseline force/drag/actuator and bounds, dt=.05, wheels10Hz/controller20Hz, initialv=2,command=.2, no sensor noise. True load changes at30s by +.3 or-.3m/s²; both-wheel dropout starts30.7s (genuine_load) or30.4s (late_update), lasts5s, ends before45s stream end. True plant velocity is only external synthetic reference, never an algorithm input beyond permitted wheel samples. Ground-truth physical load is known ONLY in this ideal counterexample, not in real bags. Native evolution initializes from past warmup, not future velocity. Fixed four cases, no tuning from them.

If these reveal stale checkpoints trading away recent genuine dynamics, record the failure, do not change the rule. Analytical/synthetic outcomes do not prove real-data gain.

## Execution, traces, CPU and publication

Before/through/after traces at every original fault tick for both variants and baseline; compressed artifact only. Natural activation episodes and per-bag/group/receiver/fault metrics compact in Git; no raw bags or giant JSON duplication. Logs/source/threshold/data hashes included.

Unit/build/integrity: all-original-state and off equality, causal prefix, future/duplicate/stale/reset/count+TTL bounds, clipping, valid recovery, zero-lock/quarantine, distance continuity, actual target replacement. No historical release guards edited.

CPU: one fixed development prefix120s of30618_0652866c and the lexicographically first original development fault replay with an eligible0.4s foundation entry (chosen by activation, not candidate error). For each lag3AB/BA pairs, fixed threads1 and same original replay array collector. Exclude initial10s from replay/step timers, measure CPU and wall separately, no correctness/traces instrumentation in timed path. Do not call process RSS node RSS or schedule20Hz wall latency. If accuracy fails, enabled installed ROS benchmark is NOT_RUN_AFTER_REJECTION. If accuracy passes, enabled installed ROS replay under2CPU/500000000bytes in both clocks with real parameter/import checks is mandatory before any merge readiness.

Final flags separately, draft PR39 only. Main/other research branches/old evidence untouched; merge and auto-merge prohibited. Literature and local oracle scope remain as recorded in SOURCES.md.

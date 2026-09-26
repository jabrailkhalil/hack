# R3-H31 / R3-v8-fixed — prospective PLAN

Baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024, actual GuardedReadoutObserver,
champion_v8.yaml, returned Estimate.v/s, readout(1,.5), inner adaptation .5,
wheel_time_compensation=0, common_mode_quarantine=1.5, 20Hz/delay0.
No main updates, old report/hash edits, merge, automatic validation, or test IO.

## Premise BEFORE algorithm

Baseline-only probe source 88776624962c0ae68959ab5015ce7d042475e98e,
Actions 36220305076/1, artifact10899227293 SHA256
65506514d55691a538b6390437f4a580cf7f698f2c0b98228449831990278496.
64 original train bags /27 groups: 17,511 completed non-overlapping 1s forecasts
(spacing>=2s) in25groups. Endpoint RMSE vs trusted wheel pseudolabel=.160311594634m/s,
p95 absolute=.246153121041m/s;559 errors>.3m/s. Braking RMSE=.215450551360,
coast=.142137565543, traction=.0929531263625. Not ground truth and not independent
17,511 trips. 42,083 nonhealthy MODEL_ONLY ticks are only an upper bound on
potential scope; these include disagreement/marginal freshness, not just true
outages. Actual both-missing activation will be measured separately.
No alternative forecast/selector comparison yet. Development streams were
transported losslessly with original role/hash/topic/order metadata, not scored
or inspected for candidate selection; train transport contains no GNSS.
H15/H16/H17 full reports read. In particular small aggregate benefits do not erase
transition/coast/group/distance regressions. Different best parameters by group
do not identify one physical law.

## Single candidate, no fitting/search

One causal ensemble, fixed internal bank (not three validation candidates):
1. Original v8 commanded physics; healthy virtual prediction uses an independent
   deepcopy of canonical observer, receives subsequent commands ONLY.
2. Constant published velocity at launch.
3. Constant clipped net acceleration a0=drive_a-resistance(inner_v)+disturbance,
   integrated only for first1s, then constant velocity. All members clip speed
   to baseline max_speed and forbid numerical reversal on braking/coasting.
All physical coefficients are exactly YAML values. No GNSS, fault labels,
file/group IDs, endpoint initialization, new Q/R, or future command use.

Launch one virtual bank from CURRENT canonical state on trusted data, no more
than once/2s. Horizon EXACTLY1s, max one pending bank; retain its endpoint forecast
without further integration after horizon. Endpoint pseudo-target is linear
interpolation of two consecutive already-received trusted wheel-pair endpoints
bracketing that horizon, gap<=max_age=.25s, scored only after later endpoint
arrives, no more than .25s grace. Endpoints require BOTH wheel timestamps advance,
mean is not two independent sensors. Start state NEVER modified by target.
Healthy held pair: fresh channels, skew<=.05s, difference<=.15m/s, statuses only
ACCEPTED/DUPLICATE_OR_OLD, valid command, |v|>.5m/s, no initialization/stop/reacquire.
A loss of health cancels pending prediction/target bracket, never fabricates a score.

Regime is traction/coast/braking by existing deadband PLUS a command epoch:
a change in sign-class or |u-u_epoch|>.2 invalidates completed scores and pending
bank. Stale command invalidates applicability immediately. These conditions
are runtime-observable, not true unknown changes in load.

Scores: last at most8 completed triplets, age<=20s. A usable selector needs>=3
completed records, newest<=4s old, EVERY completion stamp strictly<trigger.
Each record holds launch/end/completion stamps and3 losses. Loss sigma=.4m/s
=wheel_sigma + .5*disturbance_limit*1s, rho=min(4,2*(hypot(1,error/sigma)-1)).
L_i is unweighted mean of retained losses. Priors=(.5,.25,.25), temperature=1.
q_i=prior_i*exp(-L_i)/sum(prior_j*exp(-L_j));
w=(.25,0,0)+.75*q. Nonnegative sum1; physics weight>=.25.
The rule and scales above are fixed before candidate measurements; no training
optimizer or recalibration. No retrospective best-model switch in runtime.

## Outage-only published correction; canonical state stays exact

Apply only when canonical mode MODEL_ONLY and BOTH wheel statuses are
MISSING_OR_STALE. Ordinary duplicate prediction ticks are not outages. Never
activate during zero-lock suspect, quarantine (t<reacquire_blocked_until),
STOPPED or REACQUIRING. Freeze usable scores and weights at first eligible
outage tick; init alternative velocities from PREVIOUS canonical published
Estimate, not a future/returning wheel. Physical member is current canonical
published v, driven by commands as they actually arrive. Net a0 from the prior
canonical state. Use min(h,1s) for constant-acceleration member. Weights never
learn from missing/suspicious wheel readings.

Short applicability: full correction until1s from first outage tick, linearly
taper to canonical over1..2s, zero new forecast correction after2s. Change of
command epoch, stale command, stop/reacquire/quarantine revokes weights for the
rest of that outage. Missing-channel fallback targets canonical, not any
untrusted wheel. Rate-limit toward target during missing MODEL_ONLY using
intersection of speed bound, |extra delta_v|<=.6m/s and previous published
velocity +/-max_accel*dt. If intersection unexpectedly empty, veto and immediate
canonical fallback; count it. Enforce no sign reversal in braking/coast.
At any nonmissing/guarded/measurement-correction tick output v is exactly
canonical; these discrete sensor/guard transitions take precedence over the
outage-only rate limiter and are logged separately (no global smoothness claim).

delta_s += .5*(previous_delta_v+new_delta_v)*dt on ALL initialized steps,
including recovery. Never erase delta_s on recovery. Explicit reset can clear
auxiliary state. Published a=base.a+(delta_v-delta_v_previous)/dt, uncertainty
adds conservative delta envelopes, not calibrated CI. Internal canonical
variables AND base.last_estimate stay exactly untouched; wrapper.last_estimate
is the published output. This is composition, not mutation of legacy core.

## Data and measurement

Premise: all64 train, vehicle-only; no fit/check reallocation or GNSS fitting.
Main comparison: ALL17 original development bags/all7 groups; both references.
Baseline independently executes canonical v8; H31-off exact comparison and
per-tick equality of candidate.base with an independent canonical object,
including base.last_estimate. Profile/source/split/data hashes checked.
Use unchanged evaluate.score/replay/match/metrics/distance and v6.summary;
only factory/role/transport adapters added. Original fault_windows unchanged.
Legacy scorer aliases renamed only AFTER score. Per-bag, receiver, fault,
group, MAE/bias/p95/recovery/missingness and all material regressions saved.
NPZ transport arrays must reproduce original inputs exactly; hashes bind them
to original checksummed SQLite and role journals. Scoring works on either raw
role-safe source or transported arrays. No resampling or masks change.

One nonselcted equal-weight(1/3) diagnostic control on development, with SAME
eligibility, timing and guards, not a second validation candidate. Optional
posthoc oracle only as diagnostic lower bound from already-recorded member
outputs, never used by runtime or for parameter choice. It cannot authorize gain.

Separate mandatory safety suites: existing low-speed anchors and lock3/5s from
champion_v7/LOW_SPEED_REPORT; existing h11.common_fault_windows/.7/1.2s+5m/s,
same injection function. Each suite event-macro regression<=.5%, no new stops
or individual unrecovered. Preserve original suites and thresholds exactly.
Additional regime-transition dropout diagnostics: first traction->coast and
coast->brake transitions per bag after25s/before end-25s, based on vehicle data;
start dropout exactly at transition, duration5s, warmup20s/recovery10s. Their
aggregate event regression<=.5% and no new stops/unrecovered is a safety veto;
gain never substitutes original admission.

## Prospective coverage and admission

Coverage: >=100 completed forecasts in>=3 source groups; original fault suite
>=5 distinct (bag,anchor) eligible outage contexts from>=3 source groups,
>=100 effective |delta_v|>1e-6 ticks; >=2 groups with GNSS among altered original
contexts. Repeated durations and two receivers are NOT independent episodes.
Insufficient coverage -> INCONCLUSIVE, never expand suite or lower thresholds.

Only one frozen candidate can reach validation, only if ALL pass:
>=2% clean OR >=5% original fault macro gain; no >.5% clean/fault/pooled growth;
<=1% scalar-distance growth; every clean RMSE<=base+max(.005,5%base); same n,
coverage/timestamps/masks; no new per-case false-stops/unrecovered/causal/resets;
separate low/common/transition safety gates; tests and coverage pass.
Baseline zero uses absolute tolerance1e-12 instead of division. No validation
when development fails. Classification: insufficient coverage INCONCLUSIVE;
adequately covered variant failing gain/safety REJECTED. Not a family verdict.
Freeze must be separate published commit before validation IO. No automated
push-trigger validation in any workflow. Historical validation not independent.
Final test never opened. Existing baseline faults are not allowance to add new ones.

## Tests, cost, mathematical assumptions

Off equality, inner equality every tick, source pins, prefix, future/duplicate,
NaN/stale/reset, strict completion-before-trigger, endpoint isolation, no rescore,
record/time/count bounds, convex weights, distance persistence/derivative.
Synthetic mandatory cases: command acceleration/braking changes exactly with
wheel loss; hidden +/-load change same command at loss (no observability claim);
false common pair on return; genuine stop; zero-lock; long dropout/stale command.
For commanded regime-switch/guard cases require exact canonical speed once
fallback takes effect; uncommanded changes require no new false stop/nonrecovery
and event RMSE<=base*1.005+1e-12. No changes to candidate after dev results.

CPU step and replay separately: first120s firstdevelopment bag,10s warmup,
5 measured AB/BA pairs; exact same held tape/output collector and threads1.
Also a matching first-original-dropout tape so healthy learning cost and outage
cost are both visible. Benchmark excludes off-equivalence/audit wrappers.
Runtime stores one canonical plus<=one virtual canonical,<=8 score triplets,
one target predecessor, scalars and fixed-key saturated counters. No growing log
inside observer. Full traces compressed artifacts30d, not giant Git JSON.

Wolfram checked convex bounds and Jensen identity. Pointwise convex mixture is
not guaranteed better than BEST member. Frozen weights preserve derivative
bounds only when member bounds and identical weights apply; hard transitions
need separate treatment. Unknown acceleration gives CV error=-a*h and distance
error=-a*h^2/2; past scores do not predict unobserved regime changes. Pseudolabel
and interpolation assumptions are not a GNSS-independent truth guarantee.
JMLR Herbster/Warmuth2001 abstract read as expert-tracking context only. Known
Consensus30/Scite25 monthly quota stop respected: no new calls, no fulltext or
citation-context claim. Worksheets/actual outputs and source-depth saved.

## Execution/publication

Commands planned: probe.py --export (already run); tests.py; run.py --stage
baseline/train/development/cost --output fresh --streams exported_root
(or original --data-root). Source commit/hashes pinned BEFORE real comparison.
Conditional freeze/validation only after admission; enabled installed ROS both
clock modes offline2CPU/500000000B only after accuracy pass. Otherwise
NOT_RUN_AFTER_REJECTION/INCONCLUSIVE, never inherit canonical CI's certificate.
Report/SUMMARY statuses: mechanism_status,coverage_status,scientific_verdict,
accuracy_contract_passed,runtime_verified,ready_to_merge. Compact evidence in
Git; large traces/logs compressed artifact; no raw bags committed. One Russian
Draft PR R3-H31 with explicit negative/incomplete label when appropriate.

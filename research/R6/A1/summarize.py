from forensic import *
HERE=Path(__file__).resolve().parent
m=json.loads((HERE/'A1_CAUSAL_MATRIX.json').read_text());runs={r['control']:r for r in m['controls']}
a=np.load(OUT/'A0_TRACE.npz',allow_pickle=True);cl=np.load(OUT/'A0/CLEAN_TRACE.npz',allow_pickle=True);t=a['t'];delta=a['s']-cl['s'];i0=np.flatnonzero(t<START)[-1];ie=int(np.argmin(abs(t-END)))
p={'definition':'Anchor fault/end contributions at output t=74.55 inclusive; injection itself remains half-open in SOURCE event time [71.55,74.55).','fault_contribution_m':float(delta[ie]-delta[i0]),'post_fault_contribution_m':float(delta[-1]-delta[ie]),'total_m':float(delta[-1]),'first_saturation_t':float(t[np.flatnonzero(abs(a['v'])>=40-1e-9)[0]]),'first_zero_reject_t':float(t[np.flatnonzero((t>=END)&(a['front_status']=='ZERO_LOCK_SUSPECT'))[0]]),'first_returned_new_pair_t':float(t[np.flatnonzero((t>=END)&np.array([x is not None and x>=END for x in a['front_t']])&np.array([x is not None and x>=END for x in a['rear_t']]))[0]])}
write(HERE/'PHASE_ACCOUNTING.json',p)
for name in ('D','Z','DZ'):
 b=np.load(OUT/(name+'_TRACE.npz'),allow_pickle=True);pre=t<runs[name]['trigger']
 for k in ('v','s','inner_v','d','drive_a','pv','mode','front_status','rear_status'):assert np.array_equal(a[k][pre],b[k][pre]),(name,k)
 assert np.array_equal(t,b['t'])
 # No discontinuous s reset: published increments equal trapezoidal v.
 res=np.diff(b['s'])-.5*(b['v'][1:]+b['v'][:-1])*np.diff(t)
 assert max(abs(res))<1e-8
 assert np.array_equal(b['v'][t>t[-1]-60],cl['v'][t>t[-1]-60])
write(HERE/'ORACLE_INTEGRITY.json',{'same_preintervention_trajectory_all_controls':True,'same_output_timestamps':True,'no_position_reset_integral_identity':True,'canonical_step_restored_after_each_oracle':True,'terminal60_velocity_exact_clean_all_oracles':True,'Z_changes_only_zero_pair_branch':'forensic.py run(): in-memory exec replacement, original method restored in finally; d changed only by canonical adaptation/STOPPED','D_changes_only_disturbance':'one-shot before first qualified return step; no other direct state edit'})
trans=[]
for i in range(len(t)):
 if i==0 or a['mode'][i]!=a['mode'][i-1] or (abs(a['v'][i])>=40-1e-9)!=(abs(a['v'][i-1])>=40-1e-9):trans.append({'t':t[i],'mode':a['mode'][i],'v':a['v'][i],'d':a['d'][i],'saturated':abs(a['v'][i])>=40-1e-9})
csvwrite(HERE/'STATE_TRANSITIONS.csv',trans)
# State machine first point after which no acceptance returns, observed retrospectively.
post=(t>=END);accepted=np.isin(a['front_status'],['ACCEPTED','REACQUIRE_ACCEPTED'])|np.isin(a['rear_status'],['ACCEPTED','REACQUIRE_ACCEPTED'])
last=float(t[np.flatnonzero(accepted)[-1]])
write(HERE/'TIMELINE_LANDMARKS.json',dict(fault_start=START,fault_end=END,first_returned_pair=p['first_returned_new_pair_t'],first_zero_reject=p['first_zero_reject_t'],stable_oracle_trigger=75.55,first_saturation=p['first_saturation_t'],last_accepted_any_channel=last,post_fault_accepted_samples=int(sum(accepted&post)),terminal=float(t[-1]),no_recovery_from_return_through_bag_end=True))
table='\n'.join(f"| {r['control']} | {r['D_canonical']} | {r['ZERO_LOCK_canonical']} | {r['runaway']} | {r['recovery']} | {r['terminal_delta_s_m']:.12f} | {r['saturated_time_s']:.2f} |" for r in m['controls'])
horiz='\n'.join(f"| {r['control']} | {x['horizon']} | {x['delta_v']:.9f} | {x['delta_s']:.9f} | {x['d']:.9f} | {x['mode']} |" for r in m['controls'] for x in r['horizons'] if x['horizon'] in (1,5,10,30,60,120,300,'terminal'))
report=f'''# R6-A1 — independent causal forensic re-audit

**{m['status']}** — confirmed self-locking computational mechanism in this
single recorded diagnostic scenario. Returning pair: **RETURNING_PAIR_AMBIGUOUS**
with respect to physical wheel lock, despite passing observable quality checks.
No production fix, tuning, refit or new accuracy claim. STOP after this report.

## Identity and independent reproduction

Canonical {BASE}, tree{TREE}, 320files/modes verified; complete champion_v8.yaml,
unchanged GuardedReadoutObserver and Timeline,20Hz/delay0. One train-check DB:
{BAG}, group0d4506540f0e7621, label30639, event{CID}; injected both-wheel dropout
[71.55,74.55) by original source timestamps. Source/arrival order and units are
unchanged. A0 ZIP/receipt and all43 packaged payloads/input hashes verified.
No GNSS/teacher/development/validation/test measurements. H52 is closed and
untouched; no warmup experiment. Prior A1 reports remain immutable.

New canonical and clean traces exactly equal frozen FD2 t/v/s/clean_v/clean_s.
Untouched replay independently equals instrumented replay at every tick in t/v/s/
inner_v/d. Terminal internal delta_s=41424.813387721915m. It is not official XYZ
error or proven actual tram position error. Integral residual<=5.03e-9m,
max one-step contribution approximately2m, no huge timestep or position reset.

Using output at t=74.55 as fault-end boundary: fault contribution
{p['fault_contribution_m']:.12f}m; after fault {p['post_fault_contribution_m']:.12f}m.
A half-open output-tick split at t<74.55 instead assigns the final .05s step to
recovery and gives -0.125916706201m / +41424.93930442812m; this is boundary
accounting, not a changed injector or discrepant total. Primary uses the original
A0 endpoint convention, saved in PHASE_ACCOUNTING.json.

## Causal sequence and same-raw counterfactual

At fault end model v=0.234006285m/s and d=+0.6m/s². The first returned pair is
available at74.65s, source stamps74.612932064, both exactly0. Predicted v has
reached0.270730517m/s, beyond stop_model_speed_mps0.25. Both fresh candidate
samples are rejected as ZERO_LOCK_SUSPECT. Same normalized Sample bytes and
same time, paired-clean pre-step state: predicted0,d0, both ACCEPTED/STOPPED.
This is SELF_LOCKING_EVIDENCE=TRUE: identical input, different internal state,
different trust decision. It uses no future sample or reference. Raw-byte hash
in the counterfactual is for the normalized Sample tuple; original CDR/input
provenance is separately locked by DB and ordered event-array hashes.

ZERO_LOCK is a hard failure for reacquisition, clears its evidence, and does
not enqueue the rejected pair as MODEL_DISAGREEMENT. Adaptation requires FUSED
and |wheel z|>.5; stop reset requires predicted speed<.25 and .5s dwell. Thus
these zeros cannot lower model speed or reach STOPPED, and d cannot adapt away.
Canonical accepts no returning wheels before bag end. d remains+0.6; inner and
published speed eventually reach40m/s (first146.65s). Total post-fault time at
saturation is920.25s; long integration, not one tick, produces41.4km. Final60s
counterfactual distance slope36.50299324m/s; clean motion means delta slope need
not equal40m/s. MODEL_ONLY ticks in a recovered control can mean normal held
DUPLICATE_OR_OLD input ticks, not continued loss of recovery.

## Returning-pair quality and oracle boundary

Fresh/finite/range/skew/agreement/command checks pass. Nine distinct source
stamps per wheel occur before the stable trigger75.55s. Pre-model gate statuses
are CANDIDATE or held DUPLICATE_OR_OLD, no RATE_ANOMALY/RANGE. Held duplicates
sustain continuity but are not re-assimilated. All qualifying stamps follow
fault end; no future sample/injection-active tick is used. Persistence uses
existing canonical0.8s dwell, not a tuned time. Source-time persistence and
separate distinct-channel stamp counts are retained.

This is still **AMBIGUOUS physical evidence**: both wheel sensors could share a
real lock. We do not rename it trusted truth. Oracle results are conditional
on accepting this observationally qualified returning pair. They prove the
observer's computational feedback mechanism and ways to cut it; they do not
prove physical standstill or safety of an accept-zero production rule.

## Fixed causal matrix

| Run | D canonical | ZERO_LOCK canonical | Runaway | Recovery | Terminal delta_s m | Saturation s |
|---|---|---|---|---|---:|---:|
{table}

D intervenes once at75.55: only d:=0. The canonical zero gate remains active
while model speed decays; first FUSED at83.95 (end+9.40s), STOPPED84.45
(end+9.90s). Z changes only ZERO_LOCK branch eligibility on stable qualified
pairs, not innovation/rate gates or d. First FUSED75.55 (end+1s); d is still+.6
on that tick. STOPPED76.10 (end+1.55s) then resets d through the existing canonical
stop path. DZ is similarly FUSED75.55/STOPPED76.10. No s reset in any control.
Post-return rejected new samples: canonical23722,D144,Z16,DZ16, counted per
channel; held duplicates excluded. All three controls have exact clean velocity
in the final60s and only an enduring bounded s offset. A1-S is NOT_RUN because
recovery occurs before saturation in all three controls; saturation is downstream.

| Run | Horizon after end s | delta_v m/s | delta_s m | d | mode |
|---|---|---:|---:|---:|---|
{horiz}

## Necessary versus sufficient — precise scope

Within this fixed trajectory and intervention timing, retained disturbance and
the zero-rejection feedback are both contextual causes: removing either breaks
the observed runaway path. D-only and Z-only are each sufficient interventions
to restore recovery. Their combination is not necessary to remove runaway.
Keeping D canonical under Z does not sustain runaway; keeping ZERO_LOCK
canonical under D does not sustain runaway. Neither factor alone has been shown
universally sufficient for failure. Universal necessity/sufficiency and a
minimal causal model cannot be identified from one bag and these three controls.

The required single verdict is ZERO_REACQUISITION under the preregistered tie
policy, because Z restores acceptance and the same-raw self-lock test passes.
It is NOT a claim that D is irrelevant, that Z is the only sufficient cut, or
that this is COUPLED in the special sense 'only DZ works'. H_D/H_Z as claims of
standalone sufficient failure causes are not established; 'only DZ fixes it'
is disproved here. No global dominance ranking is claimed.

## Alternatives and infrastructure

Timestamp jump, duplicate event, future sample, broken dt, overflow, NaN/Inf,
integrator arithmetic, position reset mismatch, readout-only artifact, injection
past its end, wrong clean pairing, saturation logging and future counterfactual
information: PASS/excluded at the level of this locked replay (details in
A1_ALTERNATIVE_CAUSES.json). Legitimate held duplicate statuses exist and are
not duplicated assimilation. Inactive -inf state deadlines are not NaN/Inf
numeric-trajectory defects. No synthetic schedule or coordinate reference is used.

UPSTREAM_METRIC_INFRASTRUCTURE_RISK=FALSE. H58/H59/H60 MAY CONTINUE.

## One proposal, not implemented

Controlled persistent zero-wheel reacquisition, with explicit safeguards for
true common wheel lock. No thresholds chosen, no B01 implementation, no production
file changes. The remaining narrow safety question is how causal runtime evidence
can distinguish a real standstill return from common wheel lock; this forensic
experiment does not resolve that physical observability problem.

## Reproduction and export

PLAN16b7a6d; instrumentation c69fd6e in branch research/R6-A1-recovery-causality.
Run forensic.py for A0, run_causal.py for the fixed controls, summarize.py for
audits/report. Source is isolated under research/R6/A1, in-memory oracle method
restored after each run. DEPENDENCIES.lock binds the exact local/Drive inputs.
Output archive contains reports, all tick traces, code/logs and hashes, not
canonical source/dataset/H42/H43. CHAT EXPORT is an artifact export, not a
claimed byte-complete transcript. Previous A1 is preserved as history.
'''
(HERE/'A1_REPORT.md').write_text(report)
print(m['status'])

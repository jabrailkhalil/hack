"""Read-only analysis of completed H61 evidence; never calls a predictor."""
from pathlib import Path
import json,csv,hashlib,subprocess,platform
import numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'reports/research_R6/H61';CODE=Path(__file__).parent
def load(n):return json.loads((OUT/n).read_text())
def write(n,x):(OUT/n).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def main():
 s=load('SUMMARY.json');full=load('FULL_OPTIMIZATION.json');folds=load('FOLD_OPTIMIZATIONS.json');freeze=load('ALL_FITS_FREEZE.json');rep=load('OBJECTIVE_REPRODUCTION.json');integ=load('INTEGRITY.json')
 ledger=[json.loads(l) for l in (OUT/'CALL_LEDGER.jsonl').read_text().splitlines()];results=[json.loads(l) for l in (OUT/'CALL_RESULTS.jsonl').read_text().splitlines()]
 assert len(ledger)==len(results)==s['actual_evaluations']<=832
 assert [r['call'] for r in ledger]==list(range(1,len(ledger)+1))
 assert len([r for r in ledger if r['label'].startswith('line_')])==21
 assert all(r['call']>freeze['calls_before_any_heldout'] for r in ledger if '_heldout' in r['context'])
 fdefs=json.loads((CODE/'FOLDS.json').read_text())['folds'];contract=json.loads((ROOT/'.h61_inputs/h54/OBJECTIVE_CONTRACT.json').read_text());den={g['group']:g['denominator'] for g in contract['groups']}
 raw_errors=[]
 for row,result in zip(ledger,results):
  assert row['call']==result['call'] and row['x']==result['x']
  if row['context'].startswith('fold'):
   f=int(row['context'][4]);expected=fdefs[f]['heldout_groups' if row['context'].endswith('_heldout') else 'train_groups'];assert row['groups']==expected
  with np.load(OUT/'evidence'/f"call_{row['call']:04d}.npz",allow_pickle=False) as z:
   for field,key in [('prediction','prediction_hash'),('six','six_hash'),('losses','loss_hash'),('residual','residual_hash')]:assert hashlib.sha256(np.asarray(z[field],dtype='<f8').tobytes()).hexdigest()==result[key]
   losses=z['losses'];rat=losses/np.array([den[g] for g in row['groups']]);np.testing.assert_array_equal(rat,z['ratios'])
   k=(len(rat)+1)//2;prior=0 if row['context'].endswith('_heldout') else .01*np.mean(np.array(row['x'])**2)
   expected=.5*np.mean(rat)+.5*np.mean(np.sort(rat)[-k:])+prior;raw_errors.append(abs(expected-result['J1']))
 assert max(raw_errors)<1e-12
 test_counts={}
 for name,n in [('CANONICAL_TESTS.log',161),('INTEGRITY_TESTS.log',43),('H61_TESTS.log',10)]:
  text=(OUT/name).read_text();assert f'Ran {n} tests' in text and text.rstrip().endswith('OK');test_counts[name]=n
 table=list(csv.DictReader((OUT/'HELDOUT_TRANSFER.csv').open()));scan=list(csv.DictReader((OUT/'LINE_SCAN.csv').open()));scan_min=min(scan,key=lambda r:float(r['J1']))
 transfer_table='\n'.join(f"| {r['fold']} | {float(r['baseline_H']):.12f} | {float(r['optimized_H']):.12f} | {float(r['gain_pct']):+.6f}% | {folds[int(r['fold'])]['nfev']} | {folds[int(r['fold'])]['success']} |" for r in table)
 stability_table='\n'.join(f"| {p} | {lo:.10g} | {hi:.10g} |" for p,lo,hi in zip(['F/m','P/m','B/m'],s['theta_min'],s['theta_max']))
 ledger_counts={context:sum(r['context']==context for r in ledger) for context in sorted({r['context'] for r in ledger})}
 active_sets={}
 for context in ledger_counts:
  rr=[r for r in results if r['context']==context];sets=[set(r['active_top_half_groups']) for r in rr]
  active_sets[context]={'calls':len(rr),'consecutive_membership_changes':sum(x!=y for x,y in zip(sets,sets[1:])),'inclusion_count':{g:sum(g in x for x in sets) for g in rr[0]['groups']},'final_groups':rr[-1]['active_top_half_groups']}
 write('ACTIVE_SET_STABILITY.json',active_sets)
 write('POST_AUDIT_VERIFICATION.json',{'all_saved_arrays_fingerprint_verified':True,'heldout_after_all_fit_freezes':True,'subset_isolation_verified':True,'independent_objective_max_delta':max(raw_errors),'test_counts':test_counts,'physical_calls_by_context':ledger_counts,'no_extra_physical_calls_for_report':True})
 s['tests_passed']=sum(test_counts.values());s['claim_verified']=True;s['objective_reproduction']='PASS';s['branch']='research/R6-H61';s['plan_commit']='d77b7ea';s['execution_code_commit']='63b86d8';s['line_min_diagnostic_only']={'alpha':float(scan_min['alpha']),'J1':float(scan_min['J1'])};write('SUMMARY.json',s)
 report=f'''# R6-H61 — train-only optimization audit

**{s['status']}**. This is an optimization audit, not an accuracy candidate.
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
{max(raw_errors):.3g}. Each call stores predictions/residuals/losses and fingerprints.

## A — reproduction

Baseline J1: **{s['baseline_J1']:.16f}**; frozen C0 witness:
**{s['C0_J1']:.16f}**. Both repeat calls are byte-identical in prediction,
six-residual, group loss and full residual fingerprints. Gate A PASS.

## B — fixed line scan

Exactly 21 alpha=i/20 points between baseline and C0 in log-space, with passive
branch/clipping counters in LINE_SCAN.csv and per-window evidence. Both endpoint
fingerprints equal the uninstrumented reproduction calls. Minimum on this
diagnostic line: alpha={float(scan_min['alpha']):.2f}, J1={float(scan_min['J1']):.16f}.
This point is not a selected start or optimizer result. Every Powell starts at zero.

## C — single full-fit Powell

method=Powell; x=log(theta/theta0); bounds from H54 [.05,1,.05]..[5,100,5];
x0=zeros(3), xtol=1e-6, ftol=1e-8, maxfev=130. No restarts or alternative solver.
Returned J1: **{s['full_J1']:.16f}**; gain **{s['full_gain_pct']:.6f}%**.
Returned theta: {full['theta']}. Evaluations {full['nfev']};
solver success={full['success']}; termination: {full['message']}.
The returned point is retained even if another evaluated point is better.
Gate B ({s['gates']['B']}): J1<=.9920 AND J1<=J1(C0)+1e-4.
Two final physical repeats exactly verify the returned point. A budget exit is
reported as such; neither a global optimum nor numerical convergence is claimed.

## D — five-fold group transfer within train-fit

Groups sorted lexicographically; fold=index mod5, frozen before optimization.
Each optimizer receives only 12 training groups and the same fixed settings.
All five returned points are frozen before any held-out score is evaluated.
Held-out triples use data-only H with their actual recomputed baseline; no prior.

| Fold | Baseline H | Returned H | Gain | Powell calls | Solver success |
|---|---:|---:|---:|---:|---|
{transfer_table}

Improved: **{s['heldout_improved']}/5**; median gain
**{s['median_heldout_gain_pct']:.6f}%**; worst regression
**{s['worst_heldout_regression_pct']:.6f}%**. Gate C={s['gates']['C']}.
These folds are inside train-fit; they are not the historical train-check split.
They also are not untouched external evidence: H54's fixed normalizers and prior
protocol already exist. The result measures transfer of this fixed procedure,
not unbiased official accuracy. No fold was selected or removed.

## Parameter stability — descriptive only

| Parameter | Minimum across fold fits | Maximum across fold fits |
|---|---:|---:|
{stability_table}

Maximum pairwise log-parameter distance: {s['max_fold_log_distance']:.8f}.
Full pairwise distances, fold standard deviations and distance to each bound
are saved. Active worst-half groups are retained in every call and final repeat.
ACTIVE_SET_STABILITY.json records consecutive membership changes and group
inclusion counts by context; these are diagnostic counts, not frequency estimates.
None of these diagnostics changes starts, solver, gates or reported fits.

## Integrity, budget and conclusion

Gate D PASS: finite outputs, bounds, repeat fingerprints, exact windows and
subset coverage, independent objective arithmetic and frozen dependencies.
214 tests PASS (161 canonical, 43 research-integrity, 10 H61). Call ledger and
saved evidence match: **{s['actual_evaluations']} physical aggregate evaluations**,
hard cap 900; no cached evaluations hidden from accounting. Physical objective
wall time {s['physical_seconds']:.2f} s. One process, native Apple Silicon,
Python {platform.python_version()}, NumPy {np.__version__}; thread limits one.
Only Stage B uses detailed passive tracing. No unused-budget exploration.

Gates: {s['gates']}. Final status: **{s['status']}**.
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
'''
 (OUT/'REPORT.md').write_text(report)
 write('DELIVERY.json',{'hypothesis':'R6-H61','status':s['status'],'workspace':'https://drive.google.com/drive/folders/19S0NiATO_hsIIdu2wkFqdgkeE1wY7yWW','branch':'research/R6-H61','plan':'d77b7ea','execution_code':'63b86d8','claim_preserved':True,'accuracy_candidate':False,'forbidden_data_opened':False,'required_outputs_complete':True})
 (OUT/'CHAT_EXPORT.md').write_text('# H61 chat export / scoped handoff\n\nThis is a task-and-result record, not a verbatim export of unrelated prior chats.\nThe complete frozen user task is preserved in research/R6/H61/PROMPT.md.\n\n'+report)
 print(json.dumps(s,indent=2))
if __name__=='__main__':main()

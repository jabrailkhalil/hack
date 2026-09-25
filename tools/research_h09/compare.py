"""H09 paired development/validation runner; final-test access is not implemented.

The pinned evaluator is used unchanged. Only Observer construction is dispatched
by the configuration class, selecting exact baseline or materialized H09 code.
Additional low-speed diagnostics never replace the common v6 acceptance metrics.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/research_h09'), str(ROOT/'tools/finalization'),
               str(ROOT/'tools/research_v6'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
from candidate import BASELINE, implementations, sha, baseline_bytes, load_module
v6 = load_module("h09_v6_aggregation", ROOT/"tools/research_v6/compare.py")
from export_bags import decode

np, ex = ev.np, ev.ex
PREREGISTRATION = 'ef1e94de68ef74cc37dcd0eadf5e355c34137f0d'
LOCK = ROOT/'research/parallel/H09/EVALUATOR_LOCK.json'
OPS = dict(rate_hz=20., alignment_delay_s=0.)
BASE, CAND = 'baseline_v2', 'balanced_physics'
PROTECTED = ['tools/finalization/evaluate.py', 'tools/research_v3/experiment.py',
             'tools/research_v3/manifest.py', 'tools/export_bags.py',
             'tools/research_v6/compare.py', 'research/plan_v3.json',
             'research/split_v3.json', 'src/reserve_odometry/config/adaptive_v5.json',
             'src/reserve_odometry/config/adaptive_v5.yaml',
             'src/reserve_odometry/config/default.yaml',
             'src/reserve_odometry/reserve_odometry/core.py',
             'src/reserve_odometry/reserve_odometry/timeline.py']


def source_state(baseline_root):
    lock = json.loads(LOCK.read_text())
    if lock['baseline_commit'] != BASELINE: raise ValueError('Wrong evaluator lock')
    for path in PROTECTED:
        original = hashlib.sha256(baseline_bytes(path, baseline_root)).hexdigest()
        if sha(ROOT/path) != original or original != lock['sha256'][path]:
            raise ValueError('Evaluator/config/split changed: '+path)
    frozen, candidate, hashes = implementations(baseline_root)
    params = json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
    models = {BASE:frozen.Config(**params), CAND:candidate.Config(**params)}
    if asdict(models[BASE]) != asdict(models[CAND]): raise ValueError('Physical config differs')
    ev.Observer = lambda c: frozen.Observer(c) if type(c) is frozen.Config else candidate.Observer(c)
    hashes.update(evaluator_lock_sha256=sha(LOCK), runner_sha256=sha(__file__),
                  loader_sha256=sha(ROOT/'tools/research_h09/candidate.py'))
    return models, hashes


class DevelopmentStore(ex.Store):
    """Membership, topics and digest checked before read-only development IO."""
    def load(self, bag, purpose):
        if purpose != 'development': return super().load(bag,purpose)
        row = self.records[bag]
        if row['split'] != 'development' or bag not in self.plan['splits']['development']:
            raise PermissionError('Not development: '+bag)
        path = self.root/bag/(bag+'_0.db3')
        if ex.digest(path) != row['sha256']: raise ValueError('DB checksum mismatch')
        allowed = list(ex.CHANNELS)+list(ex.REFS)
        self.access.append(dict(bag=bag,group=row['group'],purpose=purpose,topics=allowed,sha256=row['sha256']))
        events=[]; refs={'master':[],'rover':[]}
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                   'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=decode(raw,typ); t=(stamp-row['sensor_start_ns'])/1e9
                if topic in ex.CHANNELS:
                    ch=ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float).reshape(-1,3),refs


class ExportStore(DevelopmentStore):
    """Verified development-only export, with original DB provenance retained."""
    def __init__(self, inputs):
        super().__init__(); self.inputs=inputs
        self.export_provenance=json.loads((inputs/'provenance.json').read_text())
        if self.export_provenance['baseline'] != BASELINE: raise ValueError('Wrong export baseline')
        self.entries={r['bag']:r for r in json.loads((inputs/'access.json').read_text())}
        if set(self.entries) != set(self.plan['splits']['development']):
            raise ValueError('Export development membership differs')

    def load(self,bag,purpose):
        if purpose != 'development' or self.records[bag]['split'] != purpose:
            raise PermissionError('Export is development only')
        row=self.entries[bag]; path=self.inputs/'development'/(bag+'.npz')
        if (row['purpose'] != purpose or row['sha256'] != self.records[bag]['sha256'] or
            row['topics'] != list(ex.CHANNELS)+list(ex.REFS) or sha(path) != row['export_sha256']):
            raise ValueError('Export integrity failure')
        self.access.append(row)
        with np.load(path,allow_pickle=False) as data:
            events=data['events'].copy()
            refs={r:data[r].tolist() for r in ('master','rover')}
        return events,refs


def diagnostic(a, target, fault=None):
    t=a[:,0]; mask=np.isfinite(target)
    if fault: mask &= (t>=fault['start']) & (t<fault['end']+10.)
    stopped=a[:,5]>0
    result=dict(slow_reference_samples=int(np.sum(mask&(target>.07)&(target<=.5))),
        slow_reference_stop_samples=int(np.sum(mask&(target>.07)&(target<=.5)&stopped)),
        medium_reference_stop_samples=int(np.sum(mask&(target>.5)&(target<=1.)&stopped)),
        low_reference_spans=[], low_reference_span_seconds=0., low_reference_odometry_abs_m=0.)
    if len(t)<2 or fault:return result
    low=mask&(target<=.03)
    edge=low[:-1]&low[1:]&(np.diff(t)<=.051)
    starts=np.flatnonzero(edge&np.r_[True,~edge[:-1]])
    ends=np.flatnonzero(edge&np.r_[~edge[1:],True])+1
    for begin,end in zip(starts,ends):
        duration=float(t[end]-t[begin])
        if duration<1.:continue
        distance=float(np.sum(np.abs(np.diff(a[begin:end+1,2]))))
        result['low_reference_span_seconds']+=duration
        result['low_reference_odometry_abs_m']+=distance
        later=np.flatnonzero(mask & (t>t[end]) & (t<=t[end]+5.) & (target>.07))
        delay=None
        if len(later):
            start=later[0]
            released=np.flatnonzero((np.arange(len(t))>=start)&~stopped)
            if len(released):delay=float(t[released[0]]-t[start])
        result['low_reference_spans'].append(dict(start_s=float(t[begin]),end_s=float(t[end]),
            duration_s=duration,odometry_abs_m=distance,departure_stop_release_s=delay))
    return result


def evaluate_case(events, refs, models, output, label, fault=None):
    row=ev.score(events,refs,models,OPS,fault)
    arrays={}; diagnostics={}; costs={}
    # A second identical replay retains traces and supplementary diagnostics;
    # common score() and its masks are never edited or replaced.
    for name,config in models.items():
        started=time.perf_counter(); a,_=ev.replay(events,config,OPS,fault)
        costs[name]=dict(offline_replay_s=time.perf_counter()-started,outputs=len(a))
        arrays[name]=a
    if not np.array_equal(arrays[BASE][:,0],arrays[CAND][:,0]):
        raise AssertionError('Exact output timestamps differ')
    if len(arrays[BASE]):
        for receiver,values in refs.items():
            target=ex.match(values,arrays[BASE][:,0]); arrays['reference_'+receiver]=target
            mask=np.isfinite(target)
            if fault:mask &= (arrays[BASE][:,0]>=fault['start'])&(arrays[BASE][:,0]<fault['end']+10.)
            arrays['mask_'+receiver]=mask
            diagnostics[receiver]={}
            for name in models:
                reproduced=ex.metrics(arrays[name][:,0],arrays[name][:,1],target,mask)
                scored=row['receivers'][receiver][name]
                for key in ('n','coverage','rmse'):
                    a,b=reproduced[key],scored[key]
                    if a != b and (a is None or b is None or abs(a-b)>1e-12):
                        raise AssertionError('Supplementary replay differs from evaluator')
                diagnostics[receiver][name]=diagnostic(arrays[name],target,fault)
    trace=output/'traces'/(label+'.npz');trace.parent.mkdir(exist_ok=True)
    np.savez_compressed(trace,**arrays)
    row.update(h09_diagnostics=diagnostics,offline_cost=costs,trace_sha256=sha(trace))
    return row


def summarize(clean,stress):
    sums={name:v6.summary(clean,stress,name) for name in (BASE,CAND)}
    reasons=[];missing=[];b,c=sums[BASE],sums[CAND]
    for key in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse'):
        if b[key] is None or c[key] is None:
            missing.append(key); continue
        change=c[key]/b[key]-1 if b[key] else (0. if c[key]==0 else math.inf)
        c[key+'_change']=change if math.isfinite(change) else 'positive_infinity'
        if change>(.01 if key=='distance_rmse' else .005):reasons.append('aggregate_regression:'+key)
    if not missing and not (c['clean_rmse']<=b['clean_rmse']*.98 or c['fault_rmse']<=b['fault_rmse']*.95):
        reasons.append('insufficient_common_gain')
    if c['unrecovered']>b['unrecovered']:reasons.append('unrecovered_increase')
    for row in clean:
        for receiver,metrics in row['receivers'].items():
            a,z=metrics[CAND],metrics[BASE]
            if z['rmse'] is not None and (a['rmse'] is None or a['rmse']>z['rmse']+max(.005,.05*z['rmse'])):
                reasons.append('per_bag_clean_regression:'+row['bag']+'/'+receiver)
    diag_totals={name:dict(low_reference_odometry_abs_m=0.,low_reference_span_seconds=0.,
                 slow_reference_stop_samples=0,medium_reference_stop_samples=0,low_reference_spans=0)
                 for name in (BASE,CAND)}
    for row in clean+stress:
        if row['runtime'][CAND]['causal_errors'] or row['runtime'][CAND]['resets']:
            reasons.append('causality_or_reset:'+row['bag'])
        for receiver,metrics in row['receivers'].items():
            a,z=metrics[CAND],metrics[BASE]
            if a['n']!=z['n'] or a['coverage']!=z['coverage']:reasons.append('coverage:'+row['bag']+'/'+receiver)
            if a.get('false_stop_samples',0)>z.get('false_stop_samples',0):reasons.append('false_stops:'+row['bag']+'/'+receiver)
        for receiver,metrics in row['h09_diagnostics'].items():
            for key in ('slow_reference_stop_samples','medium_reference_stop_samples'):
                if metrics[CAND][key]>metrics[BASE][key]:reasons.append(key+':'+row['bag']+'/'+receiver)
            for name,m in metrics.items():
                for key in diag_totals[name]:
                    diag_totals[name][key]+=len(m[key]) if key=='low_reference_spans' else m[key]
    if not diag_totals[BASE]['low_reference_spans']:missing.append('no_low_reference_spans')
    elif diag_totals[CAND]['low_reference_odometry_abs_m']>=diag_totals[BASE]['low_reference_odometry_abs_m']:
        reasons.append('no_stop_distance_proxy_gain')
    safety=[r for r in reasons if r!='insufficient_common_gain' and r!='no_stop_distance_proxy_gain']
    return dict(common=sums,h09=diag_totals,rejection_reasons=sorted(set(reasons)),
        missing_evidence=missing,development_safety_passed=not safety,
        eligible_by_measured_gates=not reasons and not missing,
        independent_true_stop_labels=False,independent_final_test=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['development','validation'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-root',type=Path)
    parser.add_argument('--inputs',type=Path,help='Verified development-only export directory')
    parser.add_argument('--freeze',type=Path)
    args=parser.parse_args()
    models,hashes=source_state(args.baseline_root)
    if args.stage=='validation':
        if not args.freeze:raise PermissionError('Commit a candidate freeze before validation')
        frozen=json.loads(args.freeze.read_text())
        if frozen['candidate_hashes']!=hashes or frozen['baseline_commit']!=BASELINE:
            raise ValueError('Candidate changed after freeze')
        if not frozen.get('development_safety_passed'):raise PermissionError('Development gate failed')
    if args.inputs and args.stage!='development':raise PermissionError('Development export cannot serve validation')
    args.output.mkdir(parents=True,exist_ok=False)
    store=ExportStore(args.inputs) if args.inputs else DevelopmentStore()
    started=time.perf_counter()
    provenance=dict(baseline_commit=BASELINE,preregistration_commit=PREREGISTRATION,stage=args.stage,
        hashes=hashes,common_evaluator_sha256=json.loads(LOCK.read_text())['sha256'],
        operational=OPS,model_parameters=asdict(models[BASE]),python=platform.python_version(),
        numpy=np.__version__,platform=platform.platform(),source_ref=os.environ.get('GITHUB_SHA','local'),
        final_test_opened=False,export_provenance=getattr(store,'export_provenance',None))
    ev.save(args.output/'started.json',provenance)
    clean=[];stress=[]
    for bag in store.plan['splits'][args.stage]:
        events,refs=store.load(bag,args.stage)
        ev.save(args.output/'access.json',store.access)
        row=evaluate_case(events,refs,models,args.output,bag)
        row.update(bag=bag,group=store.records[bag]['group'],
                   input_array_sha256=hashlib.sha256(events.tobytes()).hexdigest())
        clean.append(row)
        grid=ex.grid_channels(events)
        if grid is not None:
            t,u,f,r,valid=grid
            indices=np.flatnonzero(valid&((f+r)/2>2.)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25.))
            if len(indices):
                anchor=float(t[indices[0]])
                for kind,duration in [('bias',5.),('dropout',5.),('dropout',10.),('lock',3.)]:
                    fault=dict(kind=kind,start=anchor,end=anchor+duration)
                    window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
                    item=evaluate_case(window,refs,models,args.output,bag+'-'+kind+'-'+str(duration),fault)
                    item.update(bag=bag,group=store.records[bag]['group'],fault=fault);stress.append(item)
        ev.save(args.output/'per_bag'/(bag+'.json'),dict(clean=row,stress=[r for r in stress if r['bag']==bag]))
        print('completed',bag,flush=True)
    _,after=source_state(args.baseline_root)
    if after!=hashes:raise ValueError('Candidate changed during evaluation')
    result=dict(provenance=provenance,clean=clean,stress=stress,access=store.access,
                elapsed_s=time.perf_counter()-started,final_test_opened=False)
    ev.save(args.output/'results.json',result)
    decision=summarize(clean,stress);decision.update(stage=args.stage,bags=len(clean),
        groups=len(set(r['group'] for r in clean)),fault_scenarios=len(stress),results_sha256=sha(args.output/'results.json'))
    ev.save(args.output/'decision.json',decision)
    print(json.dumps(decision,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()

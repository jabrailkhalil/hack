"""One frozen H30 candidate, all development groups, unchanged official scorer.

Validation is intentionally not implemented: a separate published freeze and
explicit later authorization are required after every prospective R3 gate.
"""
import argparse, collections, copy, csv, datetime, hashlib, importlib.util, json, os, platform, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import common as cm
from common import np
from factory import candidate

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
v6=module('h30_fixed_v6_scoring',cm.ROOT/'tools/research_v6/compare.py')
h11=module('h30_fixed_h11_windows',cm.ROOT/'tools/research_h11/compare.py')
NAMES=('baseline_v8','H30_joint_native','feature_off')

def neutral(v):
    from dataclasses import is_dataclass,asdict
    if is_dataclass(v):return asdict(v)
    if isinstance(v,(tuple,list)):return [neutral(x) for x in v]
    if isinstance(v,dict):return {k:neutral(x) for k,x in v.items()}
    return v

class CheckedOff:
    def __init__(self):self.on=candidate(False);self.ref=cm.baseline();self.checked=0
    def __getattr__(self,k):return getattr(self.on,k)
    def reset(self):self.on.reset();self.ref.reset();self.checked=0
    def step(self,*args):
        out=self.on.step(*args);ref=self.ref.step(*args)
        if neutral(out)!=neutral(ref):raise AssertionError('Feature-off Estimate differs')
        for k,v in vars(self.ref).items():
            if neutral(v)!=neutral(getattr(self.on,k)):raise AssertionError('Feature-off state differs: '+k)
        self.checked+=1;return out

def pair(events,refs,fault=None):
    observers={'baseline_v2':cm.baseline(),'balanced_physics':candidate(),'feature_off':CheckedOff()}
    configs={name:o.c for name,o in observers.items()}
    by_config={id(configs[n]):observers[n] for n in observers}
    arrays={};old_obs,old_replay=cm.ev.Observer,cm.ev.replay
    def recording(e,c,ops,f=None):
        a,r=old_replay(e,c,ops,f)
        arrays[id(c)]=(a,r)
        return a,r
    try:
        cm.ev.Observer=lambda c:by_config[id(c)]
        cm.ev.replay=recording  # transparent collector, executes the original unchanged function
        result=cm.ev.score(events,refs,configs,cm.OPS,fault)
    finally:cm.ev.Observer,cm.ev.replay=old_obs,old_replay
    b,br=arrays[id(configs['baseline_v2'])];off,ofr=arrays[id(configs['feature_off'])]
    if not np.array_equal(b,off,equal_nan=True) or br!=ofr:raise AssertionError('Disabled replay not exact')
    c,cr=arrays[id(configs['balanced_physics'])]
    if b.shape!=c.shape or not np.array_equal(b[:,0],c[:,0]):raise AssertionError('Exact output schedule mismatch')
    for r in (br,ofr,cr):
        if r['causal_errors'] or r['resets']:raise AssertionError('Causality/reset veto')
    schedule=hashlib.sha256(b[:,0].tobytes()).hexdigest()
    masks={}
    for recv,values in refs.items():
        target=cm.ev.ex.match(values,b[:,0]);mask=np.isfinite(target)
        if fault:mask&=(b[:,0]>=fault['start'])&(b[:,0]<fault['end']+10.)
        masks[recv]=hashlib.sha256(mask.tobytes()).hexdigest()
    for src,dst in [('baseline_v2',NAMES[0]),('balanced_physics',NAMES[1])]:
        result['runtime'][dst]=result['runtime'].pop(src)
        for values in result['receivers'].values():values[dst]=values.pop(src)
    result['audit']=dict(schedule_sha256=schedule,reference_masks_sha256=masks,
      baseline_array_sha256=hashlib.sha256(b.tobytes()).hexdigest(),
      candidate_array_sha256=hashlib.sha256(c.tobytes()).hexdigest(),
      feature_off_exact=True,feature_off_checked_ticks=observers['feature_off'].checked,
      max_output_velocity_difference=float(np.max(abs(c[:,1]-b[:,1]))) if len(b) else None,
      changed_outputs=int(np.sum(abs(c[:,1]-b[:,1])>1e-9)))
    result['activation']=dict(observers['balanced_physics']._h30_stats)
    return result

def low_windows(events):
    # Exact published PR13 low_speed.py predicate at f10e3cfc, reused on DEVELOPMENT.
    grid=cm.ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2) & (u>=0)
                      & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            yield dict(kind='lock',start=anchor,end=anchor+duration),events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]

def worker(arg):
    bag,output=arg;events,refs,group=cm.load(bag,output/'access'/(bag+'.json'),reference=True)
    meta=dict(bag=bag,group=group,role='development')
    clean=dict(**meta,**pair(events,refs));stress=[];low=[];common=[]
    for f,w in cm.legacy.fault_windows(events):stress.append(dict(**meta,fault=f,**pair(w,refs,f)))
    for f,w in low_windows(events):low.append(dict(**meta,fault=f,**pair(w,refs,f)))
    for f,w in h11.common_fault_windows(events):
        # Official replay ignores unknown common_bias kind; only the external
        # immutable H11 injection changes input values. Same changed events for all.
        changed=h11.inject_common(w,f)
        common.append(dict(**meta,fault=f,**pair(changed,refs,f)))
    data=dict(clean=clean,original=stress,low_speed=low,common_mode=common)
    cm.save(output/'bags'/(bag+'.json'),data)
    print(bag,'native',clean['activation']['native_updates'],'material',clean['activation']['material_updates'],flush=True)
    return data

def identity(row,receiver):
    return dict(bag=row['bag'],group=row['group'],receiver=receiver,fault=row.get('fault'))

def aggregate_rows(rows):
    return {n:dict(event_rmse=v6.macro(rows,n,'event_rmse'),window_rmse=v6.macro(rows,n,'rmse'),
       false_stops=v6.total(rows,n,'false_stop_samples'),unrecovered=v6.unrecovered(rows,n)) for n in NAMES[:2]}

def decide(clean,stress,extras):
    # Only technical legacy labels, all point to actual measured full v8/H30.
    # v4_default also aliases v8; historical selected/fallback name is NOT used.
    ac,af=copy.deepcopy(clean),copy.deepcopy(stress)
    for row in ac+af:
        row['runtime']['v5_adaptive_05s']=row['runtime'][NAMES[0]]
        row['runtime']['v4_default']=row['runtime'][NAMES[0]]
        for scores in row['receivers'].values():
            scores['v5_adaptive_05s']=scores[NAMES[0]];scores['v4_default']=scores[NAMES[0]]
    legacy=v6.decide(ac,af,['v4_default','v5_adaptive_05s',NAMES[1]])['candidates'][NAMES[1]]
    reasons=list(legacy['rejection_reasons']);violations=[]
    stats={n:v6.summary(clean,stress,n) for n in NAMES[:2]}
    b,c=stats[NAMES[0]],stats[NAMES[1]]
    if c['pooled_rmse']>b['pooled_rmse']*1.005:reasons.append('pooled_regression')
    for suite,rows in [('clean',clean),('original',stress),*extras.items()]:
        for row in rows:
            for receiver,scores in row['receivers'].items():
                bm,cm_=scores[NAMES[0]],scores[NAMES[1]]
                checks=[]
                if bm['n']!=cm_['n'] or bm['coverage']!=cm_['coverage']:checks.append('coverage')
                if cm_['false_stop_samples']>bm['false_stop_samples']:checks.append('new_false_stop')
                if bm.get('event_rmse') is not None and bm.get('recovery_s') is not None and cm_.get('recovery_s') is None:checks.append('new_individual_unrecovered')
                if checks:
                    violations.append(dict(suite=suite,**identity(row,receiver),violations=checks))
                    reasons.extend(suite+':'+x for x in checks)
    extra_summary={}
    for suite,rows in extras.items():
        s=aggregate_rows(rows);extra_summary[suite]=s;x,y=s[NAMES[0]],s[NAMES[1]]
        if x['event_rmse'] is None or y['event_rmse'] is None:reasons.append(suite+':missing_reference')
        elif y['event_rmse']>x['event_rmse']*1.005:reasons.append(suite+':event_regression')
    activation=collections.Counter();bygroup=collections.Counter()
    for row in clean:
        activation.update({k:v for k,v in row['activation'].items() if not k.startswith('max_')})
        bygroup[row['group']]+=row['activation']['material_updates']
    for k in ('max_states','max_events','max_input_events'):
        activation[k]=max(r['activation'][k] for r in clean+stress+sum(extras.values(),[]))
    coverage=(activation['material_updates']>=1000 and sum(v>=100 for v in bygroup.values())>=3 and activation['past_tick_updates']>=100)
    if not coverage:reasons.append('insufficient_mechanism_coverage')
    return dict(summary=stats,additional_suites=extra_summary,legacy_candidate_decision=legacy,
      contract_reasons=sorted(set(reasons)),individual_violations=violations,
      activation=dict(activation),material_updates_by_group=dict(bygroup),
      mechanism_status='IMPLEMENTED_AND_SANITY_TESTED',coverage_status='SUFFICIENT' if coverage else 'INSUFFICIENT',
      scientific_verdict=('REJECTED' if coverage else 'INCONCLUSIVE') if reasons else 'DEVELOPMENT_ADMITTED',
      accuracy_contract_passed=not reasons,development_admitted=not reasons,
      validation_status='NOT_RUN_AFTER_REJECTION' if reasons else 'AWAITING_PUBLISHED_FREEZE',
      validation_opened=False,freeze_sha=None,final_test_opened=False,
      runtime_verified=False,enabled_ros_status='NOT_RUN_AFTER_REJECTION' if reasons else 'REQUIRED',ready_to_merge=False)

def export(clean,stress,extras,output):
    records=[]
    for suite,rows in [('clean',clean),('original',stress),*extras.items()]:
        for row in rows:
            for recv,scores in row['receivers'].items():
                for n in NAMES[:2]:
                    m=scores[n];f=row.get('fault',{})
                    rec=dict(suite=suite,bag=row['bag'],group=row['group'],receiver=recv,model=n,
                      kind=f.get('kind'),duration_s=f.get('end',0)-f.get('start',0),start_s=f.get('start'),
                      **{k:m.get(k) for k in ('n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples')},
                      distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m'))
                    records.append(rec)
    with (output/'per_bag_receiver_fault.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    group_rows=[]
    for suite,rows in [('clean',clean),('original',stress),*extras.items()]:
        for g in sorted(set(r['group'] for r in rows)):
            subset=[r for r in rows if r['group']==g]
            for n in NAMES[:2]:group_rows.append(dict(suite=suite,group=g,model=n,
                **{k:v6.macro(subset,n,k) for k in ('rmse','mae','bias','event_rmse','distance')},
                false_stops=v6.total(subset,n,'false_stop_samples'),unrecovered=v6.unrecovered(subset,n)))
    cm.save(output/'per_group.json',group_rows)

class Timer:
    def __init__(self,obs):self.obs=obs;self.step_ns=0;self.calls=0
    def __getattr__(self,k):return getattr(self.obs,k)
    def reset(self):self.obs.reset();self.step_ns=0;self.calls=0
    def step(self,*args):
        start=time.process_time_ns();out=self.obs.step(*args);self.step_ns+=time.process_time_ns()-start;self.calls+=1;return out

def cost(output):
    bag=cm.ev.ex.Store().plan['splits']['development'][0]
    events,_,_=cm.load(bag,output/'cost-access.json',reference=False)
    rows=[]
    for repeat in range(-1,6):
        order=NAMES[:2] if repeat%2==0 else NAMES[1::-1]
        for name in order:
            obs=Timer(cm.baseline() if name==NAMES[0] else candidate())
            cpu,wall=time.process_time_ns(),time.perf_counter_ns();arr,info=cm.predict(events,obs)
            cpu,wall=time.process_time_ns()-cpu,time.perf_counter_ns()-wall
            if repeat>=0:rows.append(dict(repeat=repeat,model=name,step_cpu_ns=obs.step_ns,step_calls=obs.calls,
                replay_cpu_ns=cpu,replay_wall_ns=wall,outputs=len(arr),output_sha256=hashlib.sha256(arr.tobytes()).hexdigest()))
    summary={}
    for metric in ('step_cpu_ns','replay_cpu_ns','replay_wall_ns'):
        ratios=[]
        for j in range(6):
            x={r['model']:r[metric] for r in rows if r['repeat']==j};ratios.append(x[NAMES[1]]/x[NAMES[0]]-1)
        summary[metric+'_median_paired_overhead']=float(np.median(ratios))
    for name in NAMES[:2]:
        if len(set(r['output_sha256'] for r in rows if r['model']==name))!=1:raise AssertionError('Cost non-deterministic output')
    cm.save(output/'COST.json',dict(bag=bag,warmup_pairs=1,measured_pairs=6,order='AB/BA alternating',
       threads={k:os.getenv(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
       summary=summary,measurements=rows,qualification='Offline Python CPU/wall, not installed ROS latency/RSS'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['development'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2);args=p.parse_args()
    if not 1<=args.workers<=4:raise ValueError('Invalid workers')
    args.output.mkdir(parents=True,exist_ok=False);cm.verify()
    files=list(cm.HERE.glob('*.py'))+list((cm.HERE/'tests').glob('*.py'))+[cm.HERE/'PLAN.md',cm.HERE/'BASELINE.json']
    files +=[cm.ROOT/'tools/research_h11/compare.py',cm.ROOT/'reports/champion_v7/LOW_SPEED_REPORT.md']
    hashes={str(f.relative_to(cm.ROOT)):cm.sha(f) for f in files}
    cm.save(args.output/'STARTED.json',dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
       source_sha=os.getenv('GITHUB_SHA','local-working-copy'),baseline_sha=cm.BASELINE,role='development',
       source_hashes=hashes,pinned_source=cm.verify(),python=platform.python_version(),numpy=np.__version__,validation_opened=False))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows=list(pool.map(worker,[(b,args.output) for b in cm.ev.ex.Store().plan['splits']['development']]))
    clean=[r['clean'] for r in rows];stress=[s for r in rows for s in r['original']]
    extras={name:[s for r in rows for s in r[name]] for name in ('low_speed','common_mode')}
    result=decide(clean,stress,extras)
    result['counts']=dict(bags=len(clean),groups=len(set(r['group'] for r in clean)),original_faults=len(stress),
       low_speed_faults=len(extras['low_speed']),common_mode_faults=len(extras['common_mode']),
       feature_off_checked_ticks=sum(r['audit']['feature_off_checked_ticks'] for r in clean+stress+sum(extras.values(),[])))
    cm.save(args.output/'SUMMARY.json',result);export(clean,stress,extras,args.output);cost(args.output)
    if hashes!={path:cm.sha(cm.ROOT/path) for path in hashes}:raise AssertionError('Source changed during development')
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()

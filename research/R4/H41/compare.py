"""H41 paired development with unchanged official scorer and aggregation.

Only the observer factory and separate passive collectors change. Validation
and final-test have no CLI stage. Large traces are gzip, not Git payloads.
"""
from __future__ import annotations
import argparse
import ast
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import foundation as f
import runtime
import numpy as np
ev=f.ev
BASE='baseline_v2';CAND='balanced_physics';OFF='h41_off'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

v6=load('_h41_summary_v6',f.ROOT/'tools/research_v6/compare.py')
guarded=load('_h41_guarded_windows',f.ROOT/'tools/research_guarded/compare.py')
_previous_compare=sys.modules.get('compare')
sys.modules['compare']=guarded
try:h11=load('_h41_h11_windows',f.ROOT/'tools/research_h11/compare.py')
finally:
    if _previous_compare is None:sys.modules.pop('compare',None)
    else:sys.modules['compare']=_previous_compare
original_windows=guarded.fault_windows


def low_speed_windows(events):
    """Reuse the exact pinned low-speed selection expression (role adapter only)."""
    p=Path(__file__).with_name('vendor')/'low_speed_original.py';raw=p.read_bytes()
    if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!='7705f88fbcdfab49a8531dadffaa8e35e996f25c':
        raise ValueError('Pinned low-speed source mismatch')
    fn=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='run_bag')
    select=next(n.value for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='idx' for t in n.targets))
    duration_node=next(n.iter for n in ast.walk(fn) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='duration')
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,front,rear,valid=grid
    idx=eval(compile(ast.Expression(select),str(p),'eval'),{'np':np,'abs':abs,'max':max},dict(t=t,u=u,f=front,r=rear,valid=valid))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in ast.literal_eval(duration_node):
            yield dict(kind='lock',start=anchor,end=anchor+duration),events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


class Capture:
    """External collector; no information is supplied to the estimator."""
    def __init__(self,inner):self.inner=inner;self.reset()
    def __getattr__(self,key):return getattr(self.inner,key)
    def reset(self,*args,**kwargs):
        self.inner.reset(*args,**kwargs)
        self.ticks=0;self.nonzero=0;self.trace=[];self.model_only=[];self.fused=[]
    def step(self,*args,**kwargs):
        e=self.inner.step(*args,**kwargs);o=self.inner
        if e.mode!='WAITING_FOR_INITIALIZATION':
            self.model_only.append(e.mode=='MODEL_ONLY');self.fused.append(e.mode=='FUSED')
            self.nonzero+=int(abs(getattr(o,'h41_delta_a',0.))>1e-12)
            if getattr(o,'h41_enabled',False):
                if o.pv*o.h41_paa-o.h41_pva**2 < -1e-10:raise AssertionError('non-PSD runtime covariance')
            if self.ticks%20==0:
                self.trace.append(dict(t=e.t,v=e.v,s=e.s,inner_v=o.v,drive_a=o.drive_a,d=o.disturbance,
                    pv=o.pv,pva=getattr(o,'h41_pva',None),paa=getattr(o,'h41_paa',None),
                    kv=getattr(o,'h41_kv',None),ka=getattr(o,'h41_ka',None),a_model=getattr(o,'h41_a_model',None),
                    mode=e.mode,front=e.front_status,rear=e.rear_status))
            self.ticks+=1
        return e


def score(events,refs,baseline_only=False,fault=None,full=False,trace_path=None):
    c,r=f.profile();cc=f.Config(**asdict(c));oc=f.Config(**asdict(c))
    models={BASE:c,CAND:cc}
    if not baseline_only and not full:models[OFF]=oc
    made={};pred={};old_factory,old_replay=ev.Observer,ev.replay
    def factory(config):
        if config is c or baseline_only:inner=f.GuardedReadoutObserver(config,readout=r)
        else:inner=runtime.candidate_class()(config,readout=r,enabled=config is not oc)
        probe=Capture(inner);made[id(config)]=probe;return probe
    def capturing_replay(events,config,ops,fault=None):
        array,info=old_replay(events,config,ops,fault)
        pred[id(config)]=array;return array,info
    try:
        ev.Observer=factory;ev.replay=capturing_replay
        result=ev.score(events,refs,models,f.OPS,fault)
    finally:ev.Observer=old_factory;ev.replay=old_replay
    a,b=pred[id(cc)],pred[id(c)]
    if a.shape!=b.shape or not np.array_equal(a[:,0],b[:,0]):raise AssertionError('Exact schedule mismatch')
    if OFF in models:
        if not np.array_equal(pred[id(oc)],b,equal_nan=True) or result['runtime'][OFF]!=result['runtime'][BASE]:
            raise AssertionError('Disabled canonical mismatch')
    if baseline_only and (not np.array_equal(a,b,equal_nan=True) or result['runtime'][CAND]!=result['runtime'][BASE]):
        raise AssertionError('Canonical replication mismatch')
    changed=np.abs(a[:,1]-b[:,1])>1e-12
    result['activation']=dict(nonzero_actuator_corrections=made[id(cc)].nonzero,
        changed_published_ticks=int(changed.sum()),
        changed_model_only_ticks=int(np.sum(changed & np.asarray(made[id(cc)].model_only,bool))))
    if full:
        for recv,values in refs.items():
            target=ev.ex.match(values,b[:,0])
            for name,config in models.items():
                result['receivers'][recv][name]['distance_surrogate']=ev.distance_surrogate(pred[id(config)],target)
        post=(a[:,0]>=fault['end']) & np.asarray(made[id(cc)].fused,bool)
        hits=np.flatnonzero(post);j=int(hits[0]) if len(hits) else None
        result['distance_residual']=dict(delta_s_bag_end_m=float(a[-1,2]-b[-1,2]),
            first_fused_after_end_s=float(a[j,0]) if j is not None else None,
            delta_s_first_fused_m=float(a[j,2]-b[j,2]) if j is not None else None,
            note='Candidate minus baseline, not ground truth; first FUSED is not confirmed reference recovery')
    if trace_path:
        trace_path.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(trace_path,'wt') as z:json.dump({name:made[id(cfg)].trace for name,cfg in models.items() if name!=OFF},z,separators=(',',':'),allow_nan=False)
    return result


def worker(args):
    bag,data_root,out,baseline_only=args;out=Path(out)
    store=f.Store(Path(data_root));events,refs=store.load(bag,'development')
    meta=dict(bag=bag,group=store.records[bag]['group'],role='development')
    rows={'clean':[],'original':[],'low_speed':[],'common_mode':[],'full_faulted':[]}
    def add(suite,tape,fault=None,full=False):
        tag=f"{suite}-{len(rows[suite])}"
        row=dict(**meta,suite=suite,fault=fault,**score(tape,refs,baseline_only,fault,full,
            None if baseline_only else out/'traces'/bag/(tag+'.json.gz')))
        rows[suite].append(row)
    add('clean',events)
    for fault,window in original_windows(events):
        add('original',window,fault)
        if not baseline_only:add('full_faulted',events,fault,True)
    if not baseline_only:
        for fault,window in low_speed_windows(events):add('low_speed',window,fault)
        for fault,window in h11.common_fault_windows(events):
            add('common_mode',h11.inject_common(window,fault),fault)
    payload=dict(rows=rows,access=store.access)
    ev.save(out/'bags'/(bag+'.json'),payload)
    print('BAG_DONE',bag,{k:len(v) for k,v in rows.items()},flush=True)
    return payload


def summaries(rows,name):
    s=v6.summary(rows['clean'],rows['original'],name)
    for suite in ('low_speed','common_mode','full_faulted'):
        s[suite+'_event_rmse']=v6.macro(rows[suite],name,'event_rmse')
        s[suite+'_unrecovered']=v6.unrecovered(rows[suite],name)
        s[suite+'_false_stops']=v6.total(rows[suite],name,'false_stop_samples')
    s['full_faulted_distance_rmse']=v6.macro(rows['full_faulted'],name,'distance')
    for suite in ('clean','original'):
        for metric in ('mae','bias','p95','recovery_s'):
            s[suite+'_'+metric]=v6.macro(rows[suite],name,metric)
    return s


def gate(rows):
    sb,sc=summaries(rows,BASE),summaries(rows,CAND);reasons=[]
    gains={k:(1.-sc[k]/sb[k]) if sb[k] else None for k in ('clean_rmse','fault_rmse')}
    if gains['clean_rmse']<.02 and gains['fault_rmse']<.05:reasons.append('insufficient_gain')
    for key,lim in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01),
        ('low_speed_event_rmse',.005),('common_mode_event_rmse',.005),('full_faulted_distance_rmse',.01)]:
        b,c=sb[key],sc[key]
        if b is None or c is None:reasons.append('missing_metric:'+key)
        elif c>b*(1.+lim)+ (1e-12 if b==0. else 0.):reasons.append('aggregate_regression:'+key)
    for suite,items in rows.items():
        for row in items:
            for name in (BASE,CAND):
                rt=row['runtime'][name]
                if rt['causal_errors'] or rt['resets']:reasons.append('causal_or_reset:'+suite+'/'+row['bag'])
            for recv,metrics in row['receivers'].items():
                b,c=metrics[BASE],metrics[CAND];key=suite+'/'+row['bag']+'/'+recv+'/'+str(row['fault'])
                if b['n']!=c['n'] or b['coverage']!=c['coverage']:reasons.append('coverage:'+key)
                if c.get('false_stop_samples',0)>b.get('false_stop_samples',0):reasons.append('added_false_stop:'+key)
                if b.get('recovery_s') is not None and c.get('recovery_s') is None:reasons.append('new_unrecovered:'+key)
                if suite=='clean' and b['rmse'] is not None and (c['rmse'] is None or c['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                    reasons.append('clean_bag_regression:'+key)
    acts=[r for k in ('clean','original') for r in rows[k]]
    corr=sum(r['activation']['nonzero_actuator_corrections'] for r in acts)
    corr_groups={r['group'] for r in acts if r['activation']['nonzero_actuator_corrections']}
    changed=sum(r['activation']['changed_published_ticks'] for r in acts)
    changed_groups={r['group'] for r in acts if r['activation']['changed_published_ticks']}
    ot=sum(r['activation']['changed_model_only_ticks'] for r in rows['original'])
    og={r['group'] for r in rows['original'] if r['activation']['changed_model_only_ticks']}
    coverage=dict(corrections=corr,correction_groups=len(corr_groups),changed_ticks=changed,
        changed_groups=len(changed_groups),original_model_only_ticks=ot,original_model_only_groups=len(og))
    sufficient=corr>=100 and len(corr_groups)>=3 and changed>=100 and len(changed_groups)>=3 and ot>=20 and len(og)>=2
    if not sufficient:reasons.append('insufficient_activation')
    return dict(baseline=sb,candidate=sc,gains_fraction=gains,coverage=coverage,coverage_sufficient=sufficient,
        numerical_reasons=sorted(set(reasons)),numerical_passed=not reasons,
        additional_synthetic_veto='see synthetic.json; any veto prohibits validation',validation_authorized=False)


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    manifest=f.check_source(args.source_receipt);cfg,read=f.profile()
    source_hashes={str(p.relative_to(f.ROOT)):f.sha(p) for p in Path(__file__).parent.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    ev.save(out/'started.json',dict(**manifest,stage=args.stage,source_sha=os.environ.get('H41_MEASURED_SHA','LOCAL_UNCOMMITTED'),
        new_source_hashes=source_hashes,config=asdict(cfg),readout=asdict(read),operational=f.OPS,
        actual_baseline_module_file=sys.modules[f.GuardedReadoutObserver.__module__].__file__,
        actual_candidate_module_file=None if args.stage=='baseline' else sys.modules[runtime.candidate_class().__module__].__file__,
        class_baseline='GuardedReadoutObserver',class_candidate=None if args.stage=='baseline' else 'VelocityActuatorObserver',
        python=platform.python_version(),numpy=np.__version__,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        test_opened=False,validation_opened=False))
    store=f.Store(args.data_root);rows={k:[] for k in ('clean','original','low_speed','common_mode','full_faulted')};access=[]
    start=time.perf_counter()
    jobs=[(bag,str(args.data_root),str(out),args.stage=='baseline') for bag in store.plan['splits']['development']]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for payload in pool.map(worker,jobs):
            for key,items in payload['rows'].items():rows[key].extend(items)
            access.extend(payload['access'])
            ev.save(out/'access.json',dict(access=access,test_opened=False,validation_opened=False))
    expected=dict(clean_rmse=.09266814298282507,fault_rmse=.2375486120563008,pooled_rmse=.1293056944774334,distance_rmse=5.310295004801444,samples=394221)
    actual=v6.summary(rows['clean'],rows['original'],BASE)
    deltas={k:abs(actual[k]-v) for k,v in expected.items()}
    reproduction=dict(expected=expected,actual=actual,max_absolute_delta=max(deltas.values()),passed=all(v<1e-10 for v in deltas.values()))
    ev.save(out/'baseline_reproduction.json',reproduction)
    if not reproduction['passed']:raise AssertionError('Baseline fingerprint mismatch')
    ev.save(out/'results.json',dict(rows=rows,elapsed_wall_s=time.perf_counter()-start,role='development',test_opened=False,validation_opened=False))
    decision=gate(rows) if args.stage=='development' else dict(baseline=actual,candidate_evaluated=False)
    ev.save(out/'decision.json',decision)
    print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=('baseline','development'),required=True)
    p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-receipt',type=Path);p.add_argument('--workers',type=int,default=2)
    args=p.parse_args()
    if not 1<=args.workers<=4:p.error('workers must be 1..4')
    run(args)

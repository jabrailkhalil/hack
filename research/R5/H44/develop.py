"""Fixed H44 development comparison, including full faulted recordings.

Uses original scorers and fault constructors, not teacher masks. No training,
validation or final-test entrypoint. Recording state never changes the Observer.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
import gzip
import json
import math
from pathlib import Path
import sys
import time
import csv
import numpy as np
from interface import ROOT, BASE, profile, PARAMETERS
from baseline_preflight import DevelopmentStore, source_integrity, sha, write, g, v6, ex, module
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver
h11=module('h44_original_h11','tools/research_h11/compare.py')
NAMES=('main','gnss','wheel')


def model_set(fit):
    cfg,readout,_=profile()
    models={'main':(partial(GuardedReadoutObserver,readout=readout),cfg)}
    lock=json.loads((fit/'FIT_LOCK.json').read_text())
    for name in ('gnss','wheel'):
        if sha(fit/(name+'.json'))!=lock['files'][name+'.json']:raise ValueError('Fitted artifact changed')
        data=json.loads((fit/(name+'.json')).read_text())
        if not data['success']:raise PermissionError('Solver failed; no candidate measurement')
        c=Config(**data['config'])
        if data['readout']!=asdict(readout):raise ValueError('Readout changed')
        if set(k for k in asdict(c) if getattr(c,k)!=getattr(cfg,k))-set(PARAMETERS):raise ValueError('Non-H44 parameter change')
        models[name]=(partial(GuardedReadoutObserver,readout=readout),c)
    return models


def low_windows(events):
    grid=ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid;v=(f+r)/2
    # Same original PR13 low-speed predicate, as pinned by previous R4 tests.
    ids=np.flatnonzero(valid&(v>1)&(v<2)&(u>=0)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25.))
    if len(ids):
        anchor=float(t[ids[0]])
        for duration in (3.,5.):
            fault=dict(kind='lock',start=anchor,end=anchor+duration)
            yield fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


class Recorder:
    def __init__(self, config, readout, fault):
        self.o=GuardedReadoutObserver(config,readout=readout);self.fault=fault;self.landmarks={};self.near=[]
    def __getattr__(self,n):return getattr(self.o,n)
    def reset(self,**kw):self.o.reset(**kw)
    def step(self,t,command=None,front=None,rear=None):
        e=self.o.step(t,command,front,rear)
        if e.mode=='WAITING_FOR_INITIALIZATION':return e
        state=dict(t=t,v=e.v,s=e.s,inner_v=self.o.v,drive_a=self.o.drive_a,disturbance=self.o.disturbance,
                   readout_v=self.o._velocity_correction,mode=e.mode,variance_v=e.variance_v)
        for label,bound in (('prefault',self.fault['start']),('end',self.fault['end']),('post10',self.fault['end']+10)):
            if t<=bound+1e-9:self.landmarks[label]=state
        self.landmarks['terminal']=state
        if self.fault['start']-3<=t<=self.fault['end']+10:
            self.near.append([t,e.v,e.s,self.o.v,self.o.drive_a,e.disturbance,self.o._velocity_correction])
        return e


def worker(args):
    bag,root,fit,out=args;out=Path(out);store=DevelopmentStore(root)
    events,refs=store.load(bag,'development');models=model_set(Path(fit));meta=dict(bag=bag,group=store.records[bag]['group'],role='development')
    clean=dict(**meta,**g.compare(events,refs,models))
    arrays={n:g.predict(events,m)[0] for n,m in models.items()}
    t=arrays['main'][:,0]
    for a in arrays.values():
        if not np.array_equal(a[:,0],t):raise AssertionError('Clean schedule mismatch')
    # Independent invocation of the original scorer for the baseline.
    previous=g.ev.Observer
    try:
        g.ev.Observer=models['main'][0]
        raw=g.ev.score(events,refs,{'baseline_v2':models['main'][1],'balanced_physics':models['main'][1]},g.OPS)
    finally:g.ev.Observer=previous
    for rec,s in clean['receivers'].items():
        m=raw['receivers'][rec]['baseline_v2']
        for k,v in s['main'].items():
            if m[k]!=v:raise AssertionError('Official baseline mismatch '+bag+':'+k)
    refbearing=any(s['main']['rmse'] is not None for s in clean['receivers'].values())
    activation={n:int(np.count_nonzero(np.abs(arrays[n][:,1]-arrays['main'][:,1])>1e-8)) for n in ('gnss','wheel')}
    np.savez_compressed(out/'traces'/(bag+'-clean.npz'),**arrays)
    cropped=[];full=[];states=[];lows=[];commons=[]
    for index,(fault,window) in enumerate(g.fault_windows(events)):
        cropped.append(dict(**meta,fault=fault,**g.compare(window,refs,models,fault)))
        predictions={};runtime={};recorders={}
        for name,(factory,cfg) in models.items():
            made=[]
            def recording(c):
                r=Recorder(c,profile()[1],fault);made.append(r);return r
            predictions[name],runtime[name]=g.predict(events,(recording,cfg),fault)
            recorders[name]=made[0]
            if not np.array_equal(predictions[name][:,0],t):raise AssertionError('Full fault schedule differs')
            before=t<fault['start']
            if not np.array_equal(predictions[name][before,:3],arrays[name][before,:3]):raise AssertionError('Fault affected prefault outputs')
        receivers={}
        for receiver,values in refs.items():
            target=ex.match(values,t);mask=np.isfinite(target);scores={}
            for name,a in predictions.items():
                m=ex.metrics(t,a[:,1],target,mask);m['distance_surrogate']=g.ev.distance_surrogate(a,target)
                m['false_stop_samples']=int(np.sum(mask&(target>1)&(a[:,5]>0)));scores[name]=m
            receivers[receiver]=scores
        full.append(dict(**meta,fault=fault,receivers=receivers,runtime=runtime))
        marks={}
        for name,a in predictions.items():
            marks[name]=dict(landmarks=recorders[name].landmarks,faulted_minus_clean={})
            for label,q in (('post10',fault['end']+10),('terminal',t[-1])):
                j=np.searchsorted(t,q+1e-9,side='right')-1
                if j>=0:marks[name]['faulted_minus_clean'][label]=dict(t=float(t[j]),delta_s=float(a[j,2]-arrays[name][j,2]))
        states.append(dict(bag=bag,group=meta['group'],fault=fault,models=marks))
        np.savez_compressed(out/'traces'/(bag+'-fault'+str(index)+'.npz'),**predictions,
                            **{n+'_state_near':np.asarray(r.near) for n,r in recorders.items()})
    for fault,window in low_windows(events):lows.append(dict(**meta,fault=fault,**g.compare(window,refs,models,fault)))
    for fault,window in h11.common_fault_windows(events):commons.append(dict(**meta,**h11.compare_common(window,refs,models,fault)))
    result=dict(clean=clean,stress=cropped,full=full,low=lows,common=commons,states=states,activation=activation,reference_bearing=refbearing,access=store.access,official_baseline_exact=True)
    with gzip.open(out/'bags'/(bag+'.json.gz'),'wt',encoding='utf-8') as f:json.dump(result,f,allow_nan=False)
    print('DEVELOP',bag,'original',len(cropped),'low',len(lows),'common',len(commons),flush=True)
    return result


def compare_gate(clean,stress,full,low,common,candidate,baseline):
    b=v6.summary(clean,stress,baseline);c=v6.summary(clean,stress,candidate);reasons=[]
    cg=1-c['clean_rmse']/b['clean_rmse'];fg=1-c['fault_rmse']/b['fault_rmse']
    if cg<.02 and fg<.05:reasons.append('insufficient_gain')
    for metric,limit in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        if c[metric]>b[metric]*(1+limit)+1e-12:reasons.append('aggregate_regression:'+metric)
    bd,cd=v6.macro(full,baseline,'distance'),v6.macro(full,candidate,'distance')
    if cd>bd*1.01+1e-12:reasons.append('full_faulted_distance_regression')
    for label,rows in [('clean',clean),('original',stress),('full',full),('low',low),('common',common)]:
        if label in ('low','common') and v6.macro(rows,candidate,'event_rmse')>v6.macro(rows,baseline,'event_rmse')*1.005+1e-12:
            reasons.append('safety_suite_regression:'+label)
        for row in rows:
            for metric in ('causal_errors','resets'):
                if row['runtime'][candidate][metric]>row['runtime'][baseline][metric]:reasons.append(label+':'+metric+':'+row['bag'])
            for receiver,s in row['receivers'].items():
                a,z=s[baseline],s[candidate];case=label+':'+row['bag']+':'+receiver
                if a['n']!=z['n'] or a['coverage']!=z['coverage']:reasons.append('coverage:'+case)
                if z['false_stop_samples']>a['false_stop_samples']:reasons.append('false_stop:'+case)
                if 'recovery_s' in a and a['recovery_s'] is not None and z['recovery_s'] is None:reasons.append('new_unrecovered:'+case)
                if label=='clean' and a['rmse'] is not None and z['rmse']>a['rmse']+max(.005,.05*a['rmse']):reasons.append('clean_per_bag:'+case)
    return dict(passed=not reasons,reasons=sorted(set(reasons)),baseline=b,candidate=c,clean_gain=cg,fault_gain=fg,full_distance_baseline=bd,full_distance_candidate=cd)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fit',type=Path,required=True);p.add_argument('--data-root',type=Path,required=True);p.add_argument('--source-receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2,choices=[1,2]);a=p.parse_args()
    source_integrity(a.source_receipt);models=model_set(a.fit);a.output.mkdir(parents=True,exist_ok=False)
    for n in ('traces','bags'):(a.output/n).mkdir()
    write(a.output/'started.json',dict(baseline=BASE,observer_class='GuardedReadoutObserver',observer_file=sys.modules[GuardedReadoutObserver.__module__].__file__,
          model_configs={n:asdict(m[1]) for n,m in models.items()},readout=asdict(profile()[1]),ops=g.OPS,fit_lock_sha256=sha(a.fit/'FIT_LOCK.json'),driver_sha256=sha(__file__),
          validation_opened=False,test_opened=False,teacher_runtime_access=False))
    bags=DevelopmentStore(a.data_root).plan['splits']['development'];start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:rows=list(pool.map(worker,[(b,a.data_root,a.fit,a.output) for b in bags]))
    sets={k:([x['clean'] for x in rows] if k=='clean' else [v for x in rows for v in x[k]]) for k in ('clean','stress','full','low','common')}
    summary={n:v6.summary(sets['clean'],sets['stress'],n) for n in NAMES}
    fingerprint={'clean_rmse':.09266814298282507,'fault_rmse':.2375486120563008,'pooled_rmse':.1293056944774334,'distance_rmse':5.310295004801444,'samples':394221}
    if any(abs(summary['main'][k]-v)>1e-12 for k,v in fingerprint.items()):raise AssertionError('Canonical baseline fingerprint mismatch')
    kwargs=[sets[k] for k in ('clean','stress','full','low','common')]
    contract=compare_gate(*kwargs,'gnss','main');control=compare_gate(*kwargs,'wheel','main');attribution=compare_gate(*kwargs,'gnss','wheel')
    check=json.loads((a.fit/'check_gate.json').read_text());activation={}
    for n in ('gnss','wheel'):
        groups={x['clean']['group'] for x in rows if x['activation'][n]>0 and x['reference_bearing']}
        count=sum(x['activation'][n] for x in rows)
        activation[n]=dict(ticks=count,groups=sorted(groups),passed=count>=100 and len(groups)>=3)
    passed=contract['passed'] and attribution['passed'] and check['gnss']['passed'] and activation['gnss']['passed']
    decision=dict(scientific_verdict='CONFIRMED' if passed else 'REJECTED',selected='gnss' if passed else None,
        baseline_contract=contract,control_vs_baseline=control,attribution=attribution,check=check,activation=activation,summary=summary,
        full_distance={n:v6.macro(sets['full'],n,'distance') for n in NAMES},
        supplemental={k:{n:dict(event_rmse=v6.macro(sets[k],n,'event_rmse'),unrecovered=v6.unrecovered(sets[k],n)) for n in NAMES} for k in ('low','common')},
        accuracy_contract_passed=passed,validation_opened=False,test_opened=False,ready_to_merge=False,
        enabled_runtime_verified=False,elapsed_wall_s=time.perf_counter()-start)
    write(a.output/'decision.json',decision)
    with gzip.open(a.output/'results.json.gz','wt',encoding='utf-8') as f:json.dump(sets,f,allow_nan=False)
    write(a.output/'access.json',[v for x in rows for v in x['access']]);write(a.output/'states.json',[v for x in rows for v in x['states']])
    logo=[]
    for group in sorted({r['group'] for r in sets['clean']}):
        logo.append(dict(omitted=group,summary={n:v6.summary([r for r in sets['clean'] if r['group']!=group],[r for r in sets['stress'] if r['group']!=group],n) for n in NAMES}))
    write(a.output/'leave_one_group_out.json',logo)
    flat=[]
    for kind,rr in sets.items():
        for row in rr:
            f=row.get('fault')
            for receiver,scores in row['receivers'].items():
                for n,m in scores.items():
                    values={k:v for k,v in m.items() if not isinstance(v,dict)};values.pop('distance_surrogate',None)
                    flat.append(dict(suite=kind,bag=row['bag'],group=row['group'],receiver=receiver,model=n,
                        fault='clean' if f is None else f['kind'],duration=0 if f is None else f['end']-f['start'],
                        distance_rmse_m=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m'),**values))
    with (a.output/'per_bag.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in flat))));writer.writeheader();writer.writerows(flat)
    source_integrity(a.source_receipt)
    print(json.dumps(decision,indent=2),flush=True)
if __name__=='__main__':main()

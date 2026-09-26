"""Foundation only: canonical v8 equality, fit-train residual scale, loss proposals.

There is deliberately no validation or test CLI stage and no candidate output.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
from statistics import median
import time
from common import ROOT,HERE,BASE,ev,OPS,profile,integrity,VehicleStore,save,sha,GuardedReadoutObserver
from history import History,LAGS

spec=importlib.util.spec_from_file_location('h27_original_windows',ROOT/'tools/research_guarded/compare.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)


class ProbeObserver(GuardedReadoutObserver):
    def __init__(self,config,*,readout,threshold,collector,trace=None):
        self._threshold=threshold
        self._collector=collector
        self._trace=trace
        self._control=GuardedReadoutObserver(config,readout=readout)
        super().__init__(config,readout=readout)

    def reset(self,**kwargs):
        super().reset(**kwargs)
        self._control.reset(**kwargs)
        self._history=History()

    def step(self,t,command=None,front=None,rear=None):
        old_pair=self.adapt_previous;old_d=self.disturbance
        estimate=super().step(t,command,front,rear)
        expected=self._control.step(t,command,front,rear)
        if estimate!=expected: raise AssertionError('Native Estimate changed by monitor')
        for k,value in vars(self._control).items():
            if getattr(self,k)!=value: raise AssertionError('Native state differs: '+k)
        closed,r,opened=self._history.observe(t,command,front,rear,estimate,old_pair,old_d,self.c,self._threshold)
        if closed is not None:self._collector['episodes'].append(closed)
        if r is not None:self._collector['residuals'].append(r)
        self._collector['ticks']+=1
        self._collector['history_peak']=max(self._collector['history_peak'],self._history.peak)
        self._collector['last_observer']=self
        if self._trace is not None:
            line=[t,command.value if command else None,front.value if front else None,rear.value if rear else None,
                  old_d,self.disturbance,self.drive_a,self.v,estimate.v,estimate.s,estimate.mode,
                  estimate.front_status,estimate.rear_status,self._history.episode is not None]
            self._trace.write(json.dumps(line,separators=(',',':'),allow_nan=False)+'\n')
        return estimate


def replay(events,threshold,fault=None,trace_path=None):
    collector=dict(episodes=[],residuals=[],ticks=0,history_peak=0)
    cfg,readout=profile()
    trace=gzip.open(trace_path,'wt',compresslevel=6) if trace_path else None
    old=ev.Observer
    try:
        ev.Observer=partial(ProbeObserver,readout=readout,threshold=threshold,collector=collector,trace=trace)
        array,info=ev.replay(events,cfg,OPS,fault)
    finally:
        ev.Observer=old
        if trace:trace.close()
    observer=collector.pop('last_observer',None)
    if observer and observer._history.episode:
        collector['episodes'].append(dict(observer._history.episode,end=observer.t,end_reason='stream_end'))
    collector.update(runtime=info,outputs=len(array),output_sha256=hashlib.sha256(array.tobytes()).hexdigest(),
                     canonical_equality='all original fields and every Estimate on every tick')
    return collector


def worker(args):
    bag,stage,threshold,output=args
    output=Path(output)
    store=VehicleStore();role='train' if stage=='fit' else 'development'
    events,_=store.load(bag,role,reference=False)
    meta=dict(bag=bag,group=store.records[bag]['group'],role=role)
    if stage=='fit':
        r=replay(events,threshold)
        return dict(**meta,**r,access=store.access)
    rows=[]
    windows=[('natural',None,events)]
    windows += [('original-'+str(i),fault,window) for i,(fault,window) in enumerate(original.fault_windows(events))]
    for label,fault,window in windows:
        trace=output/'traces'/f'{bag}-{label}.jsonl.gz'
        r=replay(window,threshold,fault,trace)
        r.pop('residuals')
        rows.append(dict(**meta,suite=label,fault=fault,**r,trace=trace.name))
    return dict(rows=rows,access=store.access)


def distribution(values):
    if not values:return dict(n=0,median=None,mad=None,p95_abs=None,max_abs=None)
    x=ev.np.asarray(values,float);m=float(ev.np.median(x))
    return dict(n=len(x),median=m,mad=float(ev.np.median(abs(x-m))),
                p95_abs=float(ev.np.quantile(abs(x),.95)),max_abs=float(max(abs(x))))


def fit(output,workers,provenance):
    store=VehicleStore();bags=store.plan['splits']['train']
    groups=sorted({store.records[b]['group'] for b in bags})
    fitting=groups[::2];checking=groups[1::2]
    by_group=defaultdict(list);access=[];checks=[]
    with gzip.open(output/'residuals.jsonl.gz','wt') as raw,ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(worker,[(b,'fit',1e9,str(output)) for b in bags]):
            residuals=result.pop('residuals');by_group[result['group']].extend(residuals)
            raw.write(json.dumps(dict(bag=result['bag'],group=result['group'],r=residuals))+'\n')
            access.extend(result.pop('access'))
            result['loss_episodes']=len(result.pop('episodes'));checks.append(result)
            print('TRAIN',result['bag'],result['ticks'],'residuals',len(residuals),flush=True)
    statistics={g:distribution(by_group[g]) for g in groups}
    sigmas=[1.4826*statistics[g]['mad'] for g in fitting if statistics[g]['n']>=100]
    threshold=max(.02,3*median(sigmas)) if len(sigmas)>=3 else None
    scale=dict(threshold=threshold,status='FITTED' if threshold is not None else 'INCONCLUSIVE',
               rule='max(.02,3*median(fit-group 1.4826*MAD of trusted legacy d increments))',
               fitting_groups=fitting,check_groups=checking,group_statistics=statistics,
               usable_fit_groups=len(sigmas),provenance=provenance)
    save(output/'SCALE.json',scale);save(output/'baseline_train.json',checks);save(output/'access.json',access)
    print('TRAIN_SCALE',json.dumps(scale),flush=True)


def probe(output,workers,scale_path,provenance):
    scale=json.loads(scale_path.read_text());threshold=scale['threshold']
    if threshold is None:raise ValueError('Insufficient train fit scale, do not access development')
    if scale['provenance']['pinned']!=provenance['pinned'] or scale['provenance']['code']!=provenance['code']:
        raise ValueError('Code/pins differ after fit')
    (output/'traces').mkdir()
    store=VehicleStore();bags=store.plan['splits']['development'];rows=[];access=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(worker,[(b,'probe',threshold,str(output)) for b in bags]):
            rows.extend(result['rows']);access.extend(result['access'])
            print('DEVELOPMENT',result['rows'][0]['bag'],flush=True)
    summary={}
    for lag in LAGS:
        entries=[(r,e) for r in rows for e in r['episodes']]
        eligible=[(r,e) for r,e in entries if e['proposals'][str(lag)]['eligible']]
        groups=sorted({r['group'] for r,e in eligible});bags_active=sorted({r['bag'] for r,e in eligible})
        ticks=sum(e['ticks'] for r,e in eligible)
        passed=len(eligible)>=10 and len(groups)>=3 and ticks>=100
        natural=sum(r['suite']=='natural' for r,e in eligible)
        bygroup={g:dict(episodes=sum(r['group']==g for r,e in eligible),ticks=sum(e['ticks'] for r,e in eligible if r['group']==g)) for g in groups}
        reasons=defaultdict(int)
        for r,e in entries:reasons[e['proposals'][str(lag)]['reason']]+=1
        summary[str(lag)]=dict(coverage_passed=passed,qualifying_episodes=len(eligible),natural_episodes=natural,
                    original_fault_episodes=len(eligible)-natural,potential_model_only_ticks=ticks,
                    original_source_groups=groups,bags=bags_active,by_group=bygroup,reasons=dict(reasons),
                    delta_d=distribution([e['proposals'][str(lag)]['delta_d'] for r,e in eligible]),
                    observed_delta_d=distribution([e['proposals'][str(lag)]['delta_d'] for r,e in entries if 'delta_d' in e['proposals'][str(lag)]]))
    with gzip.open(output/'episodes.json.gz','wt') as f:json.dump(rows,f,allow_nan=False)
    compact=[]
    for r in rows:
        clean={k:v for k,v in r.items() if k!='episodes'}
        clean['loss_episodes']=len(r['episodes']);compact.append(clean)
    save(output/'baseline_replays.json',compact);save(output/'access.json',access)
    decision=dict(hypothesis='R3-H27',baseline=BASE,threshold=threshold,scale_sha256=sha(scale_path),
                  mechanism_status='PROPOSAL_ONLY_NO_INTERVENTION',
                  coverage_status='SUFFICIENT' if any(x['coverage_passed'] for x in summary.values()) else 'INSUFFICIENT',
                  scientific_verdict='FOUNDATION_SUFFICIENT_FOR_PATCH' if any(x['coverage_passed'] for x in summary.values()) else 'INCONCLUSIVE',
                  accuracy_contract_passed=False,runtime_verified=False,ready_to_merge=False,
                  variants=summary,development_bags=len(bags),original_fault_scenarios=sum(r['fault'] is not None for r in rows),
                  validation_opened=False,test_evaluated=False,
                  limitation='Counts are proposed nonzero d substitutions, not demonstrated beneficial changes or true d contamination.',
                  provenance=provenance)
    save(output/'SUMMARY.json',decision);print(json.dumps(decision),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['fit','probe'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scale',type=Path)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    if not 1<=args.workers<=4:raise ValueError('workers1..4')
    args.output.mkdir(parents=True,exist_ok=False)
    provenance=integrity();provenance.update(python=platform.python_version(),numpy=ev.np.__version__)
    save(args.output/'started.json',provenance)
    if args.stage=='fit':fit(args.output,args.workers,provenance)
    else:
        if args.scale is None:raise ValueError('--scale required')
        probe(args.output,args.workers,args.scale,provenance)

if __name__=='__main__':main()

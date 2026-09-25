"""H13: fixed paired comparison with pinned v8, no runtime or judge edits.

Only validation may be loaded. This runner produces descriptive failures too;
eligibility is checked explicitly, never inferred from a green execution job.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'research/H13'),str(ROOT/'tools/research_guarded'),str(ROOT/'tools/finalization')]
import compare as shared
import evaluate as ev
import numpy as np
from factory import candidate, GuardedReadoutObserver, sha
from mechanism import Limits
from reserve_odometry.core import Config

OPS={'rate_hz':20., 'alignment_delay_s':0.}
NAMES=('main','candidate')


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def check_sources():
    freeze=json.loads((ROOT/'research/H13/FREEZE.json').read_text())
    for path,digest in freeze['source_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('Frozen file changed: '+path)
    if asdict(Limits())!=freeze['limits']:raise ValueError('Parameters changed')
    return freeze


def models():
    cfg=json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())['config']
    return {'main':(GuardedReadoutObserver,Config(**cfg)),
            'candidate':(candidate(True),Config(**cfg))}


def anchor(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return None
    t,u,f,r,valid=grid
    suitable=valid & (np.abs(u)<=.05) & (np.abs(f-r)<.15) & ((f+r)*.5>2)
    # A trailing one-second window, not future command data, establishes neutral.
    neutral=(np.abs(u)<=.05)&valid
    streak=0
    for i,ok in enumerate(neutral):
        streak=streak+1 if ok else 0
        if streak>=11 and suitable[i] and t[i]>max(25.,.1*t[-1]) and t[i]<t[-1]-35:
            return float(t[i])
    return None


def slow_windows(events):
    start=anchor(events)
    if start is None:return []
    result=[]
    for height,ramp in ((5.,3.),(4.,4.)):
        fault=dict(kind='slow_common',start=start,ramp_end=start+ramp,end=start+ramp+1.,height=height)
        window=events[(events[:,0]>=start-20)&(events[:,0]<=fault['end']+10.1)].copy()
        changed=window.copy();mask=(changed[:,0]>=start)&(changed[:,0]<fault['end'])&np.isin(changed[:,1],(1,2))
        changed[mask,2]+=height*np.minimum(1.,(changed[mask,0]-start)/ramp)
        result.append((fault,changed))
    return result


def abrupt_windows(events):
    spec=importlib.util.spec_from_file_location('h11_unchanged',ROOT/'tools/research_h11/compare.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return [(f,m.inject_common(w,f)) for f,w in m.common_fault_windows(events)]


class Trace:
    """Evaluator-only observation wrapper. Labels never enter the estimator."""
    def __init__(self,inner,start,end):
        self.inner,self.start,self.end=inner,start,end
        self.in_event=Counter()
    def __getattr__(self,key):return getattr(self.inner,key)
    def reset(self,*args,**kwargs):return self.inner.reset(*args,**kwargs)
    def step(self,*args,**kwargs):
        e=self.inner.step(*args,**kwargs)
        if self.start<=e.t<self.end:self.in_event[e.mode]+=1
        return e


def custom_score(events,refs,ms,fault):
    arrays={};runtime={}
    for name,(cls,config) in ms.items():
        traced=Trace(cls(config),fault['start'],fault['end'])
        old=ev.Observer
        try:
            ev.Observer=lambda c:traced
            arrays[name],runtime[name]=ev.replay(events,config,OPS)
        finally:ev.Observer=old
        runtime[name]['in_event_modes']=dict(traced.in_event)
        g=getattr(traced.inner,'_h13',None)
        runtime[name]['h13']=None if g is None else dict(pairs=g.pairs,suspicious_pairs=g.suspicious_pairs,triggers=g.triggers,vetoes=g.vetoes)
    t=arrays['main'][:,0]
    if not np.array_equal(t,arrays['candidate'][:,0]):raise AssertionError('Changed schedule')
    scores={}
    for receiver,values in refs.items():
        target=ev.ex.match(values,t)
        mask=np.isfinite(target)&(t>=fault['start'])&(t<fault['end']+10)
        event=mask&(t<fault['end'])
        scores[receiver]={}
        for name,a in arrays.items():
            m=ev.ex.metrics(t,a[:,1],target,mask)
            m['event_rmse']=ev.ex.metrics(t,a[:,1],target,event)['rmse']
            m['false_stop_samples']=int(np.sum(mask&(target>1.)&(a[:,5]>0)))
            good=mask&(t>=fault['end'])&(np.abs(a[:,1]-target)<.25)
            hits=np.flatnonzero(np.convolve(good.astype(int),np.ones(20,int),mode='valid')==20) if len(t)>=20 else []
            m['recovery_s']=float(t[hits[0]]-fault['end']) if len(hits) else None
            scores[receiver][name]=m
    return dict(fault=fault,outputs=len(t),receivers=scores,runtime=runtime)


def worker(args):
    bag,data_root,out=args
    st=ev.ex.Store(data_root)
    if bag not in st.plan['splits']['validation']:raise PermissionError('H13 validation only')
    events,refs=st.load(bag,'validation')
    meta=dict(bag=bag,group=st.records[bag]['group'],role='validation')
    ms=models()
    clean=dict(**meta,**shared.compare(events,refs,ms))
    faults=[dict(**meta,fault=f,**shared.compare(w,refs,ms,f)) for f,w in shared.fault_windows(events)]
    abrupt=[dict(**meta,**custom_score(w,refs,ms,f)) for f,w in abrupt_windows(events)]
    slow=[dict(**meta,**custom_score(w,refs,ms,f)) for f,w in slow_windows(events)]
    row=dict(clean=clean,stress=faults,abrupt=abrupt,slow=slow,access=st.access,
             slow_anchor_missing=not bool(slow))
    save(out/'bags'/(bag+'.json'),row)
    print(bag,'original',len(faults),'abrupt',len(abrupt),'slow',len(slow),flush=True)
    return row


def diagnostics(rows):
    data=shared.aggregate([],rows)
    for name in NAMES:
        counts=Counter();triggers=vetoes=0
        for r in rows:
            counts.update(r['runtime'][name].get('in_event_modes',{}))
            g=r['runtime'][name].get('h13') or {}
            triggers+=g.get('triggers',0);vetoes+=g.get('vetoes',0)
        data[name]['in_event_modes']=dict(counts)
        data[name]['h13_triggers']=triggers;data[name]['h13_vetoes']=vetoes
    return data


def decision(clean,stress,abrupt_rows,slow_rows,summary,abrupt,slow):
    reasons=[]
    b,c=summary['main'],summary['candidate']
    for key in ('macro_rmse','pooled_rmse','fault_macro','distance_macro'):
        if b[key] is None or c[key] is None:reasons.append('missing original '+key)
        elif c[key]>b[key]*1.001:reasons.append('original regression '+key)
    for key in ('false_stops','fault_false_stops','fault_missing_recovery'):
        if c[key]>b[key]:reasons.append('increased original '+key)
    for suite,agg in [('abrupt',abrupt),('slow',slow)]:
        b,c=agg['main'],agg['candidate']
        if b['fault_macro'] is None or c['fault_macro'] is None:
            reasons.append('missing '+suite+' reference');continue
        if suite=='abrupt' and c['fault_macro']>b['fault_macro']*1.001:reasons.append('abrupt regression')
        for key in ('fault_false_stops','fault_missing_recovery'):
            if c[key]>b[key]:reasons.append('increased '+suite+' '+key)
    b,c=slow['main'],slow['candidate'];gain=None
    if b['fault_macro'] is not None and c['fault_macro'] is not None and b['fault_macro']>0:
        gain=1-c['fault_macro']/b['fault_macro']
        if gain<.20:reasons.append('slow gain below 20%')
        for mode in ('REACQUIRING','FUSED'):
            x=b['in_event_modes'].get(mode,0);y=c['in_event_modes'].get(mode,0)
            if (x>0 and y>=x) or (x==0 and y>0):reasons.append('slow exposure not reduced '+mode)
    for row in clean+stress+abrupt_rows+slow_rows:
        for key in ('resets','causal_errors'):
            if row['runtime']['candidate'][key]!=0:reasons.append('runtime '+key+' '+row['bag'])
        for scores in row['receivers'].values():
            if scores['main']['n']!=scores['candidate']['n'] or scores['main']['coverage']!=scores['candidate']['coverage']:
                reasons.append('coverage mismatch '+row['bag'])
    return dict(numerically_eligible=not reasons,slow_gain=gain,rejection_reasons=sorted(set(reasons)),
                promotion_allowed=False,
                qualification='Reused validation and injected faults. Full installed-candidate ROS/resource gates also required before promotion.')


def run(out,data_root,workers):
    if out.exists():raise FileExistsError(out)
    freeze=check_sources();st=ev.ex.Store(data_root)
    out.mkdir(parents=True);(out/'bags').mkdir()
    save(out/'started.json',dict(freeze=freeze,python=sys.version,numpy=np.__version__,test_evaluated=False))
    start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows=list(pool.map(worker,[(b,data_root,out) for b in st.plan['splits']['validation']]))
    clean=[r['clean'] for r in rows];stress=[s for r in rows for s in r['stress']]
    abrupt_rows=[s for r in rows for s in r['abrupt']];slow_rows=[s for r in rows for s in r['slow']]
    summary=shared.aggregate(clean,stress);abrupt=diagnostics(abrupt_rows);slow=diagnostics(slow_rows)
    d=decision(clean,stress,abrupt_rows,slow_rows,summary,abrupt,slow)
    result=dict(summary=summary,abrupt=abrupt,slow=slow,decision=d,clean=clean,stress=stress,
                abrupt_rows=abrupt_rows,slow_rows=slow_rows,slow_missing_anchors=[r['clean']['bag'] for r in rows if r['slow_anchor_missing']],
                elapsed_s=time.perf_counter()-start)
    save(out/'access.json',[a for r in rows for a in r['access']]);save(out/'results.json',result)
    save(out/'summary.json',{k:result[k] for k in ('summary','abrupt','slow','decision','slow_missing_anchors','elapsed_s')})
    print(json.dumps(result['decision'],indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data-root',type=Path,default=ROOT/'dataset/data');p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();run(a.output,a.data_root,a.workers)

"""H11 paired validation: common-mode jump quarantine.

Uses the current champion v7 as baseline and changes only the inner Config
common_mode_quarantine_s from 0 to the preregistered 1.5 s. GNSS is evaluator
only. Final-test measurements are never opened.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/research_guarded'),str(ROOT/'tools/finalization'),str(ROOT/'src/reserve_odometry')]
import compare as base
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig

OPS={'rate_hz':20.0,'alignment_delay_s':0.0}
NAMES=('main','candidate')
QUARANTINE_S=1.5


def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def models():
    profile=json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())
    cfg=dict(profile['config'])
    # H11 is not part of the published v7 profile; zero means exact baseline.
    cfg.pop('common_mode_quarantine_s',None)
    readout=ReadoutConfig(**profile['readout'])
    baseline=Config(**cfg,common_mode_quarantine_s=0.0)
    candidate=Config(**cfg,common_mode_quarantine_s=QUARANTINE_S)
    return {
        'main': (lambda c: GuardedReadoutObserver(c,readout=readout),baseline),
        'candidate': (lambda c: GuardedReadoutObserver(c,readout=readout),candidate),
    }


def common_fault_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    indices=np.flatnonzero(valid & ((f+r)/2>2) & (np.abs(f-r)<.15)
                           & (t>max(25.,.1*t[-1])) & (t<t[-1]-35.))
    if not len(indices):return
    anchor=float(t[indices[0]])
    for duration in (.7,1.2):
        fault=dict(kind='common_bias',start=anchor,end=anchor+duration,offset=5.)
        window=events[(events[:,0]>=anchor-20.)&(events[:,0]<=anchor+duration+10.1)].copy()
        yield fault,window


def inject_common(events,fault):
    changed=events.copy()
    mask=((changed[:,0]>=fault['start'])&(changed[:,0]<fault['end'])
          &((changed[:,1]==1)|(changed[:,1]==2)))
    changed[mask,2]+=fault['offset']
    return changed


def compare_common(events,refs,model_set,fault):
    changed=inject_common(events,fault)
    predictions={};runtime={}
    for name,model in model_set.items():
        predictions[name],runtime[name]=base.predict(changed,model,None)
    ref_array=predictions['main'];t=ref_array[:,0]
    for name,a in predictions.items():
        if a.shape!=ref_array.shape or not np.allclose(a[:,0],t,rtol=0,atol=1e-8):
            raise AssertionError('candidate schedule changed')
    receivers={}
    for receiver,values in refs.items():
        target=ev.ex.match(values,t)
        mask=np.isfinite(target)&(t>=fault['start'])&(t<fault['end']+10.)
        scores={}
        for name,a in predictions.items():
            m=ev.ex.metrics(t,a[:,1],target,mask)
            m['event_rmse']=ev.ex.metrics(t,a[:,1],target,mask&(t<fault['end']))['rmse']
            m['false_stop_samples']=int(np.sum(mask&(target>1.)&(a[:,5]>0)))
            good=mask&(t>=fault['end'])&(np.abs(a[:,1]-target)<.25)
            runs=np.convolve(good.astype(int),np.ones(20,int),mode='valid') if len(t)>=20 else np.array([])
            hit=np.flatnonzero(runs==20)
            m['recovery_s']=float(t[hit[0]]-fault['end']) if len(hit) else None
            scores[name]=m
        receivers[receiver]=scores
    return dict(receivers=receivers,runtime=runtime,outputs=len(t),fault=fault)


def worker(args):
    bag,data_root,output=args
    store=ev.ex.Store(data_root)
    if bag not in store.plan['splits']['validation']:
        raise PermissionError('H11 allows validation only')
    events,refs=store.load(bag,'validation');ms=models()
    meta=dict(bag=bag,group=store.records[bag]['group'],role='validation')
    clean=dict(**meta,**base.compare(events,refs,ms))
    stress=[dict(**meta,fault=f,**base.compare(w,refs,ms,f)) for f,w in base.fault_windows(events)]
    common=[dict(**meta,**compare_common(w,refs,ms,f)) for f,w in common_fault_windows(events)]
    save(output/'bags'/(bag+'.json'),dict(clean=clean,stress=stress,common=common,access=store.access))
    print(bag,'common',len(common),flush=True)
    return clean,stress,common,store.access


def common_summary(rows):
    result={}
    for name in NAMES:
        groups=defaultdict(list);missing=0;stops=0;recoveries=[];mode_reacquire=0
        for row in rows:
            mode_reacquire+=row['runtime'][name]['mode_counts'].get('REACQUIRING',0)
            for scores in row['receivers'].values():
                m=scores[name];stops+=m['false_stop_samples']
                if m['event_rmse'] is not None:
                    groups[row['group']].append(m['event_rmse'])
                    if m['recovery_s'] is None:missing+=1
                    else:recoveries.append(m['recovery_s'])
        vals=[float(np.mean(x)) for x in groups.values()]
        result[name]=dict(event_macro_rmse=float(np.mean(vals)) if vals else None,
                          false_stops=stops,unrecovered=missing,
                          mean_recovery_s=float(np.mean(recoveries)) if recoveries else None,
                          reacquiring_ticks=mode_reacquire,groups={k:float(np.mean(v)) for k,v in groups.items()})
    return result


def decide(clean,stress,summary,common):
    b=summary['main'];c=summary['candidate'];cb=common['main'];cc=common['candidate'];reasons=[]
    for key in ('macro_rmse','fault_macro','distance_macro'):
        if b[key] is None or c[key] is None:reasons.append('missing '+key)
    if not reasons:
        if c['macro_rmse']>b['macro_rmse']*1.001:reasons.append('clean regression >0.1%')
        if c['fault_macro']>b['fault_macro']*1.001:reasons.append('original fault regression >0.1%')
        if c['distance_macro']>b['distance_macro']*1.001:reasons.append('distance regression >0.1%')
    for key in ('false_stops','fault_false_stops','fault_missing_recovery'):
        if c[key]>b[key]:reasons.append('increased '+key)
    if cb['event_macro_rmse'] is None or cc['event_macro_rmse'] is None:
        reasons.append('missing common-mode reference')
        common_gain=None
    else:
        common_gain=1-cc['event_macro_rmse']/cb['event_macro_rmse']
        if common_gain<.20:reasons.append('common-mode gain below 20%')
    if cc['unrecovered']>cb['unrecovered']:reasons.append('common-mode unrecovered increased')
    if cc['false_stops']>cb['false_stops']:reasons.append('common-mode false stops increased')
    if cc['reacquiring_ticks']>=cb['reacquiring_ticks'] and cb['reacquiring_ticks']>0:
        reasons.append('erroneous reacquiring not reduced')
    # Exact schedule/coverage checks already performed by base.compare.
    return dict(eligible=not reasons,rejection_reasons=reasons,common_mode_gain=common_gain,
                qualification='Reused validation + deterministic injected suite; NOT independent test')


def run(output,data_root,workers):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);(output/'bags').mkdir()
    store=ev.ex.Store(data_root)
    started=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 base_main='65bba39ed05c781f3f69a65c02f69931152cbfd9',
                 candidate='H11_common_mode_quarantine_1p5s',quarantine_s=QUARANTINE_S,
                 test_evaluated=False,role='validation',workers=workers,
                 split_sha256=store.plan['manifest_sha256'],
                 source_sha256={str(p.relative_to(ROOT)):ev.sha(p) for p in [
                     Path(__file__),ROOT/'src/reserve_odometry/reserve_odometry/core.py',
                     ROOT/'src/reserve_odometry/reserve_odometry/guarded_readout.py',
                     ROOT/'src/reserve_odometry/config/guarded_readout_v7.json',
                     ROOT/'research/H11_COMMON_MODE_PLAN.md']})
    save(output/'started.json',started);begin=time.perf_counter()
    args=[(bag,Path(data_root),output) for bag in store.plan['splits']['validation']]
    with ProcessPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(worker,args))
    clean=[x[0] for x in rows];stress=[s for x in rows for s in x[1]];common=[s for x in rows for s in x[2]]
    summary=base.aggregate(clean,stress);cs=common_summary(common);decision=decide(clean,stress,summary,cs)
    access=[a for x in rows for a in x[3]];save(output/'access.json',access)
    report=dict(started=started,summary=summary,common_mode=cs,decision=decision,
                clean=clean,stress=stress,common=common,elapsed_s=time.perf_counter()-begin)
    save(output/'results.json',report)
    print(json.dumps(dict(summary=summary,common_mode=cs,decision=decision),indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data-root',type=Path,default=ROOT/'dataset/data');p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();r=run(a.output,a.data_root,a.workers)
    if not r['decision']['eligible']:raise SystemExit('H11 did not pass preregistered gates')

"""Stage 0: train-only mechanism coverage and baseline residuals. No fitting."""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import json
import math
import os
from pathlib import Path
from common import ROOT, BASE, ev, np, Config, Sample, GuardedReadoutObserver, Timeline
from common import profile, integrity, train_partition, save, sha


def mode(u):
    return 'traction' if u>.04 else 'braking' if u<-.04 else 'coast'


def hat(x):
    return np.maximum(0., 1.-np.abs(np.asarray(x)[...,None]-np.array([.25,.5,.75]))/.25)


def samples(row):
    return tuple(Sample(float(row[i]),float(row[i+1])) for i in (1,3,5))


def baseline_rollout(window):
    c,r,_=profile(); obs=GuardedReadoutObserver(c,readout=r)
    for row in window[:101]:
        obs.step(float(row[0]),*samples(row))
    pred=[]
    for k,row in enumerate(window[101:],1):
        e=obs.step(float(row[0]),samples(row)[0],None,None)
        if k in (10,40): pred.append(e.v)
    return pred


def scan(bag):
    store=ev.ex.Store(); events,_=store.load(bag,'train'); c,r,ops=profile()
    obs=GuardedReadoutObserver(c,readout=r); tl=Timeline(obs,rate_hz=20.,delay_s=0.)
    rows=[];good=[];bins=defaultdict(list); levels=defaultdict(int); previous=None
    causal=0; outputs=0
    for t,ch,val in events:
        tl.ingest(int(ch), Sample(float(t),float(val)))
        for e,held in tl.advance():
            outputs+=1; causal+=sum(s is not None and s.t>e.t+1e-9 for s in held)
            row=[e.t]+[z for s in held for z in ((s.t,s.value) if s else (math.nan,math.nan))]
            ok=(all(obs._valid(s,e.t,c.command_timeout_s if i==0 else c.max_age_s)
                    for i,s in enumerate(held)) and abs(held[0].value)<=1. and
                abs(held[1].t-held[2].t)<=c.pair_skew_s and
                abs(held[1].value-held[2].value)<.15 and
                .5<(held[1].value+held[2].value)/2<35.)
            rows.append(row);good.append(ok)
            if not ok: previous=None;continue
            u=held[0].value;phase=mode(u);x=max(0.,min(1.,(abs(u)-c.command_deadband)/(1-c.command_deadband)))
            levels[(phase,round(x,6))]+=1
            if e.mode=='FUSED':
                z=(held[1].value+held[2].value)/2;tz=(held[1].t+held[2].t)/2
                if previous and .05<=tz-previous[0]<=c.max_age_s:
                    a=(z-previous[1])/(tz-previous[0])
                    if abs(a)<=2.5:
                        # Wheel-derived diagnostic at delayed pair stamps, not ground truth.
                        residual=a-obs.drive_a+obs.resistance(obs.v)
                        bins[(phase,min(3,int(x*4)))].append(residual)
                previous=(tz,z)
    a=np.asarray(rows,float).reshape(-1,7); g=np.asarray(good,bool); wins=[]
    if len(a)>=141:
        starts=np.flatnonzero(np.convolve(g.astype(int),np.ones(141,int),mode='valid')==141)
        eligible=starts+100
        for phase in ('traction','braking','coast'):
            for bin_id in ([0] if phase=='coast' else range(4)):
                ix=[int(i) for i in eligible if mode(a[i,2])==phase and
                    (phase=='coast' or min(3,int(max(0.,(abs(a[i,2])-.04)/.96)*4))==bin_id)]
                if ix:
                    i=ix[len(ix)//2]; w=a[i-100:i+41].copy()
                    if not np.allclose(np.diff(w[:,0]),.05,rtol=0,atol=1e-8):continue
                    wins.append(dict(phase=phase,bin=bin_id,anchor=float(a[i,0]),window=w.tolist()))
    residuals=[dict(phase=p,bin=b,n=len(v),mean=float(np.mean(v)),rmse=float(np.sqrt(np.mean(np.square(v)))))
               for (p,b),v in sorted(bins.items())]
    return dict(bag=bag,group=store.records[bag]['group'],outputs=outputs,causal_errors=causal,
                resets=tl.resets,levels=[dict(phase=p,x=x,ticks=n,seconds=n*.05) for (p,x),n in sorted(levels.items())],
                residuals=residuals,windows=wins,access=store.access)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    pinned=integrity();store=ev.ex.Store();partition=train_partition(store)
    save(args.output/'started.json',dict(baseline=BASE,source=os.environ.get('GITHUB_SHA'),pinned=pinned,
         time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),train_groups=partition,
         validation_evaluated=False,test_evaluated=False))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        scanned=list(pool.map(scan,store.plan['splits']['train']))
    buckets=defaultdict(list);levels=defaultdict(lambda:defaultdict(list))
    for row in scanned:
        for w in row.pop('windows'):
            buckets[(row['group'],w['phase'],w['bin'])].append(dict(bag=row['bag'],group=row['group'],**w))
        for q in row['levels']: levels[q['phase']][row['group']].append(q)
    chosen=[]
    for key,ws in sorted(buckets.items()):
        w=sorted(ws,key=lambda w:(w['bag'],w['anchor']))[len(ws)//2]
        w['role']=partition[w['group']];chosen.append(w)
    nodes={};free=[]
    for phase in ('traction','braking'):
        for j in range(3):
            byrole={role:[] for role in ('fitting','check')};notches=set();seconds=0.
            for group,qs in levels[phase].items():
                relevant=[q for q in qs if hat(q['x'])[j]>=.1]
                time=sum(q['seconds'] for q in relevant)
                if time>=5.: byrole[partition[group]].append(group)
                seconds+=time;notches.update(q['x'] for q in relevant)
            eligible=len(byrole['fitting'])>=3 and len(byrole['check'])>=2 and len(notches)>=2 and seconds>=20.
            nodes[phase+str(j+1)]=dict(x=(j+1)*.25,groups=byrole,distinct_levels=sorted(notches),
                                     seconds=seconds,eligible=eligible)
            if eligible:free.append((phase,j+1))
    # Structural command design rank counts each group/notch once, never each tick as independent.
    rank={}
    for phase in ('traction','braking'):
        xs=[x for group,qs in levels[phase].items() if partition[group]=='fitting'
            for x in sorted({q['x'] for q in qs})]
        cols=[j-1 for ph,j in free if ph==phase]
        mat=hat(xs)[:,cols] if xs and cols else np.empty((0,0))
        rank[phase]=dict(free=len(cols),rank=int(np.linalg.matrix_rank(mat,tol=1e-8)) if mat.size else 0,
                        singular_values=np.linalg.svd(mat,compute_uv=False).tolist() if mat.size else [])
    ws=np.asarray([w.pop('window') for w in chosen],float)
    np.savez_compressed(args.output/'train_windows.npz',windows=ws)
    for w,window in zip(chosen,ws):
        w['baseline_prediction']=baseline_rollout(window)
        w['wheel_target']=[float((window[k,4]+window[k,6])/2) for k in (110,140)]
        w['residual_mps']=[float(a-b) for a,b in zip(w['baseline_prediction'],w['wheel_target'])]
    save(args.output/'windows.json',chosen)
    coverage=bool(free) and all(r['rank']==r['free'] for r in rank.values())
    save(args.output/'coverage.json',dict(eligible=coverage,free_nodes=free,nodes=nodes,design=rank,
         window_count=len(chosen),window_sha256=sha(args.output/'train_windows.npz'),train_groups=partition,
         interpretation='structural amplitude coverage only; not statistical or physical identifiability'))
    save(args.output/'per_bag.json',scanned)
    save(args.output/'access.json',[a for row in scanned for a in row['access']])
    print(json.dumps(dict(coverage=coverage,free=free,design=rank,windows=len(chosen)),indent=2),flush=True)


if __name__=='__main__':main()

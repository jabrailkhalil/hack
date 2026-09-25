"""Separately scored low-speed lock coverage extension; never replaces original faults."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys
import subprocess
ROOT=Path(__file__).resolve().parents[2]
import runner as lock
v5=lock.v5
np=v5.np


def run_bag(bag):
    _,models=lock.models();models.pop('v5_zero_lock_noise2')
    v5.ev.Observer=lock.observer;v5.ex.replay=lock.replay
    store=v5.ex.Store();events,refs=store.load(bag,'validation');grid=v5.ex.grid_channels(events);stress=[];anchor=None
    if grid is not None:
        t,u,f,r,valid=grid
        idx=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2) & (u>=0) & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
        if len(idx):
            anchor=float(t[idx[0]])
            for duration in (3.,5.):
                window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
                fault=dict(kind='lock',start=anchor,end=anchor+duration)
                row=dict(bag=bag,group=store.records[bag]['group'],fault=fault,**v5.ex.compare(window,refs,models,fault))
                row['counts']['main_v5']=row['counts'].pop('baseline_v2')
                for scores in row['receivers'].values():scores['main_v5']=scores.pop('baseline_v2')
                stress.append(row)
    print('LOW_SPEED',bag,anchor,flush=True)
    return dict(bag=bag,anchor=anchor),stress,store.access


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    plan=ROOT/'research/plan_low_speed_lock.json'
    with ProcessPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run_bag,v5.ex.Store().plan['splits']['validation']))
    stress=[s for r in rows for s in r[1]];summary={}
    for name in ('main_v4','main_v5','v5_zero_lock'):
        usable=[scores[name] for row in stress for scores in row['receivers'].values() if scores[name]['rmse'] is not None]
        summary[name]=dict(event_group_macro_rmse=v5.macro(stress,name,'event_rmse'),
            event_and_recovery_group_macro_rmse=v5.macro(stress,name,'rmse'),false_stop_samples=sum(s['false_stop_samples'] for s in usable),
            unrecovered=sum(s['recovery_s'] is None for s in usable),receiver_cases=len(usable))
    reg=[]
    for row in stress:
        for recv,s in row['receivers'].items():
            if s['main_v5']['rmse'] is None:continue
            a=s['v5_zero_lock'];b=s['main_v5']
            if a['false_stop_samples']>b['false_stop_samples'] or (b['recovery_s'] is not None and a['recovery_s'] is None):reg.append([row['bag'],recv,row['fault']])
    gain=1-summary['v5_zero_lock']['event_group_macro_rmse']/summary['main_v5']['event_group_macro_rmse']
    result=dict(plan=json.loads(plan.read_text()),plan_sha256=v5.ev.sha(plan),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        sources={str(p.relative_to(ROOT)):v5.ev.sha(p) for p in [Path(__file__),Path(lock.__file__),Path(lock.__file__).with_name('prototype_core.py')]},
        summary=summary,gain=gain,case_regressions=reg,eligible=(gain>=.05 and summary['v5_zero_lock']['false_stop_samples']<summary['main_v5']['false_stop_samples'] and not reg),
        anchors=[r[0] for r in rows],stress=stress,access=[a for r in rows for a in r[2]],test_evaluated=False)
    v5.ev.save(args.output/'results.json',result)
    print(json.dumps({k:v for k,v in result.items() if k in ('summary','gain','case_regressions','eligible')},indent=2))

if __name__=='__main__':main()

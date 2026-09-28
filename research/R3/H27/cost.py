"""Fixed AB/BA post-warmup CPU cost; not ROS latency or node RSS."""
import argparse
from functools import partial
import hashlib
import json
from pathlib import Path
import statistics
import time
from common import ev,OPS,profile,VehicleStore,save
from development import CommittedDisturbanceObserver,GuardedReadoutObserver,THRESHOLD,original,source_manifest


def timed(events,fault,lag):
    cfg,readout=profile();warm=float(events[:,0].min())+10.
    stats=dict(step_cpu=0.,step_wall=0.,steps=0,start_cpu=None,start_wall=None,effective_ticks=0)
    base=GuardedReadoutObserver if lag is None else CommittedDisturbanceObserver
    class Timed(base):
        def step(self,t,*args,**kwargs):
            measure=t>=warm
            if measure and stats['start_cpu'] is None:
                stats['start_cpu']=time.process_time();stats['start_wall']=time.perf_counter()
            cpu=time.process_time();wall=time.perf_counter()
            e=super().step(t,*args,**kwargs)
            if measure:
                stats['step_cpu']+=time.process_time()-cpu;stats['step_wall']+=time.perf_counter()-wall;stats['steps']+=1
                stats['effective_ticks']+=int(abs(getattr(self,'_committed_applied_da',0))>1e-12 and abs(getattr(self,'_committed_dv',0))>1e-12)
            return e
    factory=partial(Timed,readout=readout) if lag is None else partial(Timed,readout=readout,lag_s=lag,threshold=THRESHOLD)
    previous=ev.Observer
    try:
        ev.Observer=factory;a,info=ev.replay(events,cfg,OPS,fault)
    finally:ev.Observer=previous
    stats['replay_cpu']=time.process_time()-stats.pop('start_cpu')
    stats['replay_wall']=time.perf_counter()-stats.pop('start_wall')
    stats['outputs']=len(a);stats['outputs_sha256']=hashlib.sha256(a.tobytes()).hexdigest()
    stats['runtime']=info
    return stats


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);provenance=source_manifest();store=VehicleStore()
    first,_=store.load('30618_0652866c','development');first=first[first[:,0]<=first[:,0].min()+120.]
    active,_=store.load('30639_dce52be4','development')
    f,w=list(original.fault_windows(active))[1]  # first eligible foundation case by published lexicographic rule
    workloads=[('development_prefix120',first,None),('foundation_first_active_original1',w,f)]
    rows=[];summaries=[]
    for workload,events,fault in workloads:
        for lag in (.2,.4):
            pairs=[]
            for repeat in range(3):
                for order in ('AB','BA'):
                    pair={}
                    for kind in order:
                        value=timed(events,fault,None if kind=='A' else lag)
                        pair[kind]=value
                        rows.append(dict(workload=workload,lag_s=lag,repeat=repeat,order=order,model=kind,**value))
                    pairs.append(pair)
            summary={}
            for key in ('step_cpu','step_wall','replay_cpu','replay_wall'):
                relative=[x['B'][key]/x['A'][key]-1 for x in pairs]
                summary[key]=dict(baseline_median=statistics.median(x['A'][key] for x in pairs),
                    candidate_median=statistics.median(x['B'][key] for x in pairs),
                    paired_median_change=statistics.median(relative),min_change=min(relative),max_change=max(relative))
            for model in ('A','B'):
                hashes={x[model]['outputs_sha256'] for x in pairs}
                if len(hashes)!=1:raise AssertionError('Nondeterministic cost replay')
            summaries.append(dict(workload=workload,lag_s=lag,summary=summary,post_warmup_steps=pairs[0]['A']['steps'],
                                  candidate_effective_ticks=pairs[0]['B']['effective_ticks']))
    save(args.output/'results.json',dict(provenance=provenance,rows=rows,summary=summaries,access=store.access,
        qualification='Instrumented offline replay after10s warmup, same original collector; not installed ROS latency/RSS. No reference or tuning.'))
    print(json.dumps(summaries,indent=2))

if __name__=='__main__':main()

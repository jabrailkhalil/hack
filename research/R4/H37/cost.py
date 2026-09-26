"""Fixed AB/BA offline timing. No fitting, parameter selection or validation."""
import argparse, gzip, hashlib, json, statistics, time
from pathlib import Path
from common import *
from reserve_odometry.traction_power import TractionPowerObserver


def timed(events, fault, enabled):
    """Time unchanged ev.replay after source-time warmup, with the same collector.

    Step timers include only step(); replay timers also include Timeline, output
    assembly, and the final array conversion. Warmup outputs are retained equally
    by the original evaluator, but their computation is outside the timers.
    """
    origin = float(events[:,0].min()); cut = origin + 10.
    measurements = dict(step_cpu_s=0.,step_wall_s=0.,measured_steps=0)
    started = []; instances = []
    parent = TractionPowerObserver if enabled else GuardedReadoutObserver
    class Timed(parent):
        def __init__(self,c):
            kw={'enabled':True} if enabled else {}
            super().__init__(c,readout=profile()[1],**kw);instances.append(self)
        def step(self,t,*args,**kwargs):
            if t < cut:
                return super().step(t,*args,**kwargs)
            if not started: started.extend((time.process_time(),time.perf_counter()))
            cpu,wall=time.process_time(),time.perf_counter()
            result=super().step(t,*args,**kwargs)
            measurements['step_cpu_s']+=time.process_time()-cpu
            measurements['step_wall_s']+=time.perf_counter()-wall
            measurements['measured_steps']+=1
            return result
    outputs,runtime=replay(events,Timed,fault)
    cpu,wall=time.process_time(),time.perf_counter()
    if not started:raise ValueError('Insufficient workload after 10s warmup')
    measurements.update(replay_cpu_s=cpu-started[0],replay_wall_s=wall-started[1],
        outputs=len(outputs),output_sha256=hashlib.sha256(outputs.tobytes()).hexdigest(),
        runtime=runtime)
    return measurements


def main():
    p=argparse.ArgumentParser();p.add_argument('--development',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);save(args.output/'started.json',pins())
    store=Store(args.output/'access.json');bags=store.plan['splits']['development']
    events,_=store.load(bags[0],'development');start=float(events[:,0].min())
    work=[dict(name='healthy_prefix180',bag=bags[0],events=events[events[:,0]<=start+180.],fault=None)]
    active=None
    for bag in bags:
        row=json.loads((args.development/'bags'/f'{bag}.json').read_text())
        for index,r in enumerate(row['faults']):
            if r['suite']!='original':continue
            with gzip.open(args.development/'traces'/f'{bag}-{index}.json.gz','rt') as f:trace=json.load(f)
            fault=r['fault']
            # Prespecified canonical target activation, never an accuracy ranking.
            ticks=sum(fault['start']<=t[0]<fault['end'] and abs(t[6])>.02 for t in trace['traces']['R4_v8'])
            if ticks:
                evs,_=store.load(bag,'development')
                evs=evs[(evs[:,0]>=fault['start']-20)&(evs[:,0]<=fault['end']+10.1)]
                active=dict(name='first_active_original',bag=bag,events=evs,fault=fault,target_active_ticks=ticks)
                break
        if active:break
    if active:work.append(active)
    result=dict(workloads=[],active_workload_found=active is not None,
        qualification='Instrumented offline Python; not ROS latency, RSS, or a hard real-time guarantee',
        warmup_s=10.,threads=dict(OPENBLAS_NUM_THREADS=os.getenv('OPENBLAS_NUM_THREADS'),OMP_NUM_THREADS=os.getenv('OMP_NUM_THREADS')))
    keys=('step_cpu_s','step_wall_s','replay_cpu_s','replay_wall_s')
    for w in work:
        pairs=[]
        for cycle in range(3):
            for order in ('AB','BA'):
                values={}
                for kind in order:values[kind]=timed(w['events'],w['fault'],kind=='B')
                pairs.append(dict(cycle=cycle,order=order,**values))
        for kind in ('A','B'):
            if len({x[kind]['output_sha256'] for x in pairs})!=1:raise AssertionError('Nondeterministic outputs')
        summary={k:dict(baseline_median=statistics.median(x['A'][k] for x in pairs),
                         candidate_median=statistics.median(x['B'][k] for x in pairs),
                         paired_fraction_median=statistics.median(x['B'][k]/x['A'][k]-1 for x in pairs),
                         paired_fraction_min=min(x['B'][k]/x['A'][k]-1 for x in pairs),
                         paired_fraction_max=max(x['B'][k]/x['A'][k]-1 for x in pairs)) for k in keys}
        result['workloads'].append(dict(**{k:v for k,v in w.items() if k!='events'},pairs=pairs,summary=summary))
        save(args.output/'cost.json',result);print('COST',w['name'],summary,flush=True)
    if not active:save(args.output/'cost.json',result)
if __name__=='__main__':main()

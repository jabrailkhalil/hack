"""Offline H34 AB/BA step and replay cost, identical 10+180s data/collectors.

No fitting, accuracy selection, or validation. Separate healthy and active
numerical path. Process peak RSS is a shared high-water mark, not node RSS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
from common import ROOT,np,ev,profile,save,sha,integrity
from develop import DevelopmentStore,instance

class Timer:
    def __init__(self,o,boundary):
        self.o=o;self.boundary=boundary;self.start_cpu=None;self.start_wall=None;self.step_cpu=0.;self.steps=0
        self.healthy_cpu=0.;self.healthy_steps=0;self.model_cpu=0.;self.model_steps=0
    def __getattr__(self,k):return getattr(self.o,k)
    def reset(self,**kw):self.o.reset(**kw)
    def step(self,t,*args,**kw):
        measured=t>=self.boundary
        if measured and self.start_cpu is None:self.start_cpu=time.process_time();self.start_wall=time.perf_counter()
        start=time.process_time();e=self.o.step(t,*args,**kw);elapsed=time.process_time()-start
        if measured:
            self.steps+=1;self.step_cpu+=elapsed
            if e.mode in ('FUSED','SINGLE_WHEEL'):self.healthy_steps+=1;self.healthy_cpu+=elapsed
            else:self.model_steps+=1;self.model_cpu+=elapsed
        return e


def main():
    p=argparse.ArgumentParser();p.add_argument('--fit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);integrity();fitted={n:json.loads((a.fit/(n+'.json')).read_text()) for n in ('A','B')}
    store=DevelopmentStore();bag=store.plan['splits']['development'][0];events,_=store.load(bag,'development')
    start=float(events[:,0].min());events=events[events[:,0]<start+190.];_,_,ops=profile();rows=[]
    save(a.output/'started.json',dict(fit_hashes={n:sha(a.fit/(n+'.json')) for n in fitted},timer_sha256=sha(__file__),
              stage='cost only; same source/config; no fitting/selection/validation',warmup_s=10.,measured_s=180.))
    for control in ('main','A'):
        for cycle in range(3):
            for order in ((control,'B'),('B',control)):
                for n in order:
                    o=Timer(instance(n,fitted),start+10.);old=ev.Observer
                    try:
                        ev.Observer=lambda c:o;out,info=ev.replay(events,o.c,ops)
                        cpu=time.process_time()-o.start_cpu;wall=time.perf_counter()-o.start_wall
                    finally:ev.Observer=old
                    rows.append(dict(control=control,cycle=cycle,order=order,model=n,measured_steps=o.steps,
                           step_cpu_us=1e6*o.step_cpu/o.steps,replay_cpu_us=1e6*cpu/o.steps,replay_wall_us=1e6*wall/o.steps,
                           healthy_steps=o.healthy_steps,healthy_step_cpu_us=None if not o.healthy_steps else 1e6*o.healthy_cpu/o.healthy_steps,
                           other_steps=o.model_steps,other_step_cpu_us=None if not o.model_steps else 1e6*o.model_cpu/o.model_steps,
                           output_sha256=hashlib.sha256(out.tobytes()).hexdigest(),process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,runtime=info))
    medians={}
    for ctrl in ('main','A'):
        medians[ctrl]={}
        for n in (ctrl,'B'):
            subset=[r for r in rows if r['control']==ctrl and r['model']==n]
            assert len(subset)==6 and len({r['output_sha256'] for r in subset})==1
            medians[ctrl][n]={k:dict(median=float(np.median([r[k] for r in subset])),minimum=min(r[k] for r in subset),maximum=max(r[k] for r in subset)) for k in ('step_cpu_us','replay_cpu_us','replay_wall_us','healthy_step_cpu_us','other_step_cpu_us','process_peak_rss_bytes')}
    save(a.output/'cost.json',dict(bag=bag,rows=rows,medians=medians,access=store.access,validation_opened=False,test_opened=False))
    print(json.dumps(medians,indent=2))

if __name__=='__main__':main()

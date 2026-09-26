"""H44 steady offline cost of immutable fitted profiles. Not ROS latency."""
import argparse
from pathlib import Path
import hashlib
import json
import resource
import time
import numpy as np
from develop import DevelopmentStore, model_set, source_integrity, sha, write, g

class Timer:
    def __init__(self, observer, boundary):
        self.o=observer;self.boundary=boundary;self.step_cpu=0.;self.steps=0
        self.cpu=None;self.wall=None
    def __getattr__(self,n):return getattr(self.o,n)
    def reset(self,**kw):return self.o.reset(**kw)
    def step(self,t,*a,**kw):
        measured=t>=self.boundary
        if measured and self.cpu is None:
            self.cpu=time.process_time();self.wall=time.perf_counter()
        before=time.process_time();result=self.o.step(t,*a,**kw)
        if measured:self.step_cpu+=time.process_time()-before;self.steps+=1
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--fit',type=Path,required=True);p.add_argument('--data-root',type=Path,required=True);p.add_argument('--source-receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source_integrity(a.source_receipt);models=model_set(a.fit);a.output.mkdir(parents=True,exist_ok=False)
    store=DevelopmentStore(a.data_root);bag=store.plan['splits']['development'][0];events,_=store.load(bag,'development')
    begin=float(events[:,0].min());events=events[events[:,0]<begin+190.];rows=[]
    write(a.output/'started.json',dict(fit_lock_sha256=sha(a.fit/'FIT_LOCK.json'),cost_source_sha256=sha(__file__),warmup_s=10.,measured_s=180.,validation_opened=False,test_opened=False))
    for candidate in ('gnss','wheel'):
        for cycle in range(3):
            for order in (('main',candidate),(candidate,'main')):
                for name in order:
                    factory,config=models[name];made=[]
                    def timed(c):
                        o=Timer(factory(c),begin+10.);made.append(o);return o
                    outputs,info=g.predict(events,(timed,config));cpu=time.process_time();wall=time.perf_counter();o=made[0]
                    rows.append(dict(candidate_pair=candidate,model=name,cycle=cycle,order=order,steps=o.steps,
                        step_cpu_us=o.step_cpu/o.steps*1e6,replay_cpu_us=(cpu-o.cpu)/o.steps*1e6,replay_wall_us=(wall-o.wall)/o.steps*1e6,
                        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                        output_sha256=hashlib.sha256(outputs.tobytes()).hexdigest(),runtime=info))
    medians={}
    for candidate in ('gnss','wheel'):
        medians[candidate]={}
        for name in ('main',candidate):
            rr=[r for r in rows if r['candidate_pair']==candidate and r['model']==name]
            assert len(rr)==6 and len({r['output_sha256'] for r in rr})==1
            medians[candidate][name]={k:dict(median=float(np.median([r[k] for r in rr])),minimum=min(r[k] for r in rr),maximum=max(r[k] for r in rr)) for k in ('step_cpu_us','replay_cpu_us','replay_wall_us','process_peak_rss_bytes')}
    write(a.output/'cost.json',dict(bag=bag,rows=rows,medians=medians,access=store.access,interpretation='Single-process high-water RSS, offline steady CPU/wall; not installed ROS or accuracy evidence.'))
    print(json.dumps(medians,indent=2),flush=True)
if __name__=='__main__':main()

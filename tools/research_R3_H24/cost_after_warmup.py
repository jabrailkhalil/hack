"""Measure replay AND step after warmup; do not change/refit either candidate.

The original develop.py cost records step after warmup but whole-replay CPU/wall
including warmup. Keep that record and add this correctly delimited steady
measurement, with identical AB/BA order and collector for both algorithms.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import resource
import time
from common import ROOT,BASE,ev,np,profile,integrity,save,sha
from develop import DevelopmentStore,make,CANDIDATES


class SteadyTimer:
    def __init__(self,o,boundary):
        self.o=o;self.boundary=boundary;self.step_cpu=0.;self.steps=0
        self.start_cpu=None;self.start_wall=None;self.first_t=None;self.last_t=None
    def __getattr__(self,key):return getattr(self.o,key)
    def reset(self,**kwargs):self.o.reset(**kwargs)
    def step(self,t,*args,**kwargs):
        measured=t>=self.boundary
        if measured and self.start_cpu is None:
            self.start_cpu=time.process_time();self.start_wall=time.perf_counter();self.first_t=t
        before=time.process_time();out=self.o.step(t,*args,**kwargs);elapsed=time.process_time()-before
        if measured:self.step_cpu+=elapsed;self.steps+=1;self.last_t=t
        return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--fit',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False);baseline_pins=integrity()
    pins=json.loads((ROOT/'research/R3_H24/candidate_manifest.json').read_text())
    for f,h in pins.items():assert sha(ROOT/f)==h,f
    expected=json.loads((args.fit.parent/'SHA256.json').read_text())
    for n in CANDIDATES:assert sha(args.fit/(n+'.json'))==expected['fit/'+n+'.json']
    fitted={n:json.loads((args.fit/(n+'.json')).read_text()) for n in CANDIDATES}
    assert all(x['success'] for x in fitted.values())
    save(args.output/'started.json',dict(baseline=BASE,candidate_source='6b3a11a68b83ee7b680b3b283f4800726c7b84cd',
         cost_source=os.environ.get('GITHUB_SHA'),timer_sha256=sha(__file__),candidate_pins=pins,baseline_pins=baseline_pins,
         fitted_sha256={n:sha(args.fit/(n+'.json')) for n in CANDIDATES},
         stage='cost-only: no fitting, selection, validation, or algorithm change'))
    store=DevelopmentStore();bag=store.plan['splits']['development'][0]
    events,_=store.load(bag,'development');start=float(events[:,0].min());events=events[events[:,0]<start+190.]
    c,r,ops=profile();rows=[]
    for name in CANDIDATES:
        for cycle in range(3):
            for order in (('main',name),(name,'main')):
                for model in order:
                    instance=[]
                    def factory(cfg):
                        o=SteadyTimer(make(cfg,None if model=='main' else fitted[model]['command_map']),start+10.)
                        instance.append(o);return o
                    old=ev.Observer
                    try:
                        ev.Observer=factory;out,info=ev.replay(events,c,ops)
                        end_cpu=time.process_time();end_wall=time.perf_counter()
                    finally:ev.Observer=old
                    o=instance[0];assert o.steps>0
                    rows.append(dict(pair_candidate=name,model=model,cycle=cycle,order=list(order),
                        measured_steps=o.steps,first_stamp=o.first_t,last_stamp=o.last_t,
                        step_cpu_us=o.step_cpu/o.steps*1e6,
                        replay_cpu_us=(end_cpu-o.start_cpu)/o.steps*1e6,
                        replay_wall_us=(end_wall-o.start_wall)/o.steps*1e6,
                        output_sha256=hashlib.sha256(out.tobytes()).hexdigest(),
                        process_peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024),runtime=info))
    medians={}
    for name in CANDIDATES:
        medians[name]={}
        for model in ('main',name):
            subset=[r for r in rows if r['pair_candidate']==name and r['model']==model]
            assert len({r['output_sha256'] for r in subset})==1
            medians[name][model]={k:dict(median=float(np.median([r[k] for r in subset])),
                                           minimum=min(r[k] for r in subset),maximum=max(r[k] for r in subset))
                for k in ('step_cpu_us','replay_cpu_us','replay_wall_us','process_peak_rss_bytes')}
    result=dict(bag=bag,warmup_s=10.,measured_s=180.,rows=rows,medians=medians,
        access=store.access,validation_evaluated=False,test_evaluated=False,
        interpretation='Offline steady CPU/wall per step; first timed step through end of same collector. Not installed ROS/node RSS.')
    save(args.output/'cost.json',result);print(json.dumps(medians,indent=2),flush=True)


if __name__=='__main__':main()

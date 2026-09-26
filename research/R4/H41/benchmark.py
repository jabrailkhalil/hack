"""Fixed paired H41 cost protocol; no fitting and no accuracy selection.

A/B order alternates, one warmup pair plus five measured pairs for both the
healthy and the fixed [30,40) dropout streams of the first180s development bag.
Official replay/output collection is unchanged; a symmetric step timer is used.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import foundation as f
import runtime


class Timed:
    def __init__(self,inner,warmup_end):
        self.inner=inner;self.warmup_end=warmup_end
        self.step_cpu_ns=0;self.step_wall_ns=0;self.steps=0
        self.cpu_started=None;self.wall_started=None
        self.corrected_steps=0;self.model_only_steps=0
    def __getattr__(self,key):return getattr(self.inner,key)
    def reset(self,*a,**kw):return self.inner.reset(*a,**kw)
    def step(self,t,*args,**kwargs):
        if t<self.warmup_end:return self.inner.step(t,*args,**kwargs)
        if self.cpu_started is None:
            self.wall_started=time.perf_counter_ns();self.cpu_started=time.process_time_ns()
        w=time.perf_counter_ns();c=time.process_time_ns()
        e=self.inner.step(t,*args,**kwargs)
        ce=time.process_time_ns();we=time.perf_counter_ns()
        self.step_cpu_ns+=ce-c;self.step_wall_ns+=we-w;self.steps+=1
        self.corrected_steps+=int(abs(getattr(self.inner,'h41_delta_a',0.))>1e-12)
        self.model_only_steps+=int(e.mode=='MODEL_ONLY')
        return e


def once(events,name,fault):
    config,readout=f.profile()
    inner=(f.GuardedReadoutObserver(config,readout=readout) if name=='baseline' else
        runtime.candidate_class()(config,readout=readout))
    wrapper=Timed(inner,10.)
    old=f.ev.Observer;f.ev.Observer=lambda c:wrapper
    beforew=time.perf_counter_ns();beforec=time.process_time_ns()
    try:outputs,counts=f.ev.replay(events,config,f.OPS,fault)
    finally:f.ev.Observer=old
    afterc=time.process_time_ns();afterw=time.perf_counter_ns()
    if wrapper.steps==0:raise AssertionError('Empty postwarmup')
    return dict(model=name,outputs=len(outputs),postwarmup_steps=wrapper.steps,
        step_cpu_s=wrapper.step_cpu_ns/1e9,step_wall_s=wrapper.step_wall_ns/1e9,
        step_cpu_us_per_output=wrapper.step_cpu_ns/1000/wrapper.steps,
        step_wall_us_per_output=wrapper.step_wall_ns/1000/wrapper.steps,
        replay_cpu_s=(afterc-wrapper.cpu_started)/1e9,
        replay_wall_s=(afterw-wrapper.wall_started)/1e9,
        total_replay_including_warmup_cpu_s=(afterc-beforec)/1e9,
        total_replay_including_warmup_wall_s=(afterw-beforew)/1e9,
        corrected_postwarmup_steps=wrapper.corrected_steps,model_only_postwarmup_steps=wrapper.model_only_steps,
        output_sha256=hashlib.sha256(outputs.tobytes()).hexdigest(),
        timestamps_sha256=hashlib.sha256(outputs[:,0].tobytes()).hexdigest(),runtime=counts)


def run(a):
    if a.output.exists():raise FileExistsError(a.output)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    f.check_source(a.source_receipt)
    store=f.Store(a.data_root);bag=store.plan['splits']['development'][0]
    if bag!='30618_0652866c':raise AssertionError('Preregistered first development bag changed')
    events,_=store.load(bag,'development');events=events[events[:,0]<=180.]
    trials=[]
    for scope,fault in [('healthy',None),('active_dropout',dict(kind='dropout',start=30.,end=40.))]:
        for repeat in range(6):
            order=('baseline','candidate') if repeat%2==0 else ('candidate','baseline')
            for name in order:
                row=once(events,name,fault)
                trials.append(dict(scope=scope,repeat=repeat,warmup=repeat==0,**row))
            print('BENCH_PAIR',scope,repeat,flush=True)
    summary={}
    keys=['step_cpu_s','step_wall_s','replay_cpu_s','replay_wall_s','step_cpu_us_per_output','step_wall_us_per_output']
    for scope in ('healthy','active_dropout'):
        rows=[r for r in trials if r['scope']==scope and not r['warmup']]
        hashes={n:{r['output_sha256'] for r in rows if r['model']==n} for n in ('baseline','candidate')}
        if any(len(v)!=1 for v in hashes.values()):raise AssertionError('Nondeterministic output hash')
        if len({r['timestamps_sha256'] for r in rows})!=1:raise AssertionError('Different timing stream')
        result={}
        for key in keys:
            b=statistics.median(r[key] for r in rows if r['model']=='baseline')
            c=statistics.median(r[key] for r in rows if r['model']=='candidate')
            paired=[]
            for rep in range(1,6):
                pair={r['model']:r for r in rows if r['repeat']==rep}
                paired.append((pair['candidate'][key]/pair['baseline'][key]-1.)*100.)
            result[key]=dict(baseline=b,candidate=c,ratio_of_medians_change_percent=(c/b-1.)*100.,
                paired_median_change_percent=statistics.median(paired),paired_change_percent=paired)
        summary[scope]=result
    data=dict(bag=bag,source_sha=os.environ.get('H41_MEASURED_SHA'),benchmark_source_sha256=f.sha(Path(__file__)),
        stage='development_cost_not_accuracy',seconds=180.,warmup_s=10.,trials=trials,summary=summary,
        memory=dict(process_high_water_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                    scope='Whole offline benchmark including NumPy/input/reference arrays, NOT isolated node RSS'),
        versions=dict(python=platform.python_version(),numpy=f.ev.np.__version__),
        environment=dict(OMP_NUM_THREADS=os.environ.get('OMP_NUM_THREADS'),OPENBLAS_NUM_THREADS=os.environ.get('OPENBLAS_NUM_THREADS')),
        method='1 warmup pair + 5 measured alternating AB/BA pairs per scope; same official replay, step instrumentation, output collector',
        timing_scope='Step sums exclude source timestamps below10s; replay timer starts at first postwarmup step and ends after official output-array materialization. The array includes warmup outputs equally for both methods.',
        access=store.access,validation_opened=False,test_opened=False,node_latency_measured=False)
    f.ev.save(a.output,data);print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-receipt',type=Path);run(p.parse_args())

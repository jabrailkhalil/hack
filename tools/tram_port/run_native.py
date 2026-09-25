"""Run our frozen ports in hack's source-time evaluator (offline, synthetic).

The main numerical functions and Timeline are unchanged upstream functions.
This orchestrator permits differing bootstrap coverage and records both each
method's native mask and the intersection of output timestamps across methods.
"""
from pathlib import Path
import argparse,csv,hashlib,json,math,platform,sys,time,resource
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'vendor/hack'),str(ROOT/'vendor/ours')]
from reserve_odometry.core import Config,Observer
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig
import native_functions as native
from ports import OurObserver
from native_cases import fixtures

METHODS=['mean','A','B','C','H1_10','H2_050','hack_v5','hack_v6','hack_v7','hack_v8']
OPS={'rate_hz':20.,'alignment_delay_s':0.}


def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def dump(path,value):
    def convert(x):
        if isinstance(x,np.generic):return x.item()
        raise TypeError(type(x).__name__)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False,default=convert)+'\n')


def factory(method):
    if not method.startswith('hack_'):
        config=Config()
        return lambda c:OurObserver(method,c),config
    name={'hack_v5':'adaptive_v5','hack_v6':'time_aligned_v6','hack_v7':'guarded_readout_v7','hack_v8':'champion_v8_extracted'}[method]
    document=json.loads((ROOT/'vendor/hack/config'/f'{name}.json').read_text())
    config=Config(**document['config'])
    if method in ('hack_v7','hack_v8'):
        return lambda c:GuardedReadoutObserver(c,readout=ReadoutConfig(**document['readout'])),config
    return Observer,config


class Measured:
    def __init__(self,wrapped):
        self.wrapped=wrapped;self.c=wrapped.c;self.times=[];self.saw_spike=0
    def reset(self):
        self.wrapped.reset();self.times.clear();self.saw_spike=0
    @property
    def t(self):return self.wrapped.t
    def step(self,*args):
        if any(s is not None and s.value==15. for s in args[2:]):self.saw_spike+=1
        start=time.perf_counter_ns();result=self.wrapped.step(*args)
        self.times.append(time.perf_counter_ns()-start)
        return result


def execute(method,events):
    ctor,config=factory(method);instances=[]
    def create(c):
        obj=Measured(ctor(c));instances.append(obj);return obj
    original=native.Observer
    try:
        native.Observer=create
        prediction,info=native.replay(events,config,OPS)
    finally:native.Observer=original
    timed=instances[0]
    info.update(step_p95_us=float(np.quantile(timed.times,.95)/1000),
                step_p99_us=float(np.quantile(timed.times,.99)/1000),
                step_max_us=float(max(timed.times)/1000),
                spike15_exposed_ticks=timed.saw_spike,
                prediction_sha256=digest(prediction))
    return prediction,info


def score(a,reference,interval,common):
    t=a[:,0];target=native.match(reference,t);valid=np.isfinite(target)
    common_mask=valid&np.isin(np.rint(t*1e9).astype('int64'),common)
    own=native.metrics(t,a[:,1],target,valid)
    paired=native.metrics(t,a[:,1],target,common_mask)
    path=native.distance_surrogate(a,target)
    info={'native_speed':own,'paired_speed':paired,'native_path':path,
          'first_output_s':float(t[0]),'last_output_s':float(t[-1]),'outputs':len(t),
          'max_output_gap_s':float(np.diff(t).max()) if len(t)>1 else None,
          'false_zero_samples':int(np.sum(valid&(target>.4)&(np.abs(a[:,1])<.07))),
          'false_STOPPED_samples':int(np.sum(valid&(target>1.)&(a[:,5]>0))),
          'event':None,'fault_plus_recovery':None,'recovery_s':None}
    if interval:
        begin,end=interval;mask=common_mask&(t>=begin)&(t<end+10.)
        info['event']=native.metrics(t,a[:,1],target,mask&(t<end))
        info['fault_plus_recovery']=native.metrics(t,a[:,1],target,mask)
        good=mask&(t>=end)&(np.abs(a[:,1]-target)<.25)
        runs=np.convolve(good.astype(int),np.ones(20,int),mode='valid') if len(t)>=20 else np.array([])
        hits=np.flatnonzero(runs==20)
        info['recovery_s']=float(t[hits[0]]-end) if len(hits) else None
    return info,target


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    (out/'traces').mkdir();(out/'inputs').mkdir()
    plan=fixtures();records=[];start=time.time()
    for case,item in plan.items():
        events=item['events'];reference=item['reference'];preds={};runtimes={}
        input_hash=digest(events)
        np.savez_compressed(out/'inputs'/f'{case}.npz',events=events,reference=np.asarray(reference))
        for method in METHODS:
            preds[method],runtimes[method]=execute(method,events)
        common=None
        for a in preds.values():
            keys=np.rint(a[:,0]*1e9).astype('int64')
            common=keys if common is None else np.intersect1d(common,keys)
        for method,a in preds.items():
            metrics,target=score(a,reference,item['fault'],common)
            row={'method':method,'case':case,'group':item['group'],'fault':item['fault'],
                 'input_sha256':input_hash,'runtime':runtimes[method],**metrics}
            records.append(row)
            np.savez_compressed(out/'traces'/f'{case}__{method}.npz',prediction=a,reference=target,
                                common_times_ns=common)
        print(case,'done',len(common),'common ticks',flush=True)
    dump(out/'results.json',records)
    table=[]
    for r in records:
        p=r['native_path'];s=r['paired_speed'];event=r['event']
        table.append(dict(method=r['method'],case=r['case'],rmse_mps=s.get('rmse'),mae_mps=s.get('mae'),
                          bias_mps=s.get('bias'),event_rmse_mps=event.get('rmse') if event else None,
                          path_rmse_m=p['reanchored_span_rmse_m'],terminal_error_m=p['full_span_terminal_error_m'],
                          recovery_s=r['recovery_s'],false_zero=r['false_zero_samples'],outputs=r['outputs'],
                          common_samples=s['n'],p95_step_us=r['runtime']['step_p95_us']))
    with (out/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=table[0].keys());writer.writeheader();writer.writerows(table)
    dump(out/'environment.json',dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
        elapsed_s=time.time()-start,peak_rss_process_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        memory_limit_enforced=False,ros_executed=False,methods=len(METHODS),cases=len(plan),executions=len(records)))
    return records

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)

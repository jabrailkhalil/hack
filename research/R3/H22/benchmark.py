"""AB/BA development microbenchmark; not installed ROS timing or node RSS."""
import argparse
import hashlib
import json
import resource
from pathlib import Path
import time
import numpy as np
import data as d
import evaluation as q


def measured_step(rows,theta):
    o=d.observer(theta);outputs=[];cpu=wall=0.;n=0
    begin=rows[0][0]
    for t,held in rows:
        if t-begin>=10.:
            c=time.process_time_ns();w=time.perf_counter_ns();e=o.step(t,*held)
            wall+=time.perf_counter_ns()-w;cpu+=time.process_time_ns()-c;n+=1
        else:e=o.step(t,*held)
        outputs.append((e.t,e.v,e.s))
    a=np.array(outputs)
    return dict(cpu_us_per_output=cpu/1000/n,wall_us_per_output=wall/1000/n,outputs=n,
        output_sha256=hashlib.sha256(a.tobytes()).hexdigest())


def measured_replay(events,theta):
    tl=d.Timeline(d.observer(theta),rate_hz=20.,delay_s=0.);outputs=[];cpu=wall=0.;n=0
    begin=events[0,0]
    for t,ch,value in events:
        timed=t-begin>=10.
        if timed:c=time.process_time_ns();w=time.perf_counter_ns()
        tl.ingest(int(ch),d.Sample(float(t),float(value)))
        batch=[(e.t,e.v,e.s) for e,held in tl.advance()];outputs.extend(batch)
        if timed:
            wall+=time.perf_counter_ns()-w;cpu+=time.process_time_ns()-c;n+=len(batch)
    return dict(cpu_us_per_output=cpu/1000/n,wall_us_per_output=wall/1000/n,outputs=n,
        output_sha256=hashlib.sha256(np.asarray(outputs).tobytes()).hexdigest())


def run(output,training):
    out=d.new_dir(output);selection=json.loads((training/'selection.json').read_text())
    chosen=selection['selected'];path=training/(chosen+'.json')
    assert d.sha(path)==selection['candidate_sha256']
    theta=np.array(json.loads(path.read_text())['theta']);store=d.Store(out/'access.json')
    events,_=store.load('30618_0652866c','development')
    events=events[events[:,0]<=events[0,0]+70.];rows=d.input_ticks(events)
    raw=[]
    for mode,fun,stream in [('step',measured_step,rows),('replay',measured_replay,events)]:
        for pair in range(6):
            order=['main','candidate'] if pair%2==0 else ['candidate','main']
            for name in order:
                result=fun(stream,None if name=='main' else theta)
                raw.append(dict(mode=mode,pair=pair,order=order,model=name,**result))
    summary={}
    for mode in ['step','replay']:
        summary[mode]={}
        for name in ['main','candidate']:
            selected=[r for r in raw if r['mode']==mode and r['model']==name]
            assert len({r['output_sha256'] for r in selected})==1
            summary[mode][name]={key:float(np.median([r[key] for r in selected])) for key in ['cpu_us_per_output','wall_us_per_output']}
    result=dict(**d.provenance('benchmark'),selected=chosen,bag='30618_0652866c',warmup_s=10,measured_s=60,pairs_per_mode=6,
        summary=summary,repeats=raw,process_highwater_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        rss_scope='whole Python research process, not per-model ROS node RSS',installed_enabled_ros_measured=False)
    d.save(out/'cost.json',result);print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--training',type=Path,required=True)
    a=p.parse_args();run(a.output,a.training)

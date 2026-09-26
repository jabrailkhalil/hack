"""Paired step CPU and offline replay cost, not ROS latency or node RSS."""
import argparse
from collections import defaultdict
import statistics
import time
from common import *
from run import candidate
from reserve_odometry.timeline import Timeline


def median(rows,key):return statistics.median(r[key] for r in rows)

def step_run(factory,inputs,labels):
    o=factory();output=[];phase_ns=defaultdict(int);phase_count=defaultdict(int)
    wall=time.perf_counter();cpu=time.process_time()
    for args,label in zip(inputs,labels):
        start=time.process_time_ns();e=o.step(*args);end=time.process_time_ns()
        phase_ns[label]+=end-start;phase_count[label]+=1
        output.append((e.v,e.s))
    return dict(wall_s=time.perf_counter()-wall,cpu_s=time.process_time()-cpu,outputs=len(output),
                step_cpu_ns=dict(phase_ns),phase_outputs=dict(phase_count))


def main(out):
    out.mkdir(parents=True,exist_ok=False);store=Store(out/'access.json')
    bag=store.plan['splits']['development'][0];events,_=store.load(bag,'development')
    tl=Timeline(baseline(),rate_hz=20.,delay_s=0.);inputs=[]
    for t,ch,value in events:
        tl.ingest(int(ch),Sample(float(t),float(value)))
        for e,held in tl.advance():inputs.append((e.t,*held))
    if tl.resets:raise ValueError('Benchmark requires continuous timeline')
    result=dict(bag=bag,source=os.environ.get('GITHUB_SHA'),baseline=BASE,ops=OPS,step={},replay={},
                qualifier='single development bag; paired offline timing incl timer overhead; not ROS latency/RSS')
    start_t=inputs[0][0]
    outage=[(t,u,None,None) if 5.<=((t-start_t)%20.)<11. else (t,u,f,r) for t,u,f,r in inputs]
    for label,data in [('natural',inputs),('engineered_outage',outage)]:
        probe=candidate();labels=[]
        for args in data:probe.step(*args);labels.append(probe.phase)
        for factory in (baseline,candidate):step_run(factory,data,labels)  # discarded warm-up
        rows={'baseline':[],'candidate':[]}
        for order in [('baseline','candidate'),('candidate','baseline')]*2:
            for name in order:rows[name].append(step_run(baseline if name=='baseline' else candidate,data,labels))
        result['step'][label]=dict(order='AB BA AB BA',raw=rows,median={})
        for name,rs in rows.items():
            phases={k:dict(outputs=rs[0]['phase_outputs'][k],cpu_us_per_step=statistics.median(r['step_cpu_ns'][k]/r['phase_outputs'][k]/1000 for r in rs)) for k in rs[0]['step_cpu_ns']}
            result['step'][label]['median'][name]=dict(wall_s=median(rs,'wall_s'),cpu_s=median(rs,'cpu_s'),phases=phases)
    cfg=profile()[0]
    for fac in (baseline,candidate):gc.predict(events,(fac,cfg))
    replay={'baseline':[],'candidate':[]}
    for order in [('baseline','candidate'),('candidate','baseline')]*2:
        for name in order:
            t=time.perf_counter();p=time.process_time();a,info=gc.predict(events,(baseline if name=='baseline' else candidate,cfg))
            replay[name].append(dict(wall_s=time.perf_counter()-t,cpu_s=time.process_time()-p,outputs=len(a),causal_errors=info['causal_errors']))
    result['replay']=dict(raw=replay,median={n:{k:median(v,k) for k in ('wall_s','cpu_s')} for n,v in replay.items()})
    save(out/'cost.json',result);print(json.dumps(result['replay']['median'],indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);main(p.parse_args().output)

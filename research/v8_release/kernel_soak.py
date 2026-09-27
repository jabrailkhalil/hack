"""Installed-wheel kernel soak, NOT a ROS, end-to-end latency, or accuracy test.

The unchanged v8 and the frozen selected profile consume generated faults for
six accelerated source-time hours. Two-CPU affinity and a 500 MB address-space
limit apply to THIS Python process, not to Docker, DDS or a ROS graph.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rss_bytes():
    return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')


def run(installed, output, hours=6, pattern="healthy"):
    if pattern not in ("healthy", "faults"):
        raise ValueError("Unknown synthetic pattern")
    installed = Path(installed).resolve()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    os.sched_setaffinity(0, set(cpus))
    resource.setrlimit(resource.RLIMIT_AS, (500_000_000, 500_000_000))
    sys.path.insert(0, str(installed))
    from reserve_odometry import core, guarded_readout, timeline
    modules = (core, guarded_readout, timeline)
    pins = json.loads((ROOT/'research/v8_targeted/BASELINE_PINS.json').read_text())
    for module in modules:
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(installed), path
        assert sha(path) == pins['src/reserve_odometry/reserve_odometry/'+path.name], path
    freeze = json.loads((ROOT/'research/v8_targeted/FREEZE.json').read_text())
    for name, expected in freeze['source_sha256'].items():
        assert sha(ROOT/'research/v8_targeted'/name) == expected, name
    baseline = json.loads((ROOT/'src/reserve_odometry/config/champion_v8.json').read_text())
    selected = json.loads((ROOT/'research/v8_targeted/selected.json').read_text())
    observers = {name: guarded_readout.GuardedReadoutObserver(core.Config(**doc['config']),
                 readout=guarded_readout.ReadoutConfig(**doc['readout']))
                 for name, doc in [('main', baseline), ('candidate', selected)]}
    # Third independent factory checks selected state/output determinism throughout.
    shadow = guarded_readout.GuardedReadoutObserver(core.Config(**selected['config']),
              readout=guarded_readout.ReadoutConfig(**selected['readout']))
    ticks = int(hours*3600*20)+1
    metadata = dict(kind='synthetic_installed_kernel', pattern=pattern, hours=hours, ticks_per_profile=ticks,
        cpu_affinity=cpus, address_space_limit_bytes=500_000_000, python=platform.python_version(),
        source_sha256=sha(__file__), source_modules={m.__name__:sha(m.__file__) for m in modules},
        selected_config=asdict(observers['candidate'].c), official_accuracy=False,
        ROS=False, realtime_wall_clock=False)
    (output/'STARTED.json').write_text(json.dumps(metadata,indent=2)+'\n')
    previous = {}; modes = {n:Counter() for n in observers}; durations = {n:[] for n in observers}
    max_integral_error = {n:0.0 for n in observers}
    healthy_max_error = {n:0.0 for n in observers}
    held = [None,None]; memory = []; started = time.perf_counter(); scenarios = Counter()
    for i in range(ticks):
        t = i*.05; phase=t%180; velocity=5+3*math.sin(t/20)
        u=.3 if math.cos(t/20)>.3 else (-.2 if math.cos(t/20)<-.3 else 0.)
        if i%2==0: held=[core.Sample(t-.025,velocity),core.Sample(t-.02,velocity+.005)]
        f,r=held; command=core.Sample(t,u); label='healthy'
        if pattern == "faults":
            if 35<=phase<50: f=None;label='front_dropout'
            elif 50<=phase<65: r=None;label='rear_dropout'
            elif 65<=phase<85: f=r=None;label='wheels_dropout'
            elif 85<=phase<100: f=r=command=None;label='all_inputs_dropout'
            elif 100<=phase<105: f=r=core.Sample(t,0.);label='zero_lock'
            elif 110<=phase<112: f=core.Sample(t,velocity+10);r=core.Sample(t,velocity-10);label='disagreement'
            elif 120<=phase<123: f=r=core.Sample(t,velocity+5);label='common_jump'
            elif 125<=phase<128: f=r=core.Sample(t+1,velocity);label='future'
            elif 130<=phase<133: f=core.Sample(t,float('nan'));r=core.Sample(t,float('inf'));label='nonfinite'
            elif 135<=phase<138: f=r=core.Sample(t-phase+135,4.);label='duplicates'
            elif 145<=phase<155: f=r=core.Sample(t,velocity+.8*(phase-145));label='slow_common'
        scenarios[label]+=1
        for name, observer in observers.items():
            timer=time.perf_counter_ns() if i%100==0 else None
            estimate=observer.step(t,command,f,r)
            if timer is not None:durations[name].append(time.perf_counter_ns()-timer)
            modes[name][estimate.mode]+=1
            if pattern == 'healthy' and t >= 5:
                healthy_max_error[name]=max(healthy_max_error[name],abs(estimate.v-velocity))
                assert abs(estimate.v-velocity)<.15, (name, t, estimate.v, velocity)
            assert all(math.isfinite(getattr(estimate,k)) for k in ('t','v','s','a','variance_v','variance_s','disturbance'))
            assert abs(estimate.v)<=observer.c.max_speed_mps+1e-12
            assert abs(estimate.disturbance)<=observer.c.disturbance_limit_mps2+1e-12
            if name in previous:
                p=previous[name];error=abs(estimate.s-p.s-.5*(estimate.v+p.v)*(estimate.t-p.t))
                max_integral_error[name]=max(error,max_integral_error[name]);assert error<1e-7
            previous[name]=estimate
            for value in vars(observer).values():
                if isinstance(value,(list,tuple,dict)):assert len(value)<=8
        assert shadow.step(t,command,f,r)==previous['candidate']
        assert vars(shadow)==vars(observers['candidate'])
        if i%1200==0:memory.append(dict(t=t,rss_bytes=rss_bytes()))
    for name, observer in observers.items():
        observer.reset(velocity=4,position=12)
        doc=baseline if name=='main' else selected
        fresh=guarded_readout.GuardedReadoutObserver(core.Config(**doc['config']),readout=guarded_readout.ReadoutConfig(**doc['readout']))
        fresh.reset(velocity=4,position=12);assert vars(observer)==vars(fresh)
    def percentile(values, q):
        values=sorted(values);return values[round((len(values)-1)*q)]/1000
    result=dict(metadata,status='INVARIANTS_PASS',wall_seconds=time.perf_counter()-started,
        actual_observer_calls=ticks*3, independent_selected_parity=True, reset_parity=True,
        max_integral_error_m=max_integral_error,scenarios=dict(scenarios),
        healthy_speed_max_error_mps=healthy_max_error if pattern=='healthy' else None,
        recovery_certified=False,
        modes={k:dict(v) for k,v in modes.items()},max_rss_bytes=max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,max(m['rss_bytes'] for m in memory)),
        rss_samples=memory,step_sample_every_ticks=100,
        step_microseconds={k:dict(p50=percentile(v,.5),p95=percentile(v,.95),p99=percentile(v,.99),max=max(v)/1000) for k,v in durations.items()})
    (output/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rss_samples'},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installed',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--hours',type=int,choices=range(1,25),default=6)
    p.add_argument('--pattern',choices=['healthy','faults'],default='healthy')
    a=p.parse_args();run(a.installed,a.output,a.hours,a.pattern)

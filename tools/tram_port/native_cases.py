"""Eventized upstream behavioral fixtures; no our synthetic plant is imported.

Reference curves come from the speed values/assertions of hack/tests/test_core.py
and the explicitly prescribed speed in test_guarded_readout.py::stream.
These are synthetic fixtures, NOT extracted real tram recordings. Eventization
feeds command/front/rear individually to native Timeline, unlike direct step()
in upstream unit tests. This difference is deliberate and documented.
"""
import importlib.util
from pathlib import Path
import sys
import numpy as np


def eventize(rows):
    events=[];reference=[]
    for t,command,front,rear,truth in rows:
        for ch,sample in enumerate((command,front,rear)):
            if sample is not None: events.append((sample.t,ch,sample.value))
        reference.append((t,truth))
    return np.asarray(events,dtype=float).reshape(-1,3),reference


def fixtures():
    from reserve_odometry.core import Sample
    from collections import OrderedDict
    cases=OrderedDict()
    def add(name,rows,fault=None,group='constant'):
        events,refs=eventize(rows)
        cases[name]={'events':events,'reference':refs,'fault':fault,'group':group}
    def fixed(duration,dt,command,speed,corrupt=None):
        for i in range(round(duration/dt)+1):
            t=i*dt;f=r=Sample(t,speed)
            if corrupt is not None:f,r=corrupt(t,i,f,r)
            yield t,Sample(t,command),f,r,speed
    add('constant_speed',fixed(10.,.02,.1,5.))
    # Original stationary fixture uses zero-order-held stamps at 10 Hz.
    add('stationary',((i*.02,Sample((i//5)*.1,-.5),Sample((i//5)*.1,0.),Sample((i//5)*.1,0.),0.) for i in range(501)),group='stationary')
    add('single_wheel_slip',fixed(15.,.02,.1,5.,lambda t,i,f,r:(Sample(t,13 if 3<t<8 else 5),r)),(3.,8.))
    add('simultaneous_spike',fixed(2.,.02,.1,5.,lambda t,i,f,r:(Sample(t,15 if i==70 else 5),)*2),(1.4,1.42))
    add('short_common_offset',fixed(2.,.02,0.,5.,lambda t,i,f,r:(Sample(t,10 if 1<=t<1.6 else 5),)*2),(1.,1.6))
    add('quarantine_common_offset',fixed(5.,.02,0.,5.,lambda t,i,f,r:(Sample(t,10 if 2<=t<3.2 else 5),)*2),(2.,3.2))
    # Exact time/measurement generation of the upstream dropout matrix.
    for missing in ('front','both'):
        for duration in (.1,.5,2.,5.,10.):
            rows=[];t=0.
            while t<=1.+1e-9:
                rows.append((t,Sample(t,0),Sample(t,5),Sample(t,5),5.));t+=.02
            begin=t;end=t+duration
            while t<end-1e-9:
                rows.append((t,Sample(t,0),None,None if missing=='both' else Sample(t,5),5.));t+=.02
            recovery_end=t+3
            while t<recovery_end-1e-9:
                rows.append((t,Sample(t,0),Sample(t,5),Sample(t,5),5.));t+=.02
            add(f'drop_{missing}_{duration:g}s',rows,(begin,end))
    # Reuse the upstream iterator rather than rewriting its fault schedule.
    root=Path(__file__).resolve().parent/'vendor/hack'
    sys.path.insert(0,str(root/'tests'))
    spec=importlib.util.spec_from_file_location('upstream_guarded_tests',root/'tests/test_guarded_readout.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    original=list(mod.GuardedReadoutTests().stream())
    def truth(t):return max(.1,3+.15*t if t<10 else 4.5-.1*(t-10))
    add('guarded_stream_faults',((t,c,f,r,truth(t)) for t,c,f,r in original),group='piecewise_ramp')
    # Clean counterpart removes injected faults, keeps the identical upstream law,
    # wheel timing/noise using the same deterministic random source (seed 781).
    import random
    rng=random.Random(781);held=[None,None];rows=[]
    for i in range(601):
        t=i*.05;u=.4 if t<10 else -.15;v=truth(t)
        if i%2==0:held=[Sample(t-.025,v+rng.uniform(-.01,.01)) for _ in range(2)]
        rows.append((t,Sample(t,u),*held,v))
    add('guarded_stream_clean',rows,group='piecewise_ramp')
    # Entry into low-speed lock: upstream test's 1 m/s coasting assumption,
    # with one second of wheel initialization for all APIs instead of reset(v=1).
    add('low_speed_lock',fixed(3.,.05,0.,1.,lambda t,i,f,r:(Sample(t,0. if 1<=t<2 else 1.),)*2),(1.,2.),'low_speed')
    return cases

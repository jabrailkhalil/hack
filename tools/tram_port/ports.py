"""Port our frozen Estimator API to the native hack Observer.step contract.

Only this adapter changes. There is no retuning of either party's models.
Native Timeline determines which held samples the port can access on each tick.
The native loader lacks receipt timestamps: received_ns is the current native
output tick at which a new held sample becomes visible. This is not a model of
real transport latency. Use arrival-clock comparisons for that separate question.
"""
from pathlib import Path
from dataclasses import replace
import json
import math
import time
import numpy as np
from reserve_odometry.core import Config, Estimate
from tram_lab.types import Event, COMMAND, FRONT, REAR
from tram_lab.estimators import WheelEstimator
from tram_lab.hypotheses.concept_a import RobustEstimator
from tram_lab.hypotheses.concept_b import AdaptiveEKF
from tram_lab.hypotheses.concept_c import ResidualEKF

ROOT=Path(__file__).resolve().parent
MODEL=json.loads((ROOT/'vendor/ours/research/model.json').read_text())


def our_factory(name):
    if name in ('front','rear','mean'):
        return WheelEstimator({'name':name})
    config={'dynamics':MODEL['dynamics']}
    if name=='A': return RobustEstimator(config)
    if name=='B': return AdaptiveEKF(config)
    if name=='C':
        config['residual_model']=MODEL['residual']
        return ResidualEKF(config)
    if name=='H1_10':
        from research2.h01 import Estimator
        return Estimator(dict(config,age_transport=True,physics=False))
    if name=='H2_050':
        from research2.h02 import Estimator
        return Estimator(dict(config,history_s=.5))
    raise ValueError(name)


class OurObserver:
    """Native public facade. It intentionally does not emulate private EKF fields."""
    def __init__(self,name,config=None):
        self.name=name
        # Same ingress/scheduling envelope for ALL models in hack Timeline.
        self.c=config or Config()
        self.reset()

    def reset(self,*,velocity=None,position=0.0):
        if velocity is not None or position != 0:
            raise ValueError('Frozen our API has no external initialization; use wheel startup')
        self.inner=our_factory(self.name)
        self.t=None
        self.keys=[None,None,None]
        self.sequence=0
        self.samples_seen=[]
        self.latencies_ns=[]
        self.last_estimate=None

    def step(self,t,command=None,front=None,rear=None):
        start=time.perf_counter_ns()
        if not math.isfinite(t) or (self.t is not None and t<=self.t):
            raise ValueError('Native time must increase; reset after rollback')
        if self.t is not None and t-self.t>self.c.max_step_s+1e-9:
            raise ValueError('Native max_step_s exceeded')
        now=round(t*1e9)
        for channel,(topic,sample) in enumerate(zip((COMMAND,FRONT,REAR),(command,front,rear))):
            if sample is None:continue
            if sample.t>t+1e-9:raise ValueError('Native timeline exposed a future sample')
            key=(sample.t,sample.value)
            if key==self.keys[channel]:continue
            self.keys[channel]=key
            field='position' if channel==0 else 'velocity'
            # Conversion restores original raw units used by the frozen models.
            # Do not int-round u*15: preserved normalized commands may be fractional.
            value=sample.value*(15 if channel==0 else 3.6)
            event=Event(topic,round(sample.t*1e9),now,self.sequence,{field:value})
            self.sequence+=1
            self.inner.update(event)
        raw=self.inner.predict(now)
        self.t=t
        diag=raw.diagnostics
        if raw.velocity is None:
            mode='WAITING_FOR_INITIALIZATION';v=s=0.
        else:
            v=float(raw.velocity);s=float(raw.distance)
            native_mode=diag.get('mode')
            mode='STOPPED' if native_mode=='stop' else ('MODEL_ONLY' if native_mode=='model' else 'FUSED')
        a=0. if self.last_estimate is None else (v-self.last_estimate.v)/(t-self.last_estimate.t)
        var=float(diag.get('variance_v',0.))
        result=Estimate(t,s,v,a,var,0.,float(getattr(self.inner,'disturbance',0.)),mode,
                        'PORT_DIAGNOSTICS','PORT_DIAGNOSTICS',bool(diag.get('command_stale',False)))
        self.last_estimate=result
        self.latencies_ns.append(time.perf_counter_ns()-start)
        return result

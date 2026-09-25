"""Offline-only bitwise audit; no references or fault flags enter runtime."""
from dataclasses import asdict, fields, is_dataclass
import math
import struct
from build import load, config
from reserve_odometry.core import Config, Observer
from reserve_odometry.guarded_readout import GuardedReadoutObserver as Baseline, ReadoutConfig

CORE_KEYS = tuple(k for k in vars(Observer()) if k != 'last_estimate')
READOUT_KEYS = ('_velocity_correction','_distance_correction','_correction_sigma_s','_blocked_until')


def equal(a,b):
    if isinstance(a, float) or isinstance(b, float):
        return struct.pack('>d',a) == struct.pack('>d',b)
    if is_dataclass(a):
        return all(equal(getattr(a,f.name), getattr(b,f.name)) for f in fields(a))
    if isinstance(a,(tuple,list)):
        return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(a,dict):
        return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    return a==b


def check_inner(a,b):
    for k in CORE_KEYS:
        if not equal(getattr(a,k),getattr(b,k)):
            raise AssertionError('Core state differs: '+k)
    if not equal(a._blocked_until,b._blocked_until):
        raise AssertionError('Holdoff changed')


def check_off(a,b,ea,eb):
    check_inner(a,b)
    for k in READOUT_KEYS:
        if not equal(getattr(a,k),getattr(b,k)):
            raise AssertionError('Disabled v7 readout differs: '+k)
    if not equal(ea,eb):
        raise AssertionError('Disabled Estimate differs')
    if a._model_segments:
        raise AssertionError('Disabled history not empty')


Candidate = load().GuardedReadoutObserver
CandidateConfig = load().ReadoutConfig


class AuditedCandidate(Candidate):
    def __init__(self,c=None):
        c = c or config()
        self.reference = Baseline(Config(**asdict(c)))
        self.disabled = Candidate(Config(**asdict(c)), readout=CandidateConfig(integral_age=False))
        self.audit_ticks = 0
        self.audit_updates = 0
        self.audit_changed = 0
        self.audit_multisegment = 0
        self.audit_fallback = 0
        self.audit_max_delta = 0.
        self.audit_max_history = 0
        self.audit_last = None
        self.sink = None
        super().__init__(c,readout=CandidateConfig(integral_age=True))

    def reset(self,**kwargs):
        super().reset(**kwargs)
        self.reference.reset(**kwargs)
        self.disabled.reset(**kwargs)
        self.audit_last = None

    def _age_increment(self,t,accepted,acceleration,age):
        result=super()._age_increment(t,accepted,acceleration,age)
        integrals=[self._integral_between(min(t,s.t),t) for s in accepted]
        delta=result-acceleration*age
        multi=sum(right>min(s.t for s in accepted) for left,right,a in self._model_segments)>1
        self.audit_updates += 1
        self.audit_changed += abs(delta)>1e-9
        self.audit_multisegment += multi
        self.audit_fallback += any(x is None for x in integrals)
        self.audit_max_delta=max(self.audit_max_delta,abs(delta))
        self.audit_last=dict(t=t,mean_age=age,max_age=max(t-s.t for s in accepted),
            skew=abs(accepted[0].t-accepted[-1].t),current_acceleration=acceleration,
            original_increment=acceleration*age,integral_increment=result,increment_delta=delta,
            history_segments=len(self._model_segments),multisegment=multi,
            fallback=any(x is None for x in integrals))
        return result

    def step(self,*args,**kwargs):
        self.audit_last=None
        e=super().step(*args,**kwargs)
        b=self.reference.step(*args,**kwargs)
        off=self.disabled.step(*args,**kwargs)
        check_inner(self,self.reference)
        check_off(self.disabled,self.reference,off,b)
        self.audit_ticks+=1
        self.audit_max_history=max(self.audit_max_history,len(self._model_segments))
        assert len(self._model_segments)<=16
        if self._model_segments:
            assert self._model_segments[0][1]>e.t-self.c.max_age_s
        assert self.last_estimate is e
        assert all(math.isfinite(x) for x in (e.t,e.v,e.s,e.a,e.variance_v,e.variance_s))
        if self.sink is not None:
            self.sink(self,e,b,args)
        return e

    def stats(self):
        return dict(checked_ticks=self.audit_ticks,readout_updates=self.audit_updates,
            materially_changed_updates=self.audit_changed,multisegment_updates=self.audit_multisegment,
            fallback_updates=self.audit_fallback,max_increment_delta_mps=self.audit_max_delta,
            max_history_length=self.audit_max_history,bitwise_inner=True,disabled_exact=True)

"""Read-only causal instrumentation of the exact frozen v8 observer.

No candidate is defined here. Extra state is bounded and never read by v8.
All recovery times derived from injected fault boundaries are evaluator-only.
"""
import math
from reserve_odometry.core import clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver

COLUMNS = ['innovation', 'drive_a', 'd', 'P', 'gain', 'model_residual',
           'readout_delta', 'v_inner', 's_inner', 'wheel_a', 'trusted',
           'pair_accepted', 'fused_pair', 'healthy', 'trust_age', 'pair_count',
           's_readout', 'prediction', 'P_prior', 'front_code', 'rear_code']
STATUS = ['MISSING_OR_STALE','RANGE','DUPLICATE_OR_OLD','RATE_ANOMALY',
          'ZERO_LOCK_SUSPECT','MODEL_DISAGREEMENT','AMBIGUOUS_PAIR',
          'COMMON_MODE_QUARANTINE','ACCEPTED','REACQUIRE_ACCEPTED','CANDIDATE']

class InstrumentedObserver(GuardedReadoutObserver):
    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.diag_trust_since = None
        self.diag_pair_count = 0
        self.diag_previous_pair = None
        self.diag_wheel_a = math.nan
        self.diag_last_new_pair_t = None
        self.diag = [math.nan]*len(COLUMNS)
        self.diag_drive_before_stop = 0.0

    def _wheel(self, index, sample, t):
        # Core has propagated the actuator, but has not applied a stop reset yet.
        self.diag_drive_before_stop = self.drive_a
        return super()._wheel(index, sample, t)

    def step(self, t, command=None, front=None, rear=None):
        oldt, oldv, oldP, oldd = self.t, self.v, self.pv, self.disturbance
        e = super().step(t, command, front, rear)
        dt = t-oldt if oldt is not None else 0.0
        c=self.c
        model_a=clip(self.diag_drive_before_stop-self.resistance(oldv)+oldd,-c.max_accel_mps2,c.max_accel_mps2)
        predicted=clip(oldv+dt*model_a,-c.max_speed_mps,c.max_speed_mps)
        u=0.0 if e.command_stale else clip(command.value,-1,1)
        if u <= c.command_deadband and oldv*predicted < 0.0: predicted=0.0
        prior=oldP+c.process_noise_v*dt*(4.0 if e.command_stale else 1.0)
        samples=(front,rear);statuses=(e.front_status,e.rear_status)
        accepted=[s for s,z in zip(samples,statuses) if z=='ACCEPTED']
        pair_ok=(all(self._valid(s,t,c.max_age_s) for s in samples)
                 and abs(front.t-rear.t)<=c.pair_skew_s
                 and abs(front.value-rear.value)<=c.disagreement_mps)
        fused=e.mode=='FUSED' and len(accepted)==2
        pairaccepted=all(z in ('ACCEPTED','REACQUIRE_ACCEPTED') for z in statuses)
        healthy=(pair_ok and not e.command_stale
                 and all(z in ('ACCEPTED','DUPLICATE_OR_OLD') for z in statuses)
                 and e.mode not in ('REACQUIRING','STOPPED','WAITING_FOR_INITIALIZATION','INITIALIZED'))
        if not healthy:
            self.diag_trust_since=None;self.diag_pair_count=0
            self.diag_previous_pair=None;self.diag_wheel_a=math.nan
        else:
            if self.diag_trust_since is None:self.diag_trust_since=t
            if fused:
                tz=(front.t+rear.t)*.5; z=(front.value+rear.value)*.5
                if self.diag_previous_pair is not None:
                    pt,pz=self.diag_previous_pair
                    self.diag_wheel_a=(z-pz)/(tz-pt) if 0.05<=tz-pt<=c.max_age_s else math.nan
                self.diag_previous_pair=(tz,z)
                self.diag_last_new_pair_t=t
                self.diag_pair_count+=1
        trust_age=t-self.diag_trust_since if self.diag_trust_since is not None else 0.
        trusted=healthy and trust_age>=.5-1e-9 and self.diag_pair_count>=3
        # Actual scalar gain reconstructed from the very same R expression.
        innovation=math.nan;gain=math.nan
        if accepted and oldt is not None and e.mode not in ('INITIALIZED','WAITING_FOR_INITIALIZATION'):
            z=sum(s.value for s in accepted)/len(accepted);innovation=z-predicted
            R=c.wheel_sigma_mps**2*(1.0 if len(accepted)==2 and pair_ok else 4.0)
            R*=max(1.0,abs(innovation)/max(3*c.wheel_sigma_mps,1e-9))
            gain=prior/(prior+R)
            posterior=max(1e-8,(1-gain)**2*prior+gain*gain*R)
            if abs(posterior-self.pv)>1e-10:raise AssertionError('gain reconstruction differs')
        elif pair_ok:
            innovation=(front.value+rear.value)*.5-predicted
        ma=self.drive_a-self.resistance(self.v)+self.disturbance
        residual=ma-self.diag_wheel_a
        codes=[STATUS.index(z) if z in STATUS else -1 for z in statuses]
        self.diag=[innovation,self.drive_a,self.disturbance,self.pv,gain,residual,
                   e.v-self.v,self.v,self.s,self.diag_wheel_a,float(trusted),
                   float(pairaccepted),float(fused),float(healthy),trust_age,
                   float(self.diag_pair_count),self._distance_correction,predicted,prior,*codes]
        return e


def dynamical_state(observer):
    """Exact velocity-state equivalence; additive position envelopes excluded.

    Expired timestamps are retained verbatim, except expired quarantine/readout
    deadlines: only future comparisons consult them. Diagnostic state is ignored.
    """
    d={k:v for k,v in vars(observer).items() if not k.startswith('diag') and
       k not in ('s','sigma_s','_distance_correction','_correction_sigma_s','last_estimate')}
    for name in ('_blocked_until','reacquire_blocked_until'):
        d[name]=max(d[name],observer.t) if observer.t is not None else d[name]
    return {k:tuple(v) if isinstance(v,list) else v for k,v in d.items()}

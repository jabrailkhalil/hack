"""Single preregistered H30 candidate. Unchanged canonical files stay read-only."""
from collections import deque
from dataclasses import asdict
import difflib, hashlib, json, math, sys, types
from pathlib import Path
from joint import JointHistory
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'src/reserve_odometry/reserve_odometry'

def sources():
    core=(SOURCE/'core.py').read_text()
    anchor='        samples, statuses = [], []\n'
    assert core.count(anchor)==1
    core=core.replace(anchor,"        hook = getattr(self, '_h30_begin', None)\n        if hook is not None:\n            hook(t, predicted, p_prior, a_model, command_stale, previous_v, dt)\n"+anchor)
    anchor=('            gain = p_prior / (p_prior + r)\n'
            '            self.v += gain * residual\n'
            '            self.pv = max(1e-8, (1 - gain) ** 2 * p_prior + gain * gain * r)\n')
    assert core.count(anchor)==1
    core=core.replace(anchor,"            hook = getattr(self, '_h30_update', None)\n            native = hook(t, samples, accepted, agree, predicted, z, r) if hook is not None else None\n            if native is None:\n"+''.join('    '+s+'\n' for s in anchor.splitlines())+"            else:\n                self.v, self.pv = native\n")
    readout=(SOURCE/'guarded_readout.py').read_text()
    anchor='        if not healthy or t < self._blocked_until:\n'
    assert readout.count(anchor)==1
    readout=readout.replace(anchor,"        if not healthy or t < self._blocked_until or getattr(self, '_h30_skip_readout', False):\n")
    return {'core':core,'guarded_readout':readout}

def isolated():
    name='_r3_h30_native'
    if name in sys.modules:return sys.modules[name]
    package=types.ModuleType(name);package.__path__=[str(SOURCE)];sys.modules[name]=package
    for part,code in sources().items():
        mod=types.ModuleType(name+'.'+part);mod.__package__=name;mod.__file__=str(SOURCE/(part+'.py'))
        sys.modules[mod.__name__]=mod
        exec(compile(code,mod.__file__+'[R3-H30]','exec'),mod.__dict__);setattr(package,part,mod)
    return package
M=isolated()

class NativeTimeObserver(M.guarded_readout.GuardedReadoutObserver):
    def __init__(self,config=None,*,readout=None,enabled=True):
        self.enabled=bool(enabled)
        super().__init__(config,readout=readout)
    def reset(self,**kwargs):
        super().reset(**kwargs)
        self._h30_bank=None;self._h30_native=False;self._h30_skip_readout=False
        self._h30_stale=False;self._h30_old_t=None;self._h30_reason='reset'
        self._h30_last_seen=[None,None,None];self._h30_inputs=deque(maxlen=64)
        self._h30_diag=None
        self._h30_stats={k:0 for k in ('ticks','native_updates','material_updates','past_tick_updates',
          'fallback_updates','duplicate_veto','max_states','max_events','max_input_events','hard_resets')}
    def _inc(self,key,n=1):self._h30_stats[key]=min(2147483647,self._h30_stats[key]+n)
    def _h30_begin(self,t,predicted,p_prior,a_model,stale,old_v,dt):
        if not self.enabled:return
        self._h30_native=False;self._h30_diag=None;self._h30_stale=stale;self._h30_old_t=self.t
        self._h30_reason='no_native_update'
        if self.t is None or not self.initialized:return
        if (stale or abs(predicted)<=self.c.stop_model_speed_mps or abs(predicted)>=self.c.max_speed_mps
                or old_v*predicted<=0):
            self._h30_bank=None;self._h30_skip_readout=False;self._h30_reason='stale_or_nonlinear_boundary';return
        bank=self._h30_bank
        if bank is None or bank.times[-1]!=self.t:
            bank=JointHistory(self.t,old_v,self.pv,self.c.max_age_s);self._h30_bank=bank
        # One predictor transition, same q and marginal as the original core.
        bank.append(t,predicted,self.c.process_noise_v)
        bank.p[-1][-1]=p_prior
    def _fallback(self,reason):
        self._h30_reason=reason;self._h30_bank=None;self._h30_skip_readout=False
        self._inc('fallback_updates');return None
    def _h30_update(self,t,samples,accepted,agree,predicted,z,r):
        if not self.enabled:return None
        bank=self._h30_bank
        if bank is None:return self._fallback(self._h30_reason)
        if len(accepted)!=2 or not agree or abs(samples[0].t-samples[1].t)>1e-9:
            return self._fallback('single_or_skew_pair')
        tau=samples[0].t
        if t-tau<=1e-9:return self._fallback('zero_age_legacy_exact')
        if abs(z)<=self.c.stop_model_speed_mps:return self._fallback('near_zero_measurement')
        key=((0,samples[0].t),(1,samples[1].t))
        if key in [k for _,k in bank.events]:
            self._inc('duplicate_veto');return self._fallback('duplicate_evidence')
        if len(bank.events)>=bank.MAX_EVENTS or len(bank.events)+len(self._h30_inputs)+4>64:
            return self._fallback('event_limit')
        index=bank.index(tau)
        if index is None:return self._fallback('history_or_state_limit')
        residual=z-bank.means[index]
        native_r=self.c.wheel_sigma_mps**2*max(1.,abs(residual)/max(3*self.c.wheel_sigma_mps,1e-9))
        # Retain the original current-time hard gate; also disallow native-time
        # disagreement. This is a conservative veto, never a new acceptance.
        native_gate=min(self.c.innovation_cap_mps,self.c.innovation_floor_mps+3*math.sqrt(bank.p[index][index]+self.c.wheel_sigma_mps**2))
        if abs(residual)>native_gate:return self._fallback('native_model_disagreement')
        nv=bank.means[-1]+bank.p[-1][index]*residual/(bank.p[index][index]+native_r)
        if abs(nv)>=self.c.max_speed_mps or nv*predicted<=0 or abs(nv)<=self.c.stop_model_speed_mps:
            return self._fallback('native_nonlinear_boundary')
        prior=self.pv;legacy_v=predicted+prior/(prior+r)*(z-predicted)
        self.v,self.pv=bank.observe(index,z,native_r,key)
        self.pv=max(1e-8,self.pv);bank.p[-1][-1]=self.pv
        self._h30_native=True;self._h30_skip_readout=True;self._h30_reason='native'
        self._inc('native_updates')
        if abs(self.v-legacy_v)>1e-9:self._inc('material_updates')
        if self._h30_old_t is not None and tau<self._h30_old_t-1e-9:self._inc('past_tick_updates')
        self._h30_diag=dict(t=t,tau=tau,native_delta_v=self.v-legacy_v,native_r=native_r,
            original_r=r,past_tick=tau<self._h30_old_t-1e-9,state_slots=len(bank.times),event_slots=len(bank.events))
        return self.v,self.pv
    def _output(self,t,a,mode,statuses,stale):
        if self.enabled:
            self._inc('ticks')
            keep=(not stale and mode in ('FUSED','MODEL_ONLY') and
                  all(s in ('ACCEPTED','DUPLICATE_OR_OLD') for s in statuses))
            if not keep or (mode=='FUSED' and not self._h30_native):
                self._h30_bank=None;self._h30_skip_readout=False
                if not keep:self._inc('hard_resets')
            bank=self._h30_bank
            if bank is not None:
                # Stop/recovery and clamps may change the state after the hook.
                if abs(bank.means[-1]-self.v)>1e-12 or abs(bank.p[-1][-1]-self.pv)>1e-12:
                    self._h30_bank=None;self._h30_skip_readout=False;self._inc('hard_resets')
                else:
                    bank.means[-1]=self.v;bank.p[-1][-1]=self.pv
                    self._h30_stats['max_states']=max(self._h30_stats['max_states'],len(bank.times))
                    self._h30_stats['max_events']=max(self._h30_stats['max_events'],len(bank.events))
        return super()._output(t,a,mode,statuses,stale)
    def step(self,t,command=None,front=None,rear=None):
        estimate=super().step(t,command,front,rear)
        if self.enabled:
            self._h30_inputs=deque((event for event in self._h30_inputs
                if event[1]>=t-self.c.max_age_s-1e-9),maxlen=64)
            for ch,s in enumerate((command,front,rear)):
                if (s is not None and math.isfinite(s.t) and math.isfinite(s.value)
                    and 0<=t-s.t<=self.c.max_age_s and self._h30_last_seen[ch]!=s.t):
                    self._h30_last_seen[ch]=s.t;self._h30_inputs.append((ch,s.t,s.value,t))
            if self._h30_bank is not None and len(self._h30_bank.events)+len(self._h30_inputs)>64:
                self._h30_bank=None  # bounded accounting; next update uses conservative fallback
            self._h30_stats['max_input_events']=max(self._h30_stats['max_input_events'],len(self._h30_inputs))
        return estimate

def candidate(enabled=True):
    values={}
    for line in (SOURCE.parent/'config/champion_v8.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith(('model.','readout.')):values[k]=float(v)
    c={k[6:]:v for k,v in values.items() if k.startswith('model.')}
    r={k[8:]:v for k,v in values.items() if k.startswith('readout.')}
    return NativeTimeObserver(M.core.Config(**c),readout=M.guarded_readout.ReadoutConfig(**r),enabled=enabled)

def patch():
    return ''.join(''.join(difflib.unified_diff((SOURCE/(p+'.py')).read_text().splitlines(True),s.splitlines(True),
       fromfile='a/src/reserve_odometry/reserve_odometry/'+p+'.py',tofile='b/src/reserve_odometry/reserve_odometry/'+p+'.py')) for p,s in sources().items())
if __name__=='__main__':print(patch(),end='')

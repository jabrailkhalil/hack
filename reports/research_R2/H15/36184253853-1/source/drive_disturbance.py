"""H15: bounded drive-dependent disturbance during causally detected wheel loss.

Auxiliary wheel-derived regression is not a physical mass/grade estimate.
Only the core research patch invokes the hooks. Default runtime is unchanged.
"""
from collections import deque
from dataclasses import dataclass
import math
from .core import clip
from .guarded_readout import GuardedReadoutObserver


@dataclass(frozen=True)
class DriveCorrectionConfig:
    enabled: bool = True
    ridge: float = 0.04

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError('enabled must be boolean')
        if not math.isfinite(self.ridge) or self.ridge not in (0.01, 0.04):
            raise ValueError('Only the two preregistered ridge levels are supported')


class DriveDependentObserver(GuardedReadoutObserver):
    def __init__(self, config=None, *, correction=None, readout=None):
        self.correction = correction or DriveCorrectionConfig()
        super().__init__(config, readout=readout)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.history = deque(maxlen=40)
        self.loss = None
        self.gamma = 0.0
        self.intercept = 0.0
        self.condition = None
        self.drive_variance = 0.0
        self.fit_rmse = None
        self.fit_ok = False
        self.effective_d = self.disturbance
        self.stats = dict(trusted_points=0, fits=0, loss_sessions=0,
                          loss_fitted=0, effective_ticks=0, clipped_ticks=0,
                          stale_cancel=0, fit_rejected=0, gamma_saturated=0,
                          max_history=0)

    def _prune(self, t):
        while self.history and t-self.history[0][0] > 2.0:
            self.history.popleft()

    def _fit(self, t):
        self._prune(t)
        q=self.history; n=len(q)
        self.fit_ok=False; self.gamma=0.; self.condition=None
        if n<6 or q[-1][0]-q[0][0]<0.5 or t-q[-1][0]>0.5:
            return
        mx=sum(x for _,x,y in q)/n; my=sum(y for _,x,y in q)/n
        vx=sum((x-mx)**2 for _,x,y in q)/n
        cv=sum((x-mx)*(y-my) for _,x,y in q)/n
        self.drive_variance=vx
        # Gram/n for [1, drive/(1 m/s^2)], stable eigenvalue ratio.
        tr=1+mx*mx+vx
        hi=(tr+math.sqrt(max(0.,tr*tr-4*vx)))/2
        self.condition=hi*hi/vx if vx>0 else None
        if vx<0.0025 or self.condition is None or self.condition>1000:
            self.stats['fit_rejected']+=1
            return
        raw=cv/(vx+self.correction.ridge)
        gamma=clip(raw,-0.25,0.25)
        intercept=my-gamma*mx
        error=math.sqrt(sum((y-intercept-gamma*x)**2 for _,x,y in q)/n)
        self.fit_rmse=error
        if not all(math.isfinite(x) for x in (gamma,intercept,error)) or error>0.5:
            self.stats['fit_rejected']+=1
            return
        self.gamma=gamma
        self.intercept=clip(intercept,-self.c.disturbance_limit_mps2,self.c.disturbance_limit_mps2)
        self.fit_ok=True
        self.stats['fits']+=1
        self.stats['gamma_saturated']+=int(raw!=gamma)

    def _h15_observe(self,t,tz,z,desired,samples,predicted):
        if not self.correction.enabled or self.loss is not None:
            return
        f,r=samples
        if (abs(z)<=1 or max(t-f.t,t-r.t)>0.20 or abs(f.t-r.t)>0.05
                or abs(f.value-r.value)>0.15 or abs(z-predicted)>0.6
                or abs(desired)>1.2
                or not all(math.isfinite(x) for x in (tz,z,desired,self.drive_a))):
            return
        if self.history and tz<=self.history[-1][0]:
            return
        self.history.append((tz,self.drive_a,desired))
        self.stats['trusted_points']+=1
        self.stats['max_history']=max(self.stats['max_history'],len(self.history))
        self._fit(t)

    def _h15_prediction(self,t,command_stale,accepted,statuses):
        self.effective_d=self.disturbance
        if not self.correction.enabled:
            return self.disturbance
        self._prune(t)
        if accepted:
            if self.loss is not None or len(accepted)!=2 or command_stale:
                self.history.clear(); self.fit_ok=False; self.gamma=0.
            self.loss=None
            return self.disturbance
        genuine_loss=any(s!='DUPLICATE_OR_OLD' for s in statuses)
        if self.loss is None and genuine_loss:
            self._fit(t)
            g=self.gamma if self.fit_ok and not command_stale else 0.
            self.loss=(self.disturbance,self.drive_a,g)
            self.stats['loss_sessions']+=1
            self.stats['loss_fitted']+=int(g!=0.)
            self.history.clear()
        if self.loss is None:
            return self.disturbance
        d0,x0,g=self.loss
        if command_stale:
            self.stats['stale_cancel']+=int(g!=0.)
            g=0.; self.loss=(d0,x0,0.)
        raw=d0+g*(self.drive_a-x0)
        effective=clip(raw,-self.c.disturbance_limit_mps2,self.c.disturbance_limit_mps2)
        self.stats['clipped_ticks']+=int(raw!=effective)
        self.stats['effective_ticks']+=int(abs(effective-d0)>1e-6)
        self.effective_d=effective
        return effective

    def _output(self,t,a,mode,statuses,command_stale):
        if mode in ('STOPPED','REACQUIRING','INITIALIZED','WAITING_FOR_INITIALIZATION'):
            self.loss=None; self.history.clear(); self.fit_ok=False; self.gamma=0.
        return super()._output(t,a,mode,statuses,command_stale)

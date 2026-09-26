"""Preregistered v8-only foundation. No candidate runtime or reference input."""
import argparse, collections, hashlib, json, math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import common as cm
from common import np
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from reserve_odometry.core import clip

class Diagnostic(GuardedReadoutObserver):
    def reset(self, **kw):
        super().reset(**kw)
        self.counts=collections.Counter(); self.seconds=0.; self.maximum=0.; self.total_delta=0.
        self.previous_potential=False; self.episode_length=0.; self.longest_episode=0.
    def step(self,t,command=None,front=None,rear=None):
        dt=0. if self.t is None else t-self.t
        v,d=self.v,self.disturbance; initialized=self.initialized
        valid=self._valid(command,t,self.c.command_timeout_s)
        stale=not valid or abs(command.value)>1.000001
        u=0. if stale else clip(command.value,-1,1)
        drive=self.drive_a+(1-math.exp(-dt/self.c.actuator_tau_s))*(self.drive_target(u,v)-self.drive_a)
        old_a=clip(drive-self.resistance(v)+d,-self.c.max_accel_mps2,self.c.max_accel_mps2)
        old=clip(v+dt*old_a,-self.c.max_speed_mps,self.c.max_speed_mps)
        r0=self.c.rolling_force_n/self.c.mass_kg
        q=self.c.quadratic_drag_n_s2_m2*v*abs(v)/self.c.mass_kg
        free=v+dt*(drive+d-q)
        prox=math.copysign(max(abs(free)-dt*r0,0.),free)
        if dt>0:prox=clip(v+dt*clip((prox-v)/dt,-self.c.max_accel_mps2,self.c.max_accel_mps2),-self.c.max_speed_mps,self.c.max_speed_mps)
        if u<=self.c.command_deadband:
            if v*old<0:old=0.
            if v*prox<0:prox=0.
        out=super().step(t,command,front,rear)
        diff=abs(prox-old)
        self.counts['ticks']+=1
        near=initialized and dt>0 and 0<abs(v)<=.5
        mo=out.mode=='MODEL_ONLY'
        if near:self.counts['near_zero_ticks']+=1
        if near and mo:self.counts['near_zero_model_only_ticks']+=1
        potential=near and mo and diff>=1e-4
        if potential:
            self.counts['potential_ticks']+=1;self.seconds+=dt;self.total_delta+=diff;self.maximum=max(self.maximum,diff)
            statuses=(out.front_status,out.rear_status)
            duplicate=all(s=='DUPLICATE_OR_OLD' for s in statuses)
            self.counts['duplicate_only_ticks' if duplicate else 'missing_or_rejected_ticks']+=1
            self.counts['force_below_r0' if abs(drive+d-q)<=r0 else 'force_above_r0']+=1
            self.counts['load_proxy_abs_d_ge_r0' if abs(d)>=r0 else 'load_proxy_abs_d_lt_r0']+=1
            zeros=all(self._valid(s,t,self.c.max_age_s) and abs(s.value)<self.c.stop_speed_mps for s in (front,rear))
            if zeros:self.counts['held_zero_proxy_ticks']+=1
            if not self.previous_potential:self.counts['episodes']+=1;self.episode_length=0.
            self.episode_length+=dt;self.longest_episode=max(self.longest_episode,self.episode_length)
        self.previous_potential=potential
        return out

def worker(arg):
    bag,outdir=arg
    events,_,group=cm.load(bag,outdir/'access'/(bag+'.json'),reference=False)
    c,r=cm.profile();diag=Diagnostic(c,readout=r)
    a,info=cm.predict(events,diag);b,baseinfo=cm.predict(events,cm.baseline())
    if not np.array_equal(a,b,equal_nan=True) or info!=baseinfo:raise AssertionError('Diagnostic altered baseline')
    row=dict(bag=bag,group=group,input_events=len(events),counts=dict(diag.counts),potential_seconds=diag.seconds,
       max_prediction_difference_mps=diag.maximum,sum_prediction_difference_mps=diag.total_delta,
       longest_episode_s=diag.longest_episode,baseline_array_sha256=hashlib.sha256(a.tobytes()).hexdigest(),
       runtime=info,baseline_exact=True,reference_loaded=False)
    cm.save(outdir/'bags'/(bag+'.json'),row)
    print(bag,'potential',diag.counts['potential_ticks'],flush=True)
    return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2);args=p.parse_args()
    cm.verify();args.output.mkdir(parents=True,exist_ok=False)
    bags=cm.ev.ex.Store().plan['splits']['development']
    with ProcessPoolExecutor(max_workers=args.workers) as pool:rows=list(pool.map(worker,[(b,args.output) for b in bags]))
    counts=collections.Counter();groups=collections.Counter()
    for r in rows:counts.update(r['counts']);groups[r['group']]+=r['counts'].get('potential_ticks',0)
    secs=sum(r['potential_seconds'] for r in rows)
    passed=counts['potential_ticks']>=100 and sum(n>=20 for n in groups.values())>=3 and secs>=5.
    result=dict(baseline_sha=cm.BASELINE,source_status='VERIFIED',role='development',reference_loaded=False,
      baseline_only=True,candidate_implemented=False,counts=dict(counts),groups=dict(groups),bags=len(rows),
      potential_seconds=secs,max_prediction_difference_mps=max(r['max_prediction_difference_mps'] for r in rows),
      gate=dict(ticks_min=100,groups_min=3,ticks_per_group_min=20,seconds_min=5.,delta_min_mps=1e-4),
      foundation_passed=passed,scientific_verdict='FOUNDATION_PASSED' if passed else 'INCONCLUSIVE',
      validation_opened=False,test_opened=False,per_bag=rows)
    cm.save(args.output/'FOUNDATION.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='per_bag'},indent=2),flush=True)
if __name__=='__main__':main()

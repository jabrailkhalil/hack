"""Baseline-only defect measurement; no H23 rollout, fitting or validation."""
import argparse,datetime,os
from collections import Counter
from common import *
class Probe(GuardedReadoutObserver):
    def __init__(self,c):
        self.last_trusted=None;self.rows=[];self.alt=Observer(alternate())
        super().__init__(c,readout=profile()[1])
    def step(self,t,command=None,front=None,rear=None):
        e=super().step(t,command,front,rear)
        sts=(e.front_status,e.rear_status)
        ts=[s.t for s,st in zip((front,rear),sts) if s is not None and st=='ACCEPTED']
        if ts:self.last_trusted=max(ts)
        absent=self.last_trusted is not None and t-self.last_trusted>self.c.max_age_s+1e-9
        allowed=all(s in ('MISSING_OR_STALE','DUPLICATE_OR_OLD','ZERO_LOCK_SUSPECT') for s in sts)
        eligible=absent and allowed and e.mode=='MODEL_ONLY' and not e.command_stale
        phase=0 if e.command_stale else (1 if command.value>self.c.command_deadband else -1 if command.value<-self.c.command_deadband else 0)
        a=clip(self.drive_a-self.resistance(self.v)+self.disturbance,-self.c.max_accel_mps2,self.c.max_accel_mps2)
        dreq=a-self.drive_a+self.alt.resistance(self.v)
        u=0. if e.command_stale else clip(command.value,-1,1)
        target_delta=self.alt.drive_target(u,self.v)-self.drive_target(u,self.v)
        self.rows.append((e.t,e.v,int(eligible),phase,dreq,target_delta,int(abs(dreq)<=self.c.disturbance_limit_mps2)))
        return e

def main(out):
    out.mkdir(parents=True,exist_ok=False);pins=integrity();store=Store(out/'access.json')
    save(out/'started.json',dict(source=os.environ.get('GITHUB_SHA'),baseline=BASE,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pins=pins,validation_opened=False))
    clean=[];stress=[];diagnostics=[]
    for bag in store.plan['splits']['development']:
        events,refs=store.load(bag,'development');group=store.records[bag]['group']
        cases=[('clean',None,events)]+[('original',f,w) for f,w in gc.fault_windows(events)]
        for kind,f,w in cases:
            probes=[]
            def factory(c):
                o=Probe(c);probes.append(o);return o
            row=dict(bag=bag,group=group,**score(w,refs,{'baseline_v2':factory,'balanced_physics':baseline},f))
            if f:row['fault']=f
            (clean if f is None else stress).append(row)
            for sm in row['receivers'].values():
                for key in ('rmse','mae','bias','n','coverage','false_stop_samples'):
                    assert sm['baseline_v2'][key]==sm['balanced_physics'][key]
            a=np.asarray(probes[0].rows,float);m=a[:,2]>0
            if f:m &= (a[:,0]>=f['start'])&(a[:,0]<f['end'])
            d=dict(bag=bag,group=group,kind=kind,fault=f,eligible_ticks=int(m.sum()),potential_episodes=int(np.sum(m&~np.r_[False,m[:-1]])),offset_admissible_ticks=int(np.sum(m&(a[:,6]>0))),phase_counts={str(p):int(np.sum(m&(a[:,3]==p))) for p in (-1,0,1)},reference={})
            d['max_abs_d_offset']=float(np.max(abs(a[m,4]))) if m.any() else None
            d['max_abs_drive_target_difference']=float(np.max(abs(a[m,5]))) if m.any() else None
            for receiver,values in refs.items():
                y=ev.ex.match(values,a[:,0]);d['reference'][receiver]=ev.ex.metrics(a[:,0],a[:,1],y,m&np.isfinite(y))
            diagnostics.append(d)
        save(out/'bags'/(bag+'.json'),dict(clean=clean[-1],stress=[r for r in stress if r['bag']==bag],diagnostics=[r for r in diagnostics if r['bag']==bag]))
        print('BASELINE',bag,flush=True)
    s=v6.summary(clean,stress,'baseline_v2')
    save(out/'results.json',dict(baseline=BASE,summary=s,clean=clean,stress=stress,diagnostics=diagnostics,alternative_rollout_evaluated=False,validation_opened=False,test_evaluated=False))
    print('BASELINE_SUMMARY',s,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args().output)

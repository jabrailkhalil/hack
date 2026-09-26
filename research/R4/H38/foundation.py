"""Baseline-only pre-update innovation diagnostics. No candidate trajectory."""
import argparse, json, math, datetime, sys, time
from pathlib import Path
from collections import defaultdict
from support import ROOT, ev, np, RoleStore, Config, ReadoutConfig, GuardedReadoutObserver, profile, OPS, clip, save, sha, BASELINE, TREE, PLAN_SHA
from scalar_rule import student_variance

COLUMNS=['time','residual','prior','R0','age','command','command_stable_s','model_a','inner_speed','legacy_R','nu4_R','nu8_R']

class Probe(GuardedReadoutObserver):
    def reset(self,**kwargs):
        super().reset(**kwargs);self.record=None;self._probe_u=None;self._probe_since=None
    def step(self,t,command=None,front=None,rear=None):
        old_t,old_v,old_pv,old_d=self.t,self.v,self.pv,self.disturbance
        result=super().step(t,command,front,rear)
        self.record=None
        u=0. if result.command_stale else clip(command.value,-1,1)
        if self._probe_u is None or u!=self._probe_u or result.command_stale:
            self._probe_since=t
        self._probe_u=u
        if old_t is None or result.mode not in ('FUSED','SINGLE_WHEEL'):return result
        dt=t-old_t
        a=clip(self.drive_a-self.resistance(old_v)+old_d,-self.c.max_accel_mps2,self.c.max_accel_mps2)
        pred=clip(old_v+dt*a,-self.c.max_speed_mps,self.c.max_speed_mps)
        if u<=self.c.command_deadband and old_v*pred<0:pred=0.
        accepted=[s for s,status in zip((front,rear),(result.front_status,result.rear_status)) if status=='ACCEPTED']
        r=sum(s.value for s in accepted)/len(accepted)-pred
        age=sum(max(0.,t-s.t) for s in accepted)/len(accepted)
        p=old_pv+self.c.process_noise_v*dt*(4. if result.command_stale else 1.)
        r0=self.c.wheel_sigma_mps**2*(1. if result.mode=='FUSED' else 4.)
        legacy=r0*max(1.,abs(r)/max(3*self.c.wheel_sigma_mps,1e-9))
        k=p/(p+legacy)
        if abs(self.v-(pred+k*r))>1e-11:raise AssertionError('Diagnostic does not match actual baseline correction')
        if result.command_stale:return result
        n4=student_variance(p,r0,r,4);n8=student_variance(p,r0,r,8)
        if n4 is None or n8 is None:raise AssertionError('Nonfinite prospective rule')
        self.record=(t,r,p,r0,age,u,t-self._probe_since,a,self.v,legacy,n4[0],n8[0])
        return result

def stats(a):
    if not len(a):return dict(n=0)
    r=a[:,1];z=r/np.sqrt(a[:,2]+a[:,3]);med=float(np.median(r))
    return dict(n=len(r),median_residual=med,mean_residual=float(np.mean(r)),
        abs_residual_quantiles=dict(zip(['50','90','95','99','99.9','100'],map(float,np.quantile(abs(r),[.5,.9,.95,.99,.999,1.])))),
        innovation_standardized_gt3=int(np.sum(abs(z)>3)),centered_innovation_standardized_gt3=int(np.sum(abs(r-med)/np.sqrt(a[:,2]+a[:,3])>3)),
        confidence_sigma_gt3=int(np.sum(abs(r)>3*np.sqrt(a[:,3]))),
        nu4_change_ge1pct=int(np.sum(abs(a[:,10]/a[:,9]-1)>=.01)),nu8_change_ge1pct=int(np.sum(abs(a[:,11]/a[:,9]-1)>=.01)))

def run(data_root,output):
    output.mkdir(parents=True,exist_ok=False);started=time.perf_counter();store=RoleStore(data_root);cfg,rd=profile()
    save(output/'started.json',dict(baseline_sha=BASELINE,baseline_tree=TREE,plan_commit=PLAN_SHA,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),candidate_trajectory_executed=False,validation_opened=False,test_opened=False,profile=cfg,readout=rd,script_sha256=sha(__file__),scalar_rule_sha256=sha(Path(__file__).with_name('scalar_rule.py'))))
    groups=defaultdict(list);perbag=[]
    for bag in store.plan['splits']['train']:
        events,refs=store.load(bag,'train');assert not any(refs.values())
        probe=Probe(Config(**cfg),readout=ReadoutConfig(**rd));old=ev.Observer
        ev.Observer=lambda c:probe
        # ev.replay always constructs this probe via the factory, without changing scorer.
        rows=[]
        step=probe.step
        def collect(*args,**kw):
            e=step(*args,**kw)
            if probe.record is not None:rows.append(probe.record)
            return e
        probe.step=collect
        try:pred,rt=ev.replay(events,Config(**cfg),OPS)
        finally:ev.Observer=old
        a=np.asarray(rows,float).reshape(-1,len(COLUMNS));group=store.records[bag]['group'];groups[group].append(a)
        np.savez_compressed(output/(bag+'.npz'),innovations=a)
        perbag.append(dict(bag=bag,group=group,**stats(a),runtime=rt,outputs=len(pred)))
        print('FOUNDATION',bag,len(a),flush=True)
    group_summary={};strata=[];foundation_count=0;foundation_groups=[];changed={4:0,8:0};changed_groups={4:[],8:[]}
    for group,parts in groups.items():
        a=np.concatenate(parts);group_summary[group]=stats(a)
        mask=(abs(a[:,1])>3*np.sqrt(a[:,3]))&(a[:,4]<=.1+1e-12)&(a[:,6]>=.5)
        n=int(np.sum(mask));foundation_count+=n
        if n:foundation_groups.append(group)
        for nu,col in [(4,10),(8,11)]:
            count=int(np.sum(mask&(abs(a[:,col]/a[:,9]-1)>=.01)));changed[nu]+=count
            if count:changed_groups[nu].append(group)
        mode=np.where(a[:,5]>.04,1,np.where(a[:,5]<-.04,-1,0))
        age=np.digitize(a[:,4],[.025,.05,.1])
        acc=np.digitize(abs(a[:,7]),[.1,.5])
        for m in (-1,0,1):
            for ag in range(4):
                for ac in range(3):
                    cell=a[(mode==m)&(age==ag)&(acc==ac)]
                    if len(cell):strata.append(dict(group=group,command_mode=m,age_bin=ag,accel_bin=ac,**stats(cell)))
    passed=(foundation_count>=100 and len(foundation_groups)>=3 and all(changed[n]>=100 and len(changed_groups[n])>=3 for n in (4,8)))
    result=dict(sufficient=passed,train_bags=len(perbag),accepted_updates=sum(r['n'] for r in perbag),foundation_subhard_cases=foundation_count,foundation_groups=foundation_groups,
      weight_changes_on_foundation=changed,changed_groups=changed_groups,requirements=dict(minimum_cases=100,minimum_groups=3,age_max=.1,stable_s=.5,tail_R0_sigmas=3),
      columns=COLUMNS,per_bag=perbag,per_group=group_summary,strata=strata,train_GNSS_opened=False,validation_opened=False,test_opened=False,
      verdict='FOUNDATION_SUFFICIENT_FOR_TEST' if passed else 'INCONCLUSIVE',elapsed_s=time.perf_counter()-started,
      interpretation='Pre-update innovations and prospective weights, NOT pure measurement noise, fitted Student likelihood, or candidate accuracy')
    save(output/'access.json',store.access);save(output/'foundation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('per_bag','per_group','strata','columns')},indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.data_root,a.output)

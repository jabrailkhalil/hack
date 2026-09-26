"""Preregistered train-only noise foundation. No runtime candidate or tuning.

Probe is passive: only the baseline computes/publishes Estimate. Offline sinks
can grow; no diagnostic target is fed back into any canonical state.
"""
import argparse
from collections import deque, Counter, defaultdict
from dataclasses import asdict
import csv
import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import struct
import time
from common import *
from numerics import GHistory, targets
from reserve_odometry.timeline import Timeline

COLUMNS = ['segment','t','dt','dz','y','residual_accel','raw_accel','differential_accel','steady',
           'endpoint_target','old_d','baseline_d','current_g','mean_g','skew','age','command',
           'gls20','ols20','var20','n20','gls40','ols40','var40','n40']
IDX = {k:i for i,k in enumerate(COLUMNS)}
PACK = struct.Struct('<7d?')


class Probe(GuardedReadoutObserver):
    def __init__(self,c=None):
        self.rows=[]
        super().__init__(c or profile()[0],readout=profile()[1])

    def reset(self,**kwargs):
        super().reset(**kwargs)
        self.history=GHistory();self.commands=deque(maxlen=64);self.pairs=deque(maxlen=7)
        self.segment=0;self.previous_pair=None;self.counts=Counter()

    def step(self,t,command=None,front=None,rear=None):
        old_t,old_v,old_d,old_adapt=self.t,self.v,self.disturbance,self.adapt_previous
        estimate=super().step(t,command,front,rear)
        self.counts['outputs']+=1
        if estimate.mode!='WAITING_FOR_INITIALIZATION':self.counts['published_outputs']+=1
        initialized=estimate.mode not in ('INITIALIZED','WAITING_FOR_INITIALIZATION','STOPPED')
        dt=0. if old_t is None else t-old_t
        u=0. if estimate.command_stale else clip(command.value,-1,1)
        g=self.drive_a-self.resistance(old_v)
        a=g+old_d
        raw_v=old_v+dt*clip(a,-self.c.max_accel_mps2,self.c.max_accel_mps2)
        clipped=(abs(a)>self.c.max_accel_mps2 or abs(raw_v)>self.c.max_speed_mps
                 or (u<=self.c.command_deadband and old_v*raw_v<0))
        self.history.add(t,g,initialized and not estimate.command_stale and not clipped)
        if estimate.command_stale:self.commands.clear()
        else:
            self.commands.append((t,u))
            while self.commands and t-self.commands[0][0]>2.+1e-9:self.commands.popleft()
        statuses=(estimate.front_status,estimate.rear_status)
        if estimate.mode=='FUSED' and not estimate.command_stale:
            tz=.5*(front.t+rear.t);z=.5*(front.value+rear.value);dif=front.value-rear.value
            new=(tz,z,dif)
            previous=self.previous_pair
            if old_adapt is None:
                self.pairs.clear();self.pairs.append(new);self.previous_pair=new;self.segment+=1
                return estimate
            delta=tz-old_adapt.t
            if delta<.05:return estimate  # original EMA eligibility; anchor not advanced
            measured=(z-old_adapt.value)/delta
            valid=(delta<=self.c.max_age_s and abs(measured)<=self.c.max_accel_mps2 and abs(z)>.5
                   and previous is not None and abs(previous[0]-old_adapt.t)<1e-9)
            if not valid:
                self.pairs.clear();self.pairs.append(new);self.previous_pair=new;self.segment+=1
                self.counts['ineligible_pairs']+=1
                return estimate
            self.counts['eligible_pairs']+=1
            try:
                ig=self.history.integral(old_adapt.t,tz)
            except ValueError:
                self.pairs.clear();self.pairs.append(new);self.previous_pair=new;self.segment+=1
                self.counts['history_fallbacks']+=1
                return estimate
            if not self.pairs or abs(self.pairs[-1][0]-old_adapt.t)>1e-9:
                self.pairs.clear();self.pairs.append(previous);self.segment+=1
            self.pairs.append(new)
            while self.pairs and tz-self.pairs[0][0]>.4+1e-9:self.pairs.popleft()
            steady=(.08<=delta<=.12 and abs(dif)<=.15 and abs(front.t-rear.t)<=.05
                    and len(self.commands)>1 and t-self.commands[0][0]>=2.-1e-9
                    and max(q[1] for q in self.commands)-min(q[1] for q in self.commands)<=.02+1e-12
                    and abs(self.drive_target(u,old_v)-self.drive_a)<=.1)
            y=z-old_adapt.value-ig
            row=[self.segment,tz,delta,z-old_adapt.value,y,y/delta,measured,
                 (dif-previous[2])/delta,float(steady),measured-self.drive_a+self.resistance(self.v),
                 old_d,self.disturbance,g,ig/delta,abs(front.t-rear.t),t-tz,u]
            for window in (.2,.4):
                ps=[p for p in self.pairs if tz-p[0]<=window+1e-9]
                vals=[float('nan')]*3+[len(ps)-1]
                if len(ps)>=3:
                    try:
                        ys=[b[1]-aa[1]-self.history.integral(aa[0],b[0]) for aa,b in zip(ps,ps[1:])]
                        vals=list(targets([p[0] for p in ps],ys,self.c.wheel_sigma_mps))+[len(ps)-1]
                    except ValueError:self.counts['window_fallbacks']+=1
                row.extend(vals)
            self.rows.append(row);self.previous_pair=new
        elif estimate.command_stale or estimate.mode in ('INITIALIZED','STOPPED') or any(s not in ('DUPLICATE_OR_OLD','ACCEPTED') for s in statuses):
            self.previous_pair=None;self.pairs.clear();self.segment+=1
        return estimate


def replay_probe(events,check=False):
    probe=Probe();tl=Timeline(probe,rate_hz=20.,delay_s=0.)
    ref=baseline() if check else None;digest=hashlib.sha256();n=0
    for t,ch,value in events:
        tl.ingest(int(ch),Sample(float(t),float(value)))
        for e,held in tl.advance():
            if tl.resets:raise AssertionError('Unexpected reset in foundation replay')
            if any(s is not None and s.t>e.t+1e-9 for s in held):raise AssertionError('Noncausal held input')
            if ref:
                other=ref.step(e.t,*held)
                if e!=other or any(vars(probe)[k]!=v for k,v in vars(ref).items()):
                    raise AssertionError('Passive probe changed canonical state or Estimate')
                n+=1
            digest.update(PACK.pack(e.t,e.s,e.v,e.a,e.variance_v,e.variance_s,e.disturbance,e.command_stale))
            digest.update((e.mode+'|'+e.front_status+'|'+e.rear_status+'\n').encode())
    return np.asarray(probe.rows,float).reshape(-1,len(COLUMNS)),dict(probe.counts),dict(
        full_state_checks=n,estimate_sha256=digest.hexdigest(),resets=tl.resets,dropped=tl.dropped,catchups=tl.catchup_events)


def segments(a,controlled):
    if not len(a):return
    good=np.ones(len(a),bool)
    if controlled:good=a[:,IDX['steady']]>0
    start=None
    for i in range(len(a)):
        adjacent=(i>0 and a[i,0]==a[i-1,0] and abs((a[i,1]-a[i-1,1])-a[i,2])<1e-8)
        if start is not None and (not good[i] or not adjacent):
            if i-start>=30:yield a[start:i]
            start=None
        if good[i] and start is None:start=i
    if start is not None and len(a)-start>=30:yield a[start:]


def pair_moments(x,y):
    return np.array([len(x),x.sum(),y.sum(),x@x,y@y,x@y],float)


def correlation(m):
    n,sx,sy,sxx,syy,sxy=m
    if n<2:return None
    vx,vy=sxx-sx*sx/n,syy-sy*sy/n
    return float((sxy-sx*sy/n)/math.sqrt(vx*vy)) if vx>1e-24 and vy>1e-24 else None


def moments(a,controlled):
    sums={kind:{'lag1':np.zeros(6),'lag2':np.zeros(6),'squared_increment':0.,'n':0} for kind in ['residual_accel','raw_accel','differential_accel']}
    nseg=0
    for block in segments(a,controlled):
        nseg+=1;dt=block[:,IDX['dt']]
        for kind,acc in sums.items():
            x=block[:,IDX[kind]];x=x-x.mean()
            acc['lag1']+=pair_moments(x[:-1],x[1:]);acc['lag2']+=pair_moments(x[:-2],x[2:])
            acc['squared_increment']+=float(np.sum((x*dt)**2));acc['n']+=len(x)
    return sums,nseg


def public(m,nseg):
    return dict(segments=nseg,**{kind:dict(samples=s['n'],lag1_pairs=int(s['lag1'][0]),lag2_pairs=int(s['lag2'][0]),
         lag1=correlation(s['lag1']),lag2=correlation(s['lag2']),
         sigma_proxy_mps=math.sqrt(s['squared_increment']/s['n']/2) if s['n'] else None,
         moments={k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in s.items()}) for kind,s in m.items()})


def summarize_arrays(arrays):
    result={}
    for label,controlled in [('all_trusted',False),('controlled',True)]:
        total=None;ns=0
        for a in arrays:
            m,n=moments(a,controlled);ns+=n
            if total is None:total=m
            else:
                for kind in m:
                    for k in m[kind]:total[kind][k]+=m[kind][k]
        result[label]=public(total,ns)
    windows={}
    for key in ['20','40']:
        errors=[];control=[];changes=0;n=0;two_var=[];vars_=[]
        for a in arrays:
            if not len(a):continue
            mask=np.isfinite(a[:,IDX['gls'+key]])
            g=a[mask,IDX['gls'+key]];o=a[mask,IDX['ols'+key]];e=a[mask,IDX['endpoint_target']]
            errors.extend((g-e).tolist());control.extend((g-o).tolist());changes+=int(np.sum(abs(g-o)>1e-6));n+=len(g)
            two_var.extend((.02/a[mask,IDX['dt']]**2).tolist());vars_.extend(a[mask,IDX['var'+key]].tolist())
        windows[key]=dict(targets=n,changed_vs_unweighted=changes,
            rms_target_change_vs_endpoint=math.sqrt(float(np.mean(np.square(errors)))) if n else None,
            rms_target_change_vs_unweighted=math.sqrt(float(np.mean(np.square(control)))) if n else None,
            modeled_variance_mean=float(np.mean(vars_)) if n else None,
            modeled_two_point_variance_mean=float(np.mean(two_var)) if n else None)
    return dict(**result,windows=windows)


def verdict(groups):
    qualifying={g:s for g,s in groups.items() if s['controlled']['residual_accel']['lag1_pairs']>=200}
    rows=[s['controlled']['residual_accel'] for s in qualifying.values()]
    n=sum(r['lag1_pairs'] for r in rows)
    support=sum(r['lag1'] is not None and -.75<=r['lag1']<=-.1 and r['sigma_proxy_mps']>=.001 for r in rows)
    rhos=[r['lag1'] for r in rows if r['lag1'] is not None];lag2=[abs(r['lag2']) for r in rows if r['lag2'] is not None]
    median=float(np.median(rhos)) if rhos else None;m2=float(np.median(lag2)) if lag2 else None
    changes=sum(s['windows']['40']['changed_vs_unweighted'] for s in groups.values())
    change_groups=sum(s['windows']['40']['changed_vs_unweighted']>0 for s in groups.values())
    reasons=[]
    if len(rows)<3 or n<1000:reasons.append('insufficient_controlled_group_coverage')
    if not rows or support/len(rows)<2/3:reasons.append('negative_adjacent_covariance_not_supported_in_two_thirds_groups')
    if median is None or not -.75<=median<=-.1:reasons.append('median_lag1_outside_preregistered_range')
    if m2 is None or m2>.25:reasons.append('nonlocal_serial_structure_lag2')
    if changes<100 or change_groups<3:reasons.append('insufficient_distinct_gls_targets')
    return dict(foundation_passed=not reasons,reasons=reasons,qualifying_groups=list(qualifying),lag1_pairs=n,
        supporting_groups=support,median_lag1=median,median_absolute_lag2=m2,
        gls40_changed_vs_unweighted=changes,gls40_changed_groups=change_groups)


def main(out):
    out.mkdir(parents=True,exist_ok=False);identity=integrity();save(out/'baseline_identity.json',identity)
    source={p.name:sha(p) for p in sorted(HERE.iterdir()) if p.is_file()}
    started=time.perf_counter();store=Store(out/'access.json');bygroup=defaultdict(list);bagstats={};counts=Counter();checks=[]
    save(out/'started.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),diagnostic_source_sha=os.environ.get('GITHUB_SHA'),
        candidate_sha=None,baseline=BASE,profile=asdict(profile()[0]),readout=asdict(profile()[1]),source_sha256=source,
        module_file=__file__,baseline_module_file=sys.modules[GuardedReadoutObserver.__module__].__file__,
        runtime_class='GuardedReadoutObserver (unchanged)',diagnostic_class='Probe',python=platform.python_version(),numpy=np.__version__,test_opened=False))
    (out/'arrays').mkdir()
    for i,bag in enumerate(store.plan['splits']['train']):
        events,refs=store.load(bag,'train')
        assert all(not v for v in refs.values())
        a,c,check=replay_probe(events,check=True);counts.update(c);checks.append(dict(bag=bag,**check))
        group=store.records[bag]['group'];bygroup[group].append(a)
        np.savez_compressed(out/'arrays'/(bag+'.npz'),rows=a,columns=np.array(COLUMNS))
        bagstats[bag]=dict(group=group,counts=c,**summarize_arrays([a]))
        save(out/'bags'/(bag+'.json'),bagstats[bag]);print('TRAIN',bag,'rows',len(a),flush=True)
    groups={g:summarize_arrays(arrays) for g,arrays in sorted(bygroup.items())}
    decision=verdict(groups)
    result=dict(round='R4-v8-fixed',hypothesis_id='R4-H33',baseline_sha=BASE,baseline_tree=identity['baseline_tree'],
        zip_sha256='a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2',source_status='VERIFIED',data_status='AVAILABLE',
        execution_status='COMPLETED',publication_status='NOT_ATTEMPTED',mechanism_status='FOUNDATION_ONLY',
        coverage_status='SUFFICIENT_FOR_FOUNDATION' if len(decision['qualifying_groups'])>=3 and decision['lag1_pairs']>=1000 else 'INSUFFICIENT',
        scientific_verdict='INCONCLUSIVE' if not decision['foundation_passed'] else 'FOUNDATION_PASSED',
        accuracy_contract_evaluated=False,accuracy_contract_passed=False,candidate_implemented=False,measured_source_sha=None,
        diagnostic_source_sha=os.environ.get('GITHUB_SHA'),report_sha=None,freeze_sha=None,validation_opened=False,test_opened=False,
        enabled_runtime_verified=False,ready_to_merge=False,variants_tested=[],run_ids=[os.environ.get('GITHUB_RUN_ID','local')],
        rejection_reasons=[],foundation_failure_reasons=decision['reasons'],missing_evidence=['white-endpoint residual covariance prerequisite'] if not decision['foundation_passed'] else [],
        next_resume_step='No runtime/accuracy after failed prerequisite; new protocol required' if not decision['foundation_passed'] else 'Implement only two preregistered runtime windows',
        foundation=decision,counts=dict(counts),train_bags=len(bagstats),train_groups=len(groups),
        checks=dict(full_state_comparisons=sum(r['full_state_checks'] for r in checks),resets=sum(r['resets'] for r in checks)),elapsed_s=time.perf_counter()-started)
    save(out/'results.json',dict(summary=result,per_group=groups,per_bag=bagstats,checks=checks))
    save(out/'SUMMARY.json',result)
    with (out/'per_group.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['group','subset','signal','segments','samples','lag1_pairs','lag1','lag2','sigma_proxy_mps'])
        for g,s in groups.items():
            for subset in ['all_trusted','controlled']:
                for kind in ['residual_accel','raw_accel','differential_accel']:
                    row=s[subset][kind];writer.writerow([g,subset,kind,s[subset]['segments']]+[row[k] for k in ['samples','lag1_pairs','lag1','lag2','sigma_proxy_mps']])
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args().output)

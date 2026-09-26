"""One prospective H23 experiment. New role/factory, unchanged official scorer."""
import argparse
from collections import Counter
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time
from common import *
from outage_physics import OutagePhysicsObserver
h11=module('h23_h11','tools/research_h11/compare.py')
NAMES=('baseline_v2','balanced_physics')  # canonical v8 / H23, not historical v2/v3
PACK=struct.Struct('<7d?')


def candidate(c=None, enabled=True):
    return OutagePhysicsObserver(c or profile()[0],alternate(),readout=profile()[1],enabled=enabled)


def fingerprint(h,e):
    h.update(PACK.pack(e.t,e.s,e.v,e.a,e.variance_v,e.variance_s,e.disturbance,e.command_stale))
    h.update(('|'.join((e.mode,e.front_status,e.rear_status))+'\n').encode())


class Capture:
    """Offline instrumentation only; shadow observer is never in runtime candidate."""
    def __init__(self,obj,check_inner=False):
        self.obj=obj;self.reference=baseline() if check_inner else None
        self.reset()
    @property
    def c(self):return self.obj.c
    @property
    def t(self):return self.obj.t
    def reset(self,**kwargs):
        self.obj.reset(**kwargs)
        if self.reference:self.reference.reset(**kwargs)
        self.digest=hashlib.sha256();self.schedule=hashlib.sha256()
        self.counts=Counter();self.traces=[];self.previous_phase=None;self.previous_u=None
        self.integral=0.;self.maximum_integration_error=0.;self.maximum_inner_error=0.
    def step(self,t,command=None,front=None,rear=None):
        previous_t=self.t
        is_h23=isinstance(self.obj,OutagePhysicsObserver)
        old_delta=self.obj.delta_v if is_h23 else 0.
        old_rollout=self.obj.rollout if is_h23 else None
        e=self.obj.step(t,command,front,rear)
        fingerprint(self.digest,e);self.schedule.update(struct.pack('<d',e.t));self.counts['outputs']+=1
        if self.reference:
            self.reference.step(t,command,front,rear)
            if vars(self.reference)!=vars(self.obj.inner):raise AssertionError('H23 modified canonical inner state')
            self.counts['inner_checks']+=1
        if is_h23 and self.obj.enabled:
            o=self.obj;phase=o.phase
            if previous_t is not None:
                self.integral+=.5*(old_delta+o.delta_v)*(t-previous_t)
                error=abs((e.s-o.inner.last_estimate.s)-self.integral)
                self.maximum_integration_error=max(self.maximum_integration_error,error)
                if error>1e-8:raise AssertionError('Distance integral mismatch')
            if old_rollout is None and o.rollout is not None:self.counts['starts']+=1
            if abs(o.delta_v)>1e-6:self.counts['changed_outputs']+=1
            if phase=='FALLBACK_OFFSET' and self.previous_phase!=phase:self.counts['offset_fallbacks']+=1
            self.counts['phase_'+phase]+=1
            u=None if e.command_stale else (1 if command.value>self.c.command_deadband else -1 if command.value<-self.c.command_deadband else 0)
            if phase=='ACTIVE' and self.previous_u is not None and u!=self.previous_u:self.counts['active_command_changes']+=1
            if o.rollout and t-o.started_at>o.HORIZON_S+1e-9:raise AssertionError('Rollout exceeded bound')
            if abs(o.delta_v)>self.c.max_accel_mps2*self.c.max_age_s+1e-12:raise AssertionError('Velocity correction bound')
            if (abs(o.delta_v)>1e-6 or phase!=self.previous_phase
                    or (o.delta_s!=0 and self.counts['outputs']%20==0)):
                self.traces.append([t,o.inner.last_estimate.v,e.v,o.delta_v,o.delta_s,o.inner.disturbance,
                    o.rollout.v if o.rollout else None,o.rollout.disturbance if o.rollout else None,
                    phase,e.front_status,e.rear_status,u])
            self.previous_phase=phase;self.previous_u=u
        return e


def compare_case(events,refs,output,case_id,fault=None,verify=True,common_fault=False):
    objects={}
    def fac(name):
        def construct(c):
            obj=(baseline(c) if name=='baseline_v2' else candidate(c,enabled=name!='disabled'))
            objects[name]=Capture(obj,check_inner=name=='balanced_physics' and verify)
            return objects[name]
        return construct
    factories={n:fac(n) for n in NAMES}
    if verify:factories['disabled']=fac('disabled')
    if common_fault:
        ms={'main':(factories['baseline_v2'],profile()[0]),'candidate':(factories['balanced_physics'],profile()[0])}
        result=h11.compare_common(events,refs,ms,fault)
        for location in [result['runtime']]+list(result['receivers'].values()):
            location['baseline_v2']=location.pop('main');location['balanced_physics']=location.pop('candidate')
    else:
        result=score(events,refs,factories,fault)
    if verify and not common_fault:
        if objects['disabled'].digest.digest()!=objects['baseline_v2'].digest.digest():raise AssertionError('Feature-off Estimate differs')
        if result['runtime']['disabled']!=result['runtime']['baseline_v2']:raise AssertionError('Feature-off counters differ')
        result['runtime'].pop('disabled')
        for v in result['receivers'].values():v.pop('disabled')
    if objects['baseline_v2'].schedule.digest()!=objects['balanced_physics'].schedule.digest():raise AssertionError('Exact timestamps differ')
    o=objects['balanced_physics']; result['activation']=dict(o.counts)
    result['integration_max_abs_error']=o.maximum_integration_error
    result['checks']=dict(exact_schedule=True,all_inner=bool(verify),feature_off=bool(verify and not common_fault))
    if output is not None and o.traces:
        ts=np.array([r[0] for r in o.traces]); matched={k:ev.ex.match(v,ts).tolist() for k,v in refs.items()}
        clean_ref={k:[None if not math.isfinite(x) else x for x in v] for k,v in matched.items()}
        p=output/'traces'/(case_id+'.json.gz');p.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(p,'wt') as stream:
            json.dump(dict(columns=['t','v8_v','h23_v','delta_v','delta_s','v8_d','B_v','B_d','phase','front','rear','command_class'],rows=o.traces,external_reference=clean_ref),stream,allow_nan=False)
    return result


def inject(events,fault):
    changed=events.copy();mask=(changed[:,0]>=fault['start'])&(changed[:,0]<fault['end']);wheel=changed[:,1]!=0
    if fault['kind']=='dropout':return changed[~(mask&wheel)]
    if fault['kind']=='bias':changed[mask&(changed[:,1]==1),2]+=5.
    if fault['kind']=='lock':changed[mask&wheel,2]=0.
    return changed


def low_speed_windows(events):
    # Exact selector of tools/research_lock/low_speed.py at f10e3cfc... (PR13).
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=np.flatnonzero(valid&(abs(f-r)<.15)&((f+r)/2>1)&((f+r)/2<2)&(u>=0)&(t>max(25,.1*t[-1]))&(t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            fault=dict(kind='lock',start=anchor,end=anchor+duration)
            yield fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


def canonical(rows):
    return [dict(bag=r['bag'],group=r['group'],fault=r.get('fault'),outputs=r['outputs'],runtime=r['runtime']['baseline_v2'],
                 receivers={k:v['baseline_v2'] for k,v in r['receivers'].items()}) for r in rows]


def summary(clean,stress,name):
    s=v6.summary(clean,stress,name)
    s.update(clean_mae=v6.macro(clean,name,'mae'),clean_signed_bias=v6.macro(clean,name,'bias'),
             fault_recovery_mae=v6.macro(stress,name,'mae'),fault_recovery_signed_bias=v6.macro(stress,name,'bias'),
             recovery_macro_s=v6.macro(stress,name,'recovery_s'))
    return s


def row_veto(rows,label,clean=False):
    reasons=[]
    for r in rows:
        ident=label+':'+r['bag']+':'+str(r.get('fault',{}))
        for name in NAMES:
            info=r['runtime'][name]
            if info['causal_errors'] or info['resets']:reasons.append(ident+':causal_or_reset:'+name)
        for receiver,values in r['receivers'].items():
            b,c=(values[n] for n in NAMES)
            if b['n']!=c['n'] or b['coverage']!=c['coverage']:reasons.append(ident+':coverage:'+receiver)
            if c['false_stop_samples']>b['false_stop_samples']:reasons.append(ident+':false_stop:'+receiver)
            if b.get('event_rmse') is not None and b.get('recovery_s') is not None and c.get('recovery_s') is None:
                reasons.append(ident+':new_individual_unrecovered:'+receiver)
            if clean and b['rmse'] is not None and (c['rmse'] is None or c['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                reasons.append(ident+':bag_rmse:'+receiver)
    return reasons


def decide(clean,stress,full,low,common_rows,false_pair):
    summaries={n:summary(clean,stress,n) for n in NAMES};b,c=(summaries[n] for n in NAMES)
    changes={k:(c[k]/b[k]-1 if b[k] else None) for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse')}
    reasons=[]
    if not(c['clean_rmse']<=b['clean_rmse']*.98 or c['fault_rmse']<=b['fault_rmse']*.95):reasons.append('insufficient_gain')
    for k,limit in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        if c[k]>b[k]*(1+limit)+1e-12:reasons.append('aggregate_regression:'+k)
    reasons+=row_veto(clean,'clean',True)+row_veto(stress,'original')+row_veto(full,'full')
    full_distance={n:v6.macro(full,n,'distance') for n in NAMES}
    if full_distance[NAMES[1]] is None or full_distance[NAMES[0]] is None:reasons.append('full_distance_missing')
    elif full_distance[NAMES[1]]>full_distance[NAMES[0]]*1.01+1e-12:reasons.append('full_fault_distance_regression')
    suites={}
    for label,rows in [('low_speed',low),('common',common_rows),('false_pair',false_pair)]:
        suites[label]={n:dict(event_rmse=v6.macro(rows,n,'event_rmse'),mae=v6.macro(rows,n,'mae'),
                              false_stops=v6.total(rows,n,'false_stop_samples'),unrecovered=v6.unrecovered(rows,n),
                              recovery_s=v6.macro(rows,n,'recovery_s')) for n in NAMES}
        x,y=(suites[label][n]['event_rmse'] for n in NAMES)
        if x is None or y is None:reasons.append(label+':missing_event_reference')
        elif y>x*1.005+1e-12:reasons.append(label+':event_regression')
        reasons+=row_veto(rows,label)
    counts=Counter()
    for r in clean+stress:counts.update(r['activation'])
    groups=sorted({r['group'] for r in clean+stress if r['activation'].get('changed_outputs',0)>0})
    coverage=counts['starts']>=10 and counts['changed_outputs']>=100 and len(groups)>=3
    verdict='INCONCLUSIVE' if not coverage else 'REJECTED' if reasons else 'DEVELOPMENT_PASSED'
    return dict(baseline=BASE,candidate='H23_B_outage_5s_v1',summary=summaries,relative_change=changes,
                full_fault_distance=full_distance,suites=suites,coverage=dict(passed=coverage,counts=dict(counts),groups=groups),
                mechanism_status='ACTIVE' if counts['changed_outputs'] else 'NOT_ACTIVE',coverage_status='SUFFICIENT' if coverage else 'INSUFFICIENT',
                scientific_verdict=verdict,accuracy_contract_passed=not reasons and coverage,runtime_verified=False,ready_to_merge=False,
                rejection_reasons=sorted(set(reasons)),test_evaluated=False)


def source_hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(HERE.glob('*')) if p.is_file()}


def verify_freeze(path):
    f=json.loads(path.read_text());commit=os.environ.get('H23_FREEZE_COMMIT');repo_path=os.environ.get('H23_FREEZE_PATH')
    if not commit or not repo_path:raise PermissionError('Published freeze required')
    published=subprocess.check_output(['git','show',commit+':'+repo_path],cwd=ROOT)
    if published!=path.read_bytes():raise ValueError('Freeze differs from published commit')
    if f['source_hashes']!=source_hashes() or f['baseline_pins']!=integrity():raise ValueError('Frozen code changed')
    return f


def run(stage,out,freeze=None):
    if stage=='validation':verify_freeze(freeze)
    out.mkdir(parents=True,exist_ok=False)
    pins=integrity();store=Store(out/'access.json');started=time.perf_counter()
    save(out/'started.json',dict(source_commit=os.environ.get('GITHUB_SHA','local'),baseline=BASE,source_hashes=source_hashes(),baseline_pins=pins,
        stage=stage,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),test_evaluated=False))
    collections={k:[] for k in ('clean','stress','full','low','common','false_pair')}
    for bag in store.plan['splits'][stage]:
        events,refs=store.load(bag,stage);meta=dict(bag=bag,group=store.records[bag]['group'],role=stage)
        result={k:[] for k in collections}
        def add(label,es,f=None,case_id='',common_fault=False):
            row=dict(**meta,**compare_case(es,refs,out,bag+'-'+label+case_id,f,verify=True,common_fault=common_fault))
            if f is not None:row['fault']=f
            result[label].append(row);collections[label].append(row)
        add('clean',events)
        for i,(fault,window) in enumerate(gc.fault_windows(events)):
            add('stress',window,fault,str(i))
            add('full',inject(events,fault),None,str(i))
            result['full'][-1]['injection']=fault
        for i,(f,w) in enumerate(low_speed_windows(events)):add('low',w,f,str(i))
        for i,(f,w) in enumerate(h11.common_fault_windows(events)):add('common',w,f,str(i),True)
        original=list(gc.fault_windows(events))
        if original:
            anchor=original[0][0]['start'];drop=dict(kind='dropout',start=anchor,end=anchor+5.)
            changed=inject(events,drop);mask=(changed[:,0]>=anchor+5)&(changed[:,0]<anchor+6)&(changed[:,1]!=0);changed[mask,2]+=2.
            window=changed[(changed[:,0]>=anchor-20)&(changed[:,0]<=anchor+16.1)]
            add('false_pair',window,dict(kind='externally_injected',start=anchor,end=anchor+6),'-0')
        save(out/'bags'/(bag+'.json'),result)
        print('CHECKPOINT',bag,'starts',sum(r['activation'].get('starts',0) for r in result['clean']+result['stress']),flush=True)
    digest=hashlib.sha256(json.dumps(canonical(collections['clean']+collections['stress']),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if stage=='development':
        expected=json.loads((HERE/'PREFLIGHT_BASELINE.json').read_text())['canonical_metrics_sha256']
        if digest!=expected:raise AssertionError('Baseline differs from independent preflight: '+digest)
    decision=decide(collections['clean'],collections['stress'],collections['full'],collections['low'],collections['common'],collections['false_pair'])
    decision.update(stage=stage,validation_evaluated=stage=='validation',baseline_reproduction_fingerprint=digest,
                    counts={k:len(v) for k,v in collections.items()},elapsed_s=time.perf_counter()-started)
    if stage=='validation' and decision['accuracy_contract_passed']:decision['scientific_verdict']='CONFIRMED_ACCURACY_ONLY'
    if not decision['accuracy_contract_passed']:decision['enabled_ros']='NOT_RUN_AFTER_REJECTION' if decision['scientific_verdict']=='REJECTED' else 'NOT_RUN_INCONCLUSIVE'
    save(out/'SUMMARY.json',decision)
    print(json.dumps(decision,ensure_ascii=False,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=('development','validation','freeze'),required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--freeze',type=Path);p.add_argument('--development',type=Path)
    a=p.parse_args()
    if a.stage=='freeze':
        d=json.loads((a.development/'SUMMARY.json').read_text())
        if not d['accuracy_contract_passed']:raise PermissionError('Development did not pass; validation locked')
        if a.output.exists():raise FileExistsError(a.output)
        save(a.output,dict(source_commit=os.environ.get('GITHUB_SHA'),source_hashes=source_hashes(),baseline_pins=integrity(),
                          development_summary_sha256=sha(a.development/'SUMMARY.json'),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),development_passed=True))
    else:run(a.stage,a.output,a.freeze)
if __name__=='__main__':main()

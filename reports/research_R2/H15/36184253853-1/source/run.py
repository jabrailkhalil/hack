"""R2 H15 isolated factory/driver; immutable score, matching and original faults.

Development has its real role; train never opens reference topics. There is no
final/test loading path. Run apply.py first in a clean isolated worktree.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time
import csv

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'tools/finalization'),str(ROOT/'src/reserve_odometry')]
import evaluate as ev
import numpy as np
from _canonical.guarded_readout import GuardedReadoutObserver as Canonical
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig
from reserve_odometry.drive_disturbance import DriveDependentObserver,DriveCorrectionConfig

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
v6=module('h15_immutable_v6',ROOT/'tools/research_v6/compare.py')
gv7=module('h15_immutable_guarded',ROOT/'tools/research_guarded/compare.py')
BASE='65bba39ed05c781f3f69a65c02f69931152cbfd9'
OPS={'rate_hz':20.,'alignment_delay_s':0.}
PROFILE=json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())
RIDGES={'h15_l001':.01,'h15_l004':.04}
RAW_REPLAY=ev.replay

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def manifest():
    base=json.loads((HERE/'baseline_manifest.json').read_text())
    actual={}
    for p,h in base['sha256'].items():
        expected=base['patched_core_sha256'] if p.endswith('/core.py') else h
        if sha(ROOT/p)!=expected:raise ValueError('Pinned file differs: '+p)
        actual[p]=expected
    for name in ('core.py','guarded_readout.py'):
        expected=base['sha256']['src/reserve_odometry/reserve_odometry/'+name]
        if sha(HERE/'_canonical'/name)!=expected:raise ValueError('Canonical source snapshot differs')
    paths=[HERE/'run.py',HERE/'apply.py',HERE/'algorithm.patch',HERE/'PLAN.md',HERE/'baseline_manifest.json',
           ROOT/'src/reserve_odometry/reserve_odometry/drive_disturbance.py']
    paths+=sorted((HERE/'tests').glob('*.py'))
    for p in paths:
        if p.exists():actual[str(p.relative_to(ROOT))]=sha(p)
        elif p.name=='PLAN.md':raise FileNotFoundError('Committed PLAN required')
    # Actual launch and YAML values, not a legacy alias named "main".
    yaml={}
    for line in (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text().splitlines():
        k,sep,val=line.strip().partition(':')
        if k.startswith(('model.','readout.')) and sep:yaml[k]=float(val)
    assert {k[6:]:v for k,v in yaml.items() if k.startswith('model.')}==PROFILE['config']
    assert {k[8:]:v for k,v in yaml.items() if k.startswith('readout.')}==PROFILE['readout']
    assert PROFILE['config']['wheel_time_compensation']==0 and PROFILE['config']['adaptation_tau_s']==.5
    assert PROFILE['readout']=={'gain':1,'holdoff_s':.5}
    assert 'guarded_odometry_node' in (ROOT/'src/reserve_odometry/launch/odometry.launch.py').read_text()
    return actual

def new_observer(name,c):
    readout=ReadoutConfig(**PROFILE['readout'])
    if name=='baseline_v2':return Canonical(c,readout=readout)
    if name=='balanced_physics':return GuardedReadoutObserver(c,readout=readout)
    if name=='off':return DriveDependentObserver(c,readout=readout,correction=DriveCorrectionConfig(enabled=False))
    return DriveDependentObserver(c,readout=readout,correction=DriveCorrectionConfig(ridge=RIDGES[name]))

class RoleStore(ev.ex.Store):
    """Real development role, checksum protected, query-only SQLite.

    Original train/validation loader retained; journal is recorded before IO.
    """
    def __init__(self,journal):
        super().__init__();self.journal=Path(journal);self.audit=[]
    def load(self,bag,purpose):
        if purpose not in ('train','development','validation'):
            raise PermissionError('No final/test measurement access')
        row=self.records[bag]
        if row['split']!=purpose or bag not in self.plan['splits'][purpose]:
            raise PermissionError('Cannot relabel a data role')
        allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose!='train' else [])
        path=self.root/bag/(bag+'_0.db3')
        self.audit.append(dict(bag=bag,purpose=purpose,sha256=row['sha256'],topics=allowed,utc=now(),status='requested'))
        save(self.journal,dict(test_evaluated=False,access=self.audit))
        if purpose!='development':
            result=super().load(bag,purpose)
        else:
            if sha(path)!=row['sha256']:raise ValueError('Development checksum mismatch')
            events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
            with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
                con.execute('PRAGMA query_only=ON')
                query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                       'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
                for topic,typ,raw in con.execute(query,allowed):
                    stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                    if topic in ev.ex.CHANNELS:
                        ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                    else:
                        speed=math.hypot(float(values[0]),float(values[1]))
                        if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
            result=np.asarray(events,float),refs
        self.audit[-1]['status']='completed';save(self.journal,dict(test_evaluated=False,access=self.audit))
        return result


def recorded_replay(events,c,name,fault=None,trace=False,step_timing=False):
    observer=new_observer(name,c);original_step=observer.step
    sums=Counter();last={};rows=[];step_cpu=0.;step_wall=0.;steps=0
    max_delta=0.;max_gamma=0.;max_history=0;tail_cpu=None;tail_wall=None
    def tracked(*args,**kwargs):
        nonlocal step_cpu,step_wall,steps,last,max_delta,max_gamma,max_history,tail_cpu,tail_wall
        timed=step_timing and args[0]>=10.
        if timed:
            if tail_cpu is None:tail_cpu=time.process_time();tail_wall=time.perf_counter()
            cpu=time.process_time();wall=time.perf_counter()
        e=original_step(*args,**kwargs)
        if timed:step_cpu+=time.process_time()-cpu;step_wall+=time.perf_counter()-wall
        steps+=1
        if hasattr(observer,'stats'):
            current=observer.stats
            for key,value in current.items():
                if key=='max_history':max_history=max(max_history,value)
                else:sums[key]+=value-last.get(key,0) if value>=last.get(key,0) else value
            last=dict(current)
            delta=observer.effective_d-observer.disturbance
            max_delta=max(max_delta,abs(delta));max_gamma=max(max_gamma,abs(observer.gamma))
            if trace and steps%2==0 and len(rows)<2000:
                rows.append(dict(t=e.t,mode=e.mode,statuses=[e.front_status,e.rear_status],
                    v=e.v,inner_v=observer.v,drive_a=observer.drive_a,d=observer.disturbance,
                    d_eff=observer.effective_d,gamma=observer.gamma,condition=observer.condition,
                    fit_ok=observer.fit_ok,loss=observer.loss,history=len(observer.history)))
        return e
    observer.step=tracked
    old=ev.Observer;ev.Observer=lambda conf:observer
    cpu=time.process_time();wall=time.perf_counter()
    try:a,info=RAW_REPLAY(events,c,OPS,fault)
    finally:ev.Observer=old
    diag=dict(stats=dict(sums),max_history=max_history,max_abs_delta=max_delta,max_abs_gamma=max_gamma,
              replay_cpu_s=time.process_time()-cpu,replay_wall_s=time.perf_counter()-wall,steps=steps,
              step_cpu_s=step_cpu if step_timing else None,step_wall_s=step_wall if step_timing else None)
    if step_timing:
        diag['replay_cpu_after_warmup_s']=time.process_time()-tail_cpu if tail_cpu is not None else 0.
        diag['replay_wall_after_warmup_s']=time.perf_counter()-tail_wall if tail_wall is not None else 0.
    if trace:diag['trace']=rows
    return a,info,diag


def paired(events,refs,names,fault=None,trace=False):
    keys=['baseline_v2','balanced_physics','off']+list(names)
    models={k:Config(**PROFILE['config']) for k in keys}
    ids={id(c):k for k,c in models.items()};arrays={};diagnostics={}
    def adapter(e,c,ops,f=None):
        name=ids[id(c)];a,info,diag=recorded_replay(e,c,name,f,trace=trace and name in RIDGES)
        arrays[name]=a;diagnostics[name]=diag;return a,info
    old=ev.replay;ev.replay=adapter
    try:result=ev.score(events,refs,models,OPS,fault)
    finally:ev.replay=old
    for name,a in arrays.items():
        if a.shape!=arrays['baseline_v2'].shape or not np.array_equal(a[:,0],arrays['baseline_v2'][:,0]):
            raise AssertionError('Exact output schedule mismatch '+name)
    for name in ('balanced_physics','off'):
        if not np.array_equal(arrays[name],arrays['baseline_v2'],equal_nan=True):
            raise AssertionError('Canonical R2/feature-off output mismatch '+name)
        if result['runtime'][name]!=result['runtime']['baseline_v2']:
            raise AssertionError('Canonical/disabled runtime counter mismatch '+name)
    result['diagnostics']=diagnostics;result['disabled_equivalence']=True
    result['canonical_factory']='_canonical.GuardedReadoutObserver; Estimate output; verified pinned source'
    return result


def phase_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid;m=np.where(u>.04,1,np.where(u<-.04,-1,0))
    for before,after,label in ((1,0,'traction_to_coast'),(0,-1,'coast_to_brake')):
        idx=np.flatnonzero((m[:-1]==before)&(m[1:]==after)&valid[1:]&((f[1:]+r[1:])/2>2.)
                           &(t[1:]>25.)&(t[1:]<t[-1]-15.))+1
        if len(idx):
            start=float(t[idx[0]]-.3);fault=dict(kind='dropout',start=start,end=start+5.)
            window=events[(events[:,0]>=start-20)&(events[:,0]<=start+15.1)]
            yield label,fault,window


def summaries(clean,stress,names):
    result={}
    for name in ['baseline_v2']+list(names):
        s=v6.summary(clean,stress,name)
        s['clean_mae']=v6.macro(clean,name,'mae');s['clean_signed_bias']=v6.macro(clean,name,'bias')
        s['fault_mae']=v6.macro(stress,name,'mae');s['fault_signed_bias']=v6.macro(stress,name,'bias')
        s['recovery_group_macro_s']=v6.macro(stress,name,'recovery_s')
        result[name]=s
    return result


def safety(clean,stress,name):
    reasons=[]
    for row in clean+stress:
        rt=row['runtime'][name]
        if rt['causal_errors'] or rt['resets']:reasons.append('causality_or_reset:'+row['bag'])
        for receiver,scores in row['receivers'].items():
            a,b=scores[name],scores['baseline_v2'];label=row['bag']+'/'+receiver
            if a['n']!=b['n'] or a['coverage']!=b['coverage']:reasons.append('coverage:'+label)
            if a['false_stop_samples']>b['false_stop_samples']:reasons.append('false_stops:'+label)
            if 'fault' in row:
                if b.get('event_rmse') is not None and b.get('recovery_s') is not None and a.get('recovery_s') is None:
                    reasons.append('new_unrecovered:'+label+'/'+str(row['fault']))
            elif b['rmse'] is not None and (a['rmse'] is None or a['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                reasons.append('clean_per_bag:'+label)
    return sorted(set(reasons))

def change(a,b):return a/b-1 if b!=0 else (0. if abs(a)<=1e-12 else None)
def admission(clean,stress,names):
    s=summaries(clean,stress,names);base=s['baseline_v2'];res={}
    for name in names:
        a=s[name];reasons=safety(clean,stress,name)
        deltas={k:change(a[k],base[k]) for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse')}
        if not ((deltas['clean_rmse'] is not None and deltas['clean_rmse']<=-.02) or
                (deltas['fault_rmse'] is not None and deltas['fault_rmse']<=-.05)):
            reasons.append('insufficient_gain')
        for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse'):
            limit=.01 if k=='distance_rmse' else .005
            if deltas[k] is None or deltas[k]>limit:reasons.append('aggregate_regression:'+k)
        res[name]=dict(eligible=not reasons,reasons=sorted(set(reasons)),relative_change=deltas)
    return dict(summary=s,candidates=res)


def coverage(clean,stress,phases,name):
    fits=sum(r['diagnostics'][name]['stats'].get('fits',0) for r in clean)
    fit_bags=[r['bag'] for r in clean if r['diagnostics'][name]['stats'].get('fits',0)>0]
    effective=sum(r['diagnostics'][name]['stats'].get('effective_ticks',0) for r in stress+phases)
    loss_bags=sorted({r['bag'] for r in stress+phases if r['diagnostics'][name]['stats'].get('effective_ticks',0)>0})
    return dict(fits=fits,fit_bags=fit_bags,effective_ticks=effective,loss_bags=loss_bags,
                sufficient=fits>=100 and len(fit_bags)>=3 and effective>=20 and len(loss_bags)>=3)


def export_csv(output,clean,stress,phases,summary):
    rows=[]
    for suite,data in [('clean',clean),('original_fault',stress),('phase_diagnostic',phases)]:
        for row in data:
            for receiver,scores in row['receivers'].items():
                for name in ['baseline_v2']+[n for n in RIDGES if n in scores]:
                    m=scores[name];fault=row.get('fault',{})
                    rows.append(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,model=name,
                        fault=fault.get('kind'),start=fault.get('start'),end=fault.get('end'),
                        phase=row.get('phase'),**{k:m.get(k) for k in ('n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples')},
                        distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')))
    if rows:
        with (output/'per_bag.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    if summary:
        with (output/'aggregate.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=['model']+list(next(iter(summary.values()))));w.writeheader()
            w.writerows(dict(model=k,**v) for k,v in summary.items())


def cost(events):
    prefix=events[events[:,0]<=180.]
    # Warm-up is replayed but excluded from both step and replay measured blocks.
    warm=prefix[prefix[:,0]<10.]
    for name in ['baseline_v2']+list(RIDGES):recorded_replay(warm,Config(**PROFILE['config']),name)
    # Identical prefix constructs the same causal state; t<10 excluded from tail and step timers.
    result=[]
    for candidate in RIDGES:
        for repeat in range(6):
            order=['baseline_v2',candidate] if repeat%2==0 else [candidate,'baseline_v2']
            for name in order:
                a,info,diag=recorded_replay(prefix,Config(**PROFILE['config']),name,step_timing=True)
                result.append(dict(candidate=candidate,repeat=repeat,order='AB' if repeat%2==0 else 'BA',model=name,
                    outputs=len(a),**diag))
    return dict(bag='30618_0652866c',warmup_s=10,prefix_s=180,
        scope='Six AB/BA pairs per variant, identical 180s prefix; after_warmup and step timers exclude first10s, total replay timers also retained. NOT ROS latency/RSS',
        repetitions=result,thread_limits={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')})


def run(stage,output,names):
    output.mkdir(parents=True,exist_ok=False);hashes=manifest();store=RoleStore(output/'access.json')
    provenance=dict(stage=stage,baseline=BASE,source_ref=os.environ.get('H15_MEASURED_SHA',os.environ.get('GITHUB_SHA','local')),utc=now(),
        source_sha256=hashes,profile=PROFILE,ops=OPS,python=platform.python_version(),numpy=np.__version__,
        test_evaluated=False,candidates={n:asdict(DriveCorrectionConfig(ridge=RIDGES[n])) for n in names})
    save(output/'started.json',provenance);started=time.perf_counter()
    clean=[];stress=[];phases=[];train=[];cost_result=None
    for bag in store.plan['splits'][stage]:
        events,refs=store.load(bag,stage);meta=dict(bag=bag,group=store.records[bag]['group'],role=stage)
        if stage=='train':
            events=events[events[:,0]<=180.]
            row=dict(**meta,diagnostics={})
            baseline=None
            for n in ['baseline_v2','off']+list(names):
                a,info,d=recorded_replay(events,Config(**PROFILE['config']),n)
                row['diagnostics'][n]=dict(**d,outputs=len(a),runtime=info)
                if n=='baseline_v2':baseline=(a,info)
                if n=='off' and (not np.array_equal(a,baseline[0],equal_nan=True) or info!=baseline[1]):
                    raise AssertionError('Train off equivalence failed')
            row['reference_accuracy']=None;train.append(row);save(output/'bags'/(bag+'.json'),row)
        else:
            c=dict(**meta,**paired(events,refs,names));clean.append(c)
            fs=[dict(**meta,fault=f,**paired(win,refs,names,f,trace=True)) for f,win in gv7.fault_windows(events)]
            stress+=fs;ps=[]
            if stage=='development':
                ps=[dict(**meta,phase=phase,fault=f,**paired(win,refs,names,f,trace=True)) for phase,f,win in phase_windows(events)]
                phases+=ps
                if bag==store.plan['splits']['development'][0]:cost_result=cost(events);save(output/'cost.json',cost_result)
            save(output/'bags'/(bag+'.json'),dict(clean=c,stress=fs,phase=ps))
        print(stage,bag,flush=True)
    if stage=='train':
        result=dict(**provenance,bags=train,elapsed_s=time.perf_counter()-started)
    else:
        gates=admission(clean,stress,names)
        cov={n:coverage(clean,stress,phases,n) for n in names}
        if stage=='development':
            safe={n:safety(clean,stress+phases,n) for n in names}
            choices=[n for n in names if not safe[n] and cov[n]['sufficient']]
            selected=None
            for n in choices:
                if selected is None or gates['summary'][n]['fault_rmse']<gates['summary'][selected]['fault_rmse']-1e-12 or (
                        abs(gates['summary'][n]['fault_rmse']-gates['summary'][selected]['fault_rmse'])<=1e-12 and RIDGES[n]>.01):selected=n
            verdict='READY_FOR_FROZEN_VALIDATION' if selected else ('REJECTED' if all(safe[n] for n in names) else 'INCONCLUSIVE')
            decision=dict(verdict=verdict,selected=selected,safety=safe,coverage=cov,**gates,
                validation_opened=False,merge_ready=False)
        else:
            selected=names[0];verdict='ACCURACY_PASSED_RUNTIME_PENDING' if gates['candidates'][selected]['eligible'] else 'REJECTED'
            decision=dict(verdict=verdict,selected=selected,**gates,coverage=cov,merge_ready=False,independent_test=False)
        result=dict(**provenance,clean=clean,stress=stress,phase_diagnostics=phases,summary=gates['summary'],
                    elapsed_s=time.perf_counter()-started,baseline_reproduction=dict(canonical_off_equal=True,
                    method='Actual independent pinned canonical plus patched no-hook and feature-off on every replay'))
        save(output/'decision.json',decision);export_csv(output,clean,stress,phases,gates['summary'])
        print(json.dumps(decision,indent=2),flush=True)
    save(output/'results.json',result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['train','development','freeze','validation'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--development',type=Path);p.add_argument('--frozen',type=Path)
    a=p.parse_args()
    if a.stage=='freeze':
        d=json.loads((a.development/'decision.json').read_text())
        if not d['selected']:raise ValueError('No candidate passed pre-validation gates; do not open validation')
        if a.output.exists():raise FileExistsError('Do not replace freeze')
        store=ev.ex.Store()
        save(a.output,dict(utc=now(),baseline=BASE,source_ref=os.environ.get('H15_MEASURED_SHA',os.environ.get('GITHUB_SHA','local')),
            selected=d['selected'],source_sha256=manifest(),development_sha256=sha(a.development/'results.json'),
            decision_sha256=sha(a.development/'decision.json'),candidates=RIDGES,profile=PROFILE,ops=OPS,
            validation_bags=store.plan['splits']['validation'],
            data_sha256={k:store.records[k]['sha256'] for role in ('train','development','validation') for k in store.plan['splits'][role]},
            test_evaluated=False))
    elif a.stage=='validation':
        f=json.loads(a.frozen.read_text())
        if manifest()!=f['source_sha256'] or f['baseline']!=BASE:raise ValueError('Frozen algorithm changed')
        if f['validation_bags']!=ev.ex.Store().plan['splits']['validation']:raise ValueError('Frozen split changed')
        # Separate publication is mandatory in the executing workflow; recorded for audit.
        if not os.environ.get('H15_FREEZE_COMMIT'):raise ValueError('Publish freeze commit BEFORE validation; set H15_FREEZE_COMMIT')
        run('validation',a.output,[f['selected']])
        save(a.output/'freeze_provenance.json',dict(freeze_sha256=sha(a.frozen),freeze_commit=os.environ['H15_FREEZE_COMMIT']))
    else:run(a.stage,a.output,list(RIDGES))

if __name__=='__main__':main()

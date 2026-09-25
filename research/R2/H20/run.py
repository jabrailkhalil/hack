#!/usr/bin/env python3
"""H20: development selection and explicitly frozen, single paired validation.

Only factories, role-specific loader and diagnostics are new. Original score,
replay, masks, original fault anchors, summary and legacy decide remain pinned.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import csv
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import factory as f
import evaluate as ev
import numpy as np
ex = ev.ex

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

legacy = load_module('h20_unchanged_v6', ROOT/'tools/research_v6/compare.py')
guarded = load_module('h20_unchanged_guarded', ROOT/'tools/research_guarded/compare.py')
REPLAY = ev.replay
VARIANTS = {'H20_alpha025': .25, 'H20_alpha050': .5}
BASE = 'baseline_v7'


def save(path, value):
    ev.save(path, value)


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def source_hashes():
    manifest = json.loads((HERE/'BASELINE.json').read_text())
    for path, expected in manifest['files'].items():
        if f.sha(ROOT/path) != expected:
            raise ValueError('Changed fixed baseline/evaluator: '+path)
    code = sorted(p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py','.patch','.json','.wl','.sh') and '__pycache__' not in str(p))
    return dict(manifest['files']) | {str(p.relative_to(ROOT)): f.sha(p) for p in code}


def source_sha():
    return os.environ.get('H20_SOURCE_SHA') or os.environ.get('GITHUB_SHA') or subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True).stdout.strip() or 'local-uncommitted'


class RoleStore(ex.Store):
    """Same read-only decoder/order/scales, with explicitly authorized dev role."""
    def __init__(self, role, journal):
        if role not in ('development','validation'):
            raise PermissionError('H20 cannot open train references or test payloads')
        super().__init__(); self.role=role; self.journal=journal

    def load(self, bag, purpose):
        row=self.records[bag]
        if purpose != self.role or purpose not in ('development','validation') or row['split'] != purpose or bag not in self.plan['splits'][purpose]:
            raise PermissionError('Role rejected before measurement IO: '+bag+'/'+purpose)
        path=self.root/bag/(bag+'_0.db3')
        allowed=list(ex.CHANNELS)+list(ex.REFS)
        entry=dict(bag=bag,purpose=purpose,sha256=row['sha256'],topics=allowed,mode='sqlite_ro')
        self.access.append(entry)
        save(self.journal,dict(test_payload_opened=False,access=self.access))
        if f.sha(path)!=row['sha256']: raise ValueError('Bag checksum differs: '+bag)
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                   'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ex.CHANNELS:
                    ch=ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs


class Monitor:
    """Offline instrumentation. References and fault identity never enter inner."""
    def __init__(self, inner, check_disabled=False, trace_fault=None):
        self.inner=inner
        self.trace_fault=trace_fault
        self.off=f.candidate(0.) if check_disabled else None
        self.reset()
    def __getattr__(self,name):return getattr(self.inner,name)
    def reset(self,**kwargs):
        self.inner.reset(**kwargs)
        if self.off:self.off.reset(**kwargs)
        self.ticks=0;self.accepted=0;self.changed=0
        self.fault_trace=[]
        self.seconds=Counter();self.signs=Counter();self.traces=[];self.trace_counts=Counter()
        self.phase_ticks=[];self.last_t=None;self.state_keys=None
    def step(self,*args,**kwargs):
        old_t=self.inner.t
        e=self.inner.step(*args,**kwargs)
        if self.off:
            other=self.off.step(*args,**kwargs)
            if asdict(e)!=asdict(other):raise AssertionError('Disabled returned Estimate mismatch')
            f.assert_disabled(self.inner,self.off)
        self.ticks+=1
        d=getattr(self.inner,'_h20_diag',None)
        phase=getattr(self.inner,'_h20_confirmed',0)
        dt=0. if old_t is None else e.t-old_t
        self.seconds[str(phase)]+=dt
        # The clean phase label is vehicle-only command at this output tick.
        cmd=args[1] if len(args)>1 else kwargs.get('command')
        cp=0
        if cmd is not None and self.inner._valid(cmd,e.t,self.c.command_timeout_s):
            cp=1 if cmd.value>.09 else -1 if cmd.value<-.09 else 0
        if e.mode!='WAITING_FOR_INITIALIZATION':self.phase_ticks.append(cp)
        if d:
            self.accepted+=1;self.changed+=int(d['changed'])
            for value,w in zip(d['innovations'],d['weights']):
                self.signs[f"{d['instantaneous_phase']}:{'positive' if value>0 else 'negative' if value<0 else 'zero'}"]+=1
                if w<1.:self.signs[f"weighted:{d['phase']}:{'positive' if value>0 else 'negative'}"]+=1
            key=str(d['phase'])+('changed' if d['changed'] else 'unchanged')
            # Bounded trace reservoir selected on vehicle-side state, not errors.
            if self.trace_counts[key]<16:
                self.trace_counts[key]+=1
                self.traces.append(dict(t=e.t,published_v=e.v,published_s=e.s,inner_v=self.inner.v,inner_s=self.inner.s,
                    pv=self.inner.pv,drive_a=self.inner.drive_a,disturbance=self.inner.disturbance,
                    readout_correction=self.inner._velocity_correction,mode=e.mode,
                    front_status=e.front_status,rear_status=e.rear_status,**d))
        if self.trace_fault and self.ticks % 4 == 0 and len(self.fault_trace) < 128:
            start,end=self.trace_fault['start'],self.trace_fault['end']
            middle=(start+end)*.5
            if abs(e.t-start)<=1. or abs(e.t-middle)<=.5 or abs(e.t-end)<=1.:
                self.fault_trace.append(dict(t=e.t,segment='before' if e.t<start else 'during' if e.t<end else 'after',
                    published_v=e.v,published_s=e.s,inner_v=self.inner.v,inner_s=self.inner.s,
                    pv=self.inner.pv,drive_a=self.inner.drive_a,disturbance=self.inner.disturbance,
                    readout_correction=self.inner._velocity_correction,mode=e.mode,
                    front_status=e.front_status,rear_status=e.rear_status,soft_update=d))
        for key in ('v','s','a','variance_v','variance_s','disturbance'):
            if not math.isfinite(getattr(e,key)):raise AssertionError('Nonfinite estimate: '+key)
        return e
    def diagnostic(self):
        return dict(ticks=self.ticks,accepted_updates=self.accepted,changed_updates=self.changed,
            confirmed_mode_seconds=dict(self.seconds),innovation_signs=dict(self.signs),
            trace=self.traces,fault_trace=self.fault_trace,disabled_full_state_ticks=self.ticks if self.off else 0)


def paired(events,refs,names,fault=None,check_disabled=False,clean_phases=False):
    aliases={'baseline_v2':BASE,'balanced_physics':names[0]}
    aliases.update({name:name for name in names[1:]})
    cfg=f.profile()[0]
    configs={internal:ex.Config(**cfg) for internal in aliases}
    lookup={id(configs[k]):v for k,v in aliases.items()}
    arrays={};diagnostics={};phase_masks={}
    def replay(inputs,config,ops,scenario=None):
        name=lookup[id(config)]
        inner=f.baseline() if name==BASE else f.candidate(VARIANTS[name])
        if f.neutral(inner.c)!=asdict(config):raise AssertionError('Effective config mismatch')
        monitor=Monitor(inner,check_disabled=check_disabled and name==BASE,trace_fault=scenario)
        old=ev.Observer
        try:
            ev.Observer=lambda _:monitor
            a,info=REPLAY(inputs,config,ops,scenario)
        finally:ev.Observer=old
        arrays[name]=a
        diagnostics[name]=monitor.diagnostic()
        phase_masks[name]=np.asarray(monitor.phase_ticks)
        return a,info
    previous=ev.replay
    try:
        ev.replay=replay
        result=ev.score(events,refs,configs,f.OPS,fault)
    finally:ev.replay=previous
    for internal,public in aliases.items():
        if internal!=public:
            result['runtime'][public]=result['runtime'].pop(internal)
            for scores in result['receivers'].values():scores[public]=scores.pop(internal)
    t=arrays[BASE][:,0]
    for name,a in arrays.items():
        if a.shape!=arrays[BASE].shape or not np.array_equal(a[:,0],t):raise AssertionError('Exact schedule mismatch '+name)
    result['input_sha256']=hashlib.sha256(events.tobytes()).hexdigest()
    result['timestamps_sha256']=hashlib.sha256(t.tobytes()).hexdigest()
    result['reference_mask_sha256']={}
    result['diagnostics']=diagnostics
    result['clean_phases']={}
    for receiver,values in refs.items():
        target=ex.match(values,t);mask=np.isfinite(target)
        if fault:mask &= (t>=fault['start']) & (t<fault['end']+10.)
        result['reference_mask_sha256'][receiver]=hashlib.sha256(np.packbits(mask).tobytes()).hexdigest()
        if clean_phases:
            # Baseline and candidate share the same external, vehicle-only masks.
            result['clean_phases'][receiver]={str(phase):{name:ex.metrics(t,a[:,1],target,mask & (phase_masks[BASE]==phase))
                for name,a in arrays.items()} for phase in (-1,0,1)}
    return result


def diagnostic_scenarios(events):
    grid=ex.grid_channels(events)
    if grid is None:return [],['no_vehicle_grid']
    t,u,front,rear,valid=grid
    wheel=(front+rear)*.5
    result=[];missing=[]
    for phase in (1,-1):
        ok=valid & (np.abs(wheel)>1.) & (t>=25.) & (t<=t[-1]-25.)
        ok &= u>.09 if phase==1 else u<-.09
        ii=np.flatnonzero(ok)
        if not len(ii):missing.append('no_'+str(phase)+'_anchor');continue
        anchor=float(t[ii[0]])
        for channels in ((1,),(2,)):
            for sign in (-1,1):
                result.append(dict(kind='h20_diagnostic',form='bias',phase=phase,channels=channels,amplitude=sign*.3,start=anchor,end=anchor+4.))
                result.append(dict(kind='h20_diagnostic',form='gradual',phase=phase,channels=channels,amplitude=sign*.8,start=anchor,end=anchor+4.))
        for sign in (-1,1):
            result.append(dict(kind='h20_diagnostic',form='gradual',phase=phase,channels=(1,2),amplitude=sign*.8,start=anchor,end=anchor+4.))
        result.append(dict(kind='h20_diagnostic',form='lock',phase=phase,channels=(1,2),amplitude=0.,start=anchor,end=anchor+3.))
    return result,missing


def inject(events,fault):
    window=events[(events[:,0]>=fault['start']-20.) & (events[:,0]<=fault['end']+10.1)].copy()
    mask=np.isin(window[:,1],fault['channels']) & (window[:,0]>=fault['start']) & (window[:,0]<fault['end'])
    if fault['form']=='lock':window[mask,2]=0.
    else:
        mult=1.
        if fault['form']=='gradual':mult=np.maximum(0.,1.-np.abs(window[mask,0]-fault['start']-2.)/2.)
        window[mask,2]+=fault['amplitude']*mult
    return window


def worker(args):
    bag,role,output,names=args;out=Path(output)
    store=RoleStore(role,out/'access'/f'{bag}.json')
    events,refs=store.load(bag,role)
    metadata=dict(bag=bag,group=store.records[bag]['group'],role=role)
    clean=dict(**metadata,**paired(events,refs,names,check_disabled=True,clean_phases=True))
    stress=[dict(**metadata,fault=fault,**paired(window,refs,names,fault,check_disabled=True))
            for fault,window in guarded.fault_windows(events)]
    extra=[];missing=[]
    if role=='development':
        cases,missing=diagnostic_scenarios(events)
        for fault in cases:
            extra.append(dict(**metadata,fault=fault,**paired(inject(events,fault),refs,names,fault)))
    result=dict(clean=clean,stress=stress,diagnostic_faults=extra,missing_anchors=missing,access=store.access)
    save(out/'bags'/f'{bag}.json',result)
    print('BAG',bag,'clean_ticks',clean['outputs'],'original_faults',len(stress),'diagnostic_faults',len(extra),flush=True)
    return result


def extra_safety(rows,name):
    reasons=[]
    for row in rows:
        if row['runtime'][name]['causal_errors'] or row['runtime'][name]['resets']:reasons.append('causality_or_reset:'+row['bag'])
        for receiver,scores in row['receivers'].items():
            a,b=scores[name],scores[BASE];label=row['bag']+'/'+receiver+'/'+str(row.get('fault','clean'))
            if a['n']!=b['n'] or a['coverage']!=b['coverage']:reasons.append('coverage:'+label)
            if a.get('false_stop_samples',0)>b.get('false_stop_samples',0):reasons.append('false_stops:'+label)
            if b.get('event_rmse') is not None and b.get('recovery_s') is not None and a.get('recovery_s') is None:
                reasons.append('new_unrecovered:'+label)
    return sorted(set(reasons))


def contract(clean,stress,names,require_gain):
    summaries={name:legacy.summary(clean,stress,name) for name in [BASE]+names}
    # Only aliases enter the legacy function; its formulas and thresholds unchanged.
    aliased=[]
    for rows in (clean,stress):
        copied=[]
        for row in rows:
            new=dict(row);new['runtime']=dict(row['runtime'])
            new['runtime']['v5_adaptive_05s']=new['runtime']['v4_default']=row['runtime'][BASE]
            new['receivers']={k:dict(v, v5_adaptive_05s=v[BASE],v4_default=v[BASE]) for k,v in row['receivers'].items()}
            copied.append(new)
        aliased.append(copied)
    base=summaries[BASE]
    if any(base.get(k) is None for k in ('clean_rmse','fault_rmse','distance_rmse','pooled_rmse')):
        return summaries,{n:['insufficient_reference_data'] for n in names},None
    # Explicit absolute zero guard instead of legacy division by zero.
    legacy_decision=None
    if all(base[k]>0 for k in ('clean_rmse','fault_rmse','distance_rmse')):
        legacy_decision=legacy.decide(*aliased,['v4_default','v5_adaptive_05s']+names)
    reasons={}
    for name in names:
        a=summaries[name]
        problems=list(legacy_decision['candidates'][name]['rejection_reasons']) if legacy_decision else []
        if not require_gain:problems=[p for p in problems if p!='insufficient_gain']
        for key,limit in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
            if a[key] is None or a[key]>base[key]*(1+limit)+(1e-12 if base[key]==0 else 0):problems.append('aggregate:'+key)
        if legacy_decision is None:
            gain=any(base[k]>0 and a[k] is not None and 1-a[k]/base[k]>=minimum for k,minimum in [('clean_rmse',.02),('fault_rmse',.05)])
            if require_gain and not gain:problems.append('insufficient_gain')
            for row in clean:
                for receiver,s in row['receivers'].items():
                    if s[BASE]['rmse'] is not None and (s[name]['rmse'] is None or s[name]['rmse']>s[BASE]['rmse']+max(.005,.05*s[BASE]['rmse'])):
                        problems.append('bag_regression:'+row['bag']+'/'+receiver)
        problems+=extra_safety(clean+stress,name)
        reasons[name]=sorted(set(problems))
    return summaries,reasons,legacy_decision


def coverage_and_safety(clean,extras,names):
    results={}
    for name in names:
        groups=defaultdict(lambda:Counter());changed=0;accepted=0;signs=Counter()
        for row in clean:
            d=row['diagnostics'][name];changed+=d['changed_updates'];accepted+=d['accepted_updates']
            groups[row['group']].update(d['confirmed_mode_seconds']);signs.update(d['innovation_signs'])
        sufficient=[g for g,v in groups.items() if v.get('1',0)>=5 and v.get('-1',0)>=5]
        diag_signs=Counter()
        for row in extras:diag_signs.update(row['diagnostics'][name]['innovation_signs'])
        enough=(changed>=200 and len(sufficient)>=2 and diag_signs.get('weighted:1:positive',0)>0 and diag_signs.get('weighted:-1:negative',0)>0)
        problems=extra_safety(extras,name)
        for row in clean:
            for receiver,phases in row['clean_phases'].items():
                for phase,scores in phases.items():
                    a,b=scores[name]['rmse'],scores[BASE]['rmse']
                    if b is not None and (a is None or a>b+max(.005,.05*b)):
                        problems.append('clean_phase_regression:'+row['bag']+'/'+receiver+'/'+phase)
        results[name]=dict(sufficient=bool(enough),changed_updates=changed,accepted_updates=accepted,
            changed_fraction=changed/accepted if accepted else None,
            group_seconds={k:dict(v) for k,v in groups.items()},sufficient_groups=sufficient,
            clean_innovation_signs=dict(signs),diagnostic_innovation_signs=dict(diag_signs),
            safety_reasons=sorted(set(problems)))
    return results


def cost(events,names):
    cfg=ex.Config(**f.profile()[0]);result=[]
    # Warm each implementation on the same prefix; output collection identical.
    for name in [BASE]+names:
        old=ev.Observer
        try:
            ev.Observer=lambda _,n=name:f.baseline() if n==BASE else f.candidate(VARIANTS[n])
            REPLAY(events[:min(3000,len(events))],cfg,f.OPS)
        finally:ev.Observer=old
    class Timed:
        def __init__(self,inner):self.inner=inner;self.ns=0;self.steps=0
        def __getattr__(self,k):return getattr(self.inner,k)
        def reset(self,**kw):self.inner.reset(**kw);self.ns=0;self.steps=0
        def step(self,*a,**kw):
            start=time.process_time_ns();out=self.inner.step(*a,**kw);self.ns+=time.process_time_ns()-start;self.steps+=1;return out
    for name in names:
        for repetition in range(6):
            order=[BASE,name] if repetition%2==0 else [name,BASE]
            for current in order:
                obj=Timed(f.baseline() if current==BASE else f.candidate(VARIANTS[current]));old=ev.Observer
                try:
                    ev.Observer=lambda _:obj
                    cpu=time.process_time();wall=time.perf_counter()
                    array,info=REPLAY(events,cfg,f.OPS)
                    wall=time.perf_counter()-wall;cpu=time.process_time()-cpu
                finally:ev.Observer=old
                result.append(dict(candidate_pair=name,repetition=repetition,order=order,name=current,
                    replay_cpu_s=cpu,replay_wall_s=wall,step_cpu_s=obj.ns/1e9,step_calls=obj.steps,outputs=len(array),
                    output_sha256=hashlib.sha256(array[:,:3].tobytes()).hexdigest()))
    return dict(threads={k:os.getenv(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
                rows=result,includes_output_collection=True,includes_diagnostic_last_state=True,
                ros_latency_measured=False,rss_measured=False)


def csv_export(path,clean,stress,extras,names):
    fields=['suite','bag','group','receiver','model','fault','n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples','distance_rmse']
    with Path(path).open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
        for suite,rows in [('clean',clean),('original_fault',stress),('diagnostic_fault',extras)]:
            for row in rows:
                for receiver,scores in row['receivers'].items():
                    for name in [BASE]+names:
                        m=scores[name]
                        w.writerow(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,model=name,
                            fault=json.dumps(row.get('fault',{}),sort_keys=True),distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m'),
                            **{k:m.get(k) for k in fields if k in ('n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples')}))


def synthetic(names):
    """Prespecified diagnostics, independent generated truth is external only."""
    results=[]
    for direction in (1,-1):
        for mismatch in (0.,.35,-.35):
            for faultkind in ('clean','common_smooth','dropout'):
                cfg,readout=f.profile();cfg=cfg|{'travel_direction':float(direction)}
                plant=f.BASE.core.Observer(f.BASE.core.Config(**cfg))
                observers={BASE:f.BASE.guarded_readout.GuardedReadoutObserver(f.BASE.core.Config(**cfg),readout=f.BASE.guarded_readout.ReadoutConfig(**readout))}
                observers.update({n:f.AsymmetricObserver(f.CANDIDATE.core.Config(**cfg),alpha=VARIANTS[n],readout=f.CANDIDATE.guarded_readout.ReadoutConfig(**readout)) for n in names})
                for obj in observers.values():obj.reset(velocity=direction*8.)
                v=direction*8.;drive=0.;rows=defaultdict(list);truth=[];phase=[];activation=Counter()
                for j in range(800):
                    t=j*.05;u=.6 if t<12 else 0. if t<18 else -.6 if t<30 else .6
                    target=plant.drive_target(u,v);drive+=(1-math.exp(-.05/cfg['actuator_tau_s']))*(target-drive)
                    a=drive-plant.resistance(v)+direction*mismatch
                    vnext=v+.05*a
                    if u<=cfg['command_deadband'] and vnext*v<0:vnext=0.
                    v=vnext;truth.append(v);phase.append(1 if u>0 else -1 if u<0 else 0)
                    command=f.BASE.core.Sample(t,u)
                    noise=.04*math.sin(j*1.7)
                    z=v+noise
                    if faultkind=='common_smooth' and 5<=t<9:z+=direction*.8*max(0.,1-abs(t-7)/2)
                    wheels=(None,None) if faultkind=='dropout' and 5<=t<9 else (f.BASE.core.Sample(t,z),f.BASE.core.Sample(t,v-noise if faultkind!='common_smooth' else z))
                    for name,obj in observers.items():
                        e=obj.step(t,command,*wheels);rows[name].append(e.v)
                        d=getattr(obj,'_h20_diag',None)
                        if d and d['changed']:activation[name]+=1
                target=np.asarray(truth);t=np.arange(800)*.05;phase=np.asarray(phase)
                scores={str(p):{name:ex.metrics(t,np.asarray(vals),target,phase==p) for name,vals in rows.items()} for p in (-1,0,1)}
                results.append(dict(direction=direction,model_mismatch=mismatch,fault=faultkind,scores=scores,activation=dict(activation)))
    reasons={n:[] for n in names}
    for row in results:
        if row['fault']!='clean':continue
        for phase,scores in row['scores'].items():
            for n in names:
                a,b=scores[n]['rmse'],scores[BASE]['rmse']
                if b is not None and (a is None or a>b+max(.005,.05*b)):
                    reasons[n].append(f"synthetic_clean_mismatch_regression:{row['direction']}:{row['model_mismatch']}:{phase}")
    return dict(rows=results,safety_reasons=reasons,accuracy_evidence=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['development','validation'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    if not 1<=args.workers<=2:raise ValueError('workers must be 1 or 2')
    hashes=source_hashes();root=args.output
    if args.stage=='development':
        root.mkdir(parents=True,exist_ok=False);names=list(VARIANTS)
    else:
        freeze=json.loads((root/'FREEZE.json').read_text())
        publication=json.loads((root/'FREEZE_PUBLICATION.json').read_text())
        if not publication.get('commit_sha') or freeze['source_hashes']!=hashes:raise ValueError('Missing published freeze or source changed')
        if freeze['development_results_sha256']!=f.sha(root/'development/results.json'):raise ValueError('Development evidence changed')
        names=[freeze['selected']]
    stage=root/args.stage;stage.mkdir(exist_ok=False)
    provenance=dict(baseline_sha=f.BASELINE,measured_source_sha=source_sha(),effective_profile=f.profile(),operational=f.OPS,
        source_hashes=hashes,python=platform.python_version(),numpy=np.__version__,stage=args.stage,variants={n:VARIANTS[n] for n in names},
        test_payloads_opened=False,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(stage/'started.json',provenance)
    store=ex.Store();bags=store.plan['splits'][args.stage]
    clean=[];stress=[];extras=[];access=[];missing={}
    started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(worker,[(bag,args.stage,str(stage),names) for bag in bags]):
            clean.append(result['clean']);stress.extend(result['stress']);extras.extend(result['diagnostic_faults']);access+=result['access']
            missing[result['clean']['bag']]=result['missing_anchors']
    summaries,reasons,legacy_decision=contract(clean,stress,names,require_gain=args.stage=='validation')
    diagnostics=coverage_and_safety(clean,extras,names) if args.stage=='development' else {}
    synth=synthetic(names) if args.stage=='development' else None
    for name in names:
        if args.stage=='development':
            reasons[name]+=diagnostics[name]['safety_reasons']+synth['safety_reasons'][name]
    result=dict(provenance=provenance,clean=clean,stress=stress,diagnostic_faults=extras,missing_anchors=missing,
        summaries=summaries,reasons=reasons,legacy_decision=legacy_decision,coverage=diagnostics,synthetic=synth,
        wall_s=time.perf_counter()-started)
    save(stage/'results.json',result);save(stage/'summary.json',summaries);save(stage/'access.json',dict(test_payloads_opened=False,access=access))
    csv_export(stage/'per_bag.csv',clean,stress,extras,names)
    if args.stage=='development':
        # Cost runs use the first bag in the fixed split, regardless of accuracy.
        coststore=RoleStore('development',stage/'cost_access.json')
        events,_=coststore.load(bags[0],'development')
        save(stage/'cost.json',dict(bag=bags[0],**cost(events,names)))
        eligible=[n for n in names if not reasons[n] and diagnostics[n]['sufficient']]
        if eligible:
            selected=min(eligible,key=lambda n:(summaries[n]['fault_rmse'],summaries[n]['clean_rmse'],VARIANTS[n]))
            save(root/'FREEZE.json',dict(selected=selected,alpha=VARIANTS[selected],measured_source_sha=source_sha(),
                source_hashes=hashes,baseline_sha=f.BASELINE,development_results_sha256=f.sha(stage/'results.json'),
                data_sha256={bag:store.records[bag]['sha256'] for bag in store.plan['splits']['development']+store.plan['splits']['validation']},
                split_sha256=f.sha(ROOT/'research/split_v3.json'),effective_profile=f.profile(),operational=f.OPS,
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
            verdict='READY_FOR_FREEZE_PUBLICATION'
        else:
            selected=None
            verdict='REJECTED' if all(diagnostics[n]['sufficient'] for n in names) else 'INCONCLUSIVE'
        save(stage/'OUTCOME.json',dict(verdict=verdict,stage='development',selected=selected,reasons=reasons,coverage=diagnostics,
             validation_opened=False,merge_ready=False,ros_candidate_benchmark_performed=False))
    else:
        selected=names[0]
        save(stage/'OUTCOME.json',dict(verdict='REJECTED' if reasons[selected] else 'ACCURACY_PASSED_RUNTIME_PENDING',
            stage='validation',selected=selected,reasons=reasons,validation_opened=True,merge_ready=False,
            ros_candidate_benchmark_performed=False))
    print(json.dumps({'stage':args.stage,'summaries':summaries,'reasons':reasons},indent=2),flush=True)

if __name__=='__main__':main()

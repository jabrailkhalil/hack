"""H16: two preregistered recursive calibrations; canonical runtime is unchanged."""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import datetime as dtm
from functools import partial, lru_cache
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import sqlite3
import struct
import subprocess
import sys
import time
import csv
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/finalization'),str(ROOT/'tools/research_guarded'),str(ROOT/'tools/research_v6'),str(ROOT/'src/reserve_odometry')]
import numpy as np
import scipy
from scipy.optimize import least_squares
import evaluate as ev
from reserve_odometry.core import Config,Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig
from reserve_odometry.timeline import Timeline

def module_at(name,relative):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

gc=module_at('h16_guarded_compare','tools/research_guarded/compare.py')
v6=module_at('h16_v6_compare','tools/research_v6/compare.py')
BASE='65bba39ed05c781f3f69a65c02f69931152cbfd9'
PLAN_COMMIT='49cd275b8d1169ef1344f5b201f71eaff635aab3'
HERE=Path(__file__).resolve().parent
PROFILE=ROOT/'src/reserve_odometry/config/guarded_readout_v7.json'
OPS={'rate_hz':20.,'alignment_delay_s':0.}
NAMES=list(ev.ex.NAMES);LOW,HIGH=ev.ex.LOW.copy(),ev.ex.HIGH.copy()
HORIZONS=np.array([.5,2.,5.]);HINDEX=[9,39,99];SIGMA=.1+.2*HORIZONS
PHYSICAL=('total_motor_torque_nm','max_power_w','max_brake_force_n','rolling_force_n','quadratic_drag_n_s2_m2','command_exponent','actuator_tau_s')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def new_dir(path):
    path=Path(path);path.mkdir(parents=True,exist_ok=False);return path

@lru_cache(maxsize=1)
def _canonical_config():
    p=json.loads(PROFILE.read_text())
    assert p['readout']=={'gain':1.,'holdoff_s':.5}
    assert p['config']['wheel_time_compensation']==0. and p['config']['adaptation_tau_s']==.5
    c=Config(**p['config']);yaml={}
    for line in PROFILE.with_suffix('.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith('model.'):yaml[k[6:]]=float(v)
    assert yaml==asdict(c),'Effective canonical YAML differs'
    return asdict(c)

def base_config():return Config(**_canonical_config())
def theta_from(c):
    return np.array([c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m/c.mass_kg,c.max_power_w/c.mass_kg,c.max_brake_force_n/c.mass_kg,c.rolling_force_n/c.mass_kg,c.quadratic_drag_n_s2_m2/c.mass_kg,c.command_exponent,c.actuator_tau_s])
THETA0=theta_from(base_config());SCALE=np.maximum(np.abs(THETA0),.1*(HIGH-LOW))

def config_for(theta=None,enabled=True):
    c=base_config()
    if not enabled or theta is None or np.array_equal(theta,THETA0):return c
    x=np.asarray(theta,dtype=float)
    if x.shape!=(7,) or not np.all(np.isfinite(x)) or np.any(x<LOW) or np.any(x>HIGH):raise ValueError('Invalid effective physical coefficients')
    f,p,b,r,d,g,t=map(float,x)
    c.total_motor_torque_nm=f*c.mass_kg*c.wheel_radius_m/(c.efficiency*c.gear_ratio)
    c.max_power_w=p*c.mass_kg;c.max_brake_force_n=b*c.mass_kg;c.rolling_force_n=r*c.mass_kg
    c.quadratic_drag_n_s2_m2=d*c.mass_kg;c.command_exponent=g;c.actuator_tau_s=t;c.__post_init__()
    candidate_dict=asdict(c)
    assert all(candidate_dict[k]==_canonical_config()[k] for k in candidate_dict if k not in PHYSICAL)
    return c

def observer(theta=None,enabled=True):return GuardedReadoutObserver(config_for(theta,enabled),readout=ReadoutConfig(1.,.5))
def check_integrity():
    m=json.loads((HERE/'manifest.json').read_text());assert m['baseline']==BASE
    for p,digest in m['immutable_sha256'].items():
        if sha(ROOT/p)!=digest:raise ValueError('Immutable source mismatch: '+p)
    return m

def source_hashes():
    result=check_integrity()['immutable_sha256'].copy()
    for name in ('run.py','test_h16.py','PLAN.md','manifest.json'):
        p=HERE/name
        if p.exists():result[str(p.relative_to(ROOT))]=sha(p)
    return result

def provenance(stage):
    return dict(stage=stage,round='R2-v7-fixed',hypothesis='H16',baseline=BASE,plan_commit=PLAN_COMMIT,
                source_ref=os.getenv('H16_SOURCE_SHA',os.getenv('GITHUB_SHA','local-working-copy')),
                utc=dtm.datetime.now(dtm.timezone.utc).isoformat(),source_sha256=source_hashes(),
                python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,operations=OPS,test_evaluated=False)

class Store(ev.ex.Store):
    """Role checked before SQLite; original train/validation loader preserved."""
    def __init__(self,journal=None):super().__init__();self.journal=journal
    def load(self,bag,purpose):
        row=self.records[bag]
        if purpose not in ('train','development','validation') or row['split']!=purpose:raise PermissionError('H16 role denied before SQLite: '+bag+'/'+purpose)
        topics=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose!='train' else [])
        self.access.append(dict(bag=bag,purpose=purpose,sha256=row['sha256'],topics=topics,read_only=True))
        if self.journal:save(self.journal,dict(test_evaluated=False,access=self.access))
        if purpose in ('train','validation'):
            before=len(self.access);events,refs=super().load(bag,purpose);self.access=self.access[:before];return events,refs
        path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=row['sha256']:raise ValueError('DB checksum mismatch')
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name IN ('+','.join('?' for _ in topics)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,topics):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs

@dataclass
class Window:
    bag:str
    group:str
    phase:str
    anchor:float
    warmup:list
    times:np.ndarray
    commands:list
    target:np.ndarray

def input_ticks(events):
    tl=Timeline(observer(),rate_hz=20.,delay_s=0.);rows=[]
    for t,ch,value in events:
        tl.ingest(int(ch),Sample(float(t),float(value)))
        for e,held in tl.advance():rows.append((e.t,held))
    return rows

def windows_for(events,bag,group):
    rows=input_ticks(events);n=len(rows)
    if n<202:return [],dict(bag=bag,group=group,windows=0,reason='short_stream')
    good=np.zeros(n,bool);phase=np.full(n,'coast',object);y=np.full(n,np.nan);c=base_config()
    for i,(t,held) in enumerate(rows):
        u,f,r=held
        if not all(x is not None and 0<=t-x.t+1e-9<=age+1e-9 and math.isfinite(x.value) for x,age in zip(held,(c.command_timeout_s,c.max_age_s,c.max_age_s))):continue
        y[i]=(f.value+r.value)*.5
        good[i]=(abs(u.value)<=1 and abs(f.t-r.t)<=c.pair_skew_s and abs(f.value-r.value)<=.15 and .5<y[i]<35)
        phase[i]='traction' if u.value>.04 else 'braking' if u.value<-.04 else 'coast'
    bad=np.r_[0,np.cumsum(~good)]
    eligible=np.array([i for i in range(100,n-100) if rows[i][0]>=10 and bad[i+101]==bad[i-100]],int)
    result=[];counts={}
    for label in ('traction','coast','braking'):
        ids=eligible[phase[eligible]==label];counts[label]=int(len(ids))
        if not len(ids):continue
        i=int(ids[len(ids)//2]);ts=np.array([row[0] for row in rows[i+1:i+101]])
        result.append(Window(bag,group,label,rows[i][0],rows[i-100:i+1],ts,[row[1][0] for row in rows[i+1:i+101]],y[i+np.array([10,40,100])]))
    return result,dict(bag=bag,group=group,windows=len(result),eligible_by_phase=counts)

def warm_states(theta,windows):
    c=config_for(theta);states=[]
    for w in windows:
        o=GuardedReadoutObserver(c,readout=ReadoutConfig(1.,.5))
        for t,held in w.warmup:o.step(t,*held)
        if not o.initialized:raise AssertionError('Causal warmup did not initialize')
        states.append((o.v,o.drive_a,o.disturbance))
    return np.asarray(states,float)

def rollout_from_states(theta,states,times,commands,anchors):
    """OFFLINE vectorized legacy drive-before-Euler, no wheel/target argument."""
    c=config_for(theta);v,drive,d=states.T.copy();out=[];previous=anchors.copy()
    for j in range(times.shape[1]):
        delta=times[:,j]-previous;previous=times[:,j];u=commands[:,j]
        q=np.minimum(1.,np.maximum(0.,(np.abs(u)-c.command_deadband)/(1-c.command_deadband)))**c.command_exponent
        force=np.minimum(c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m,c.max_power_w/np.maximum(np.abs(v),1.))
        target=np.where(u>=0,c.travel_direction*q*force/c.mass_kg,-np.tanh(v/.20)*q*c.max_brake_force_n/c.mass_kg)
        drive+=(1-np.exp(-delta/c.actuator_tau_s))*(target-drive)
        resistance=(c.rolling_force_n*np.tanh(v/.20)+c.quadratic_drag_n_s2_m2*v*np.abs(v))/c.mass_kg
        acceleration=np.clip(drive-resistance+d,-c.max_accel_mps2,c.max_accel_mps2)
        predicted=np.clip(v+delta*acceleration,-c.max_speed_mps,c.max_speed_mps)
        v=np.where((u<=c.command_deadband)&(v*predicted<0),0.,predicted);out.append(v.copy())
    a=np.stack(out,axis=1)
    if not np.all(np.isfinite(a)):raise AssertionError('Nonfinite open loop')
    return a

def predict_windows(theta,windows):
    if not windows:return np.empty((0,3))
    states=warm_states(theta,windows);times=np.stack([w.times for w in windows]);anchors=np.array([w.anchor for w in windows])
    timeout=_canonical_config()['command_timeout_s']
    commands=np.array([[0. if s is None or t-s.t>timeout or t<s.t-1e-9 or abs(s.value)>1.000001 else min(1.,max(-1.,s.value)) for t,s in zip(w.times,w.commands)] for w in windows])
    return rollout_from_states(theta,states,times,commands,anchors)[:,HINDEX]

def original_rollout(theta,w):
    o=observer(theta)
    for t,held in w.warmup:o.step(t,*held)
    f,r=w.warmup[-1][1][1:];out=[]
    for t,u in zip(w.times,w.commands):out.append(o.step(float(t),u,f,r).v)
    return np.array(out)[HINDEX]

def summarize_proxy(theta,windows,split_groups):
    pred=predict_windows(theta,windows);target=np.stack([w.target for w in windows]) if windows else np.empty((0,3));records=[]
    for w,p,y,e in zip(windows,pred,target,pred-target):
        records.append(dict(bag=w.bag,group=w.group,phase=w.phase,anchor=w.anchor,role='check' if w.group in split_groups else 'fitting',prediction=p.tolist(),wheel_pseudo_target=y.tolist(),error=e.tolist()))
    summary={}
    for role in ('fitting','check'):
        rows=[r for r in records if r['role']==role];groups=sorted({r['group'] for r in rows})
        if not rows:summary[role]=None;continue
        gstats={}
        for g in groups:
            e=np.array([r['error'] for r in rows if r['group']==g]);x=e/SIGMA
            gstats[g]=dict(n=len(e),rmse=np.sqrt(np.mean(e*e,axis=0)).tolist(),mae=np.mean(abs(e),axis=0).tolist(),bias=np.mean(e,axis=0).tolist(),loss=float(np.mean(2*x*x/(np.sqrt(1+x*x)+1))))
        phases={}
        for ph in ('traction','coast','braking'):
            selected=[r for r in rows if r['phase']==ph];pg=[]
            for g in sorted({r['group'] for r in selected}):
                e=np.array([r['error'] for r in selected if r['group']==g]);pg.append(np.sqrt(np.mean(e*e,axis=0)))
            phases[ph]=dict(windows=len(selected),groups=len(pg),rmse=np.mean(pg,axis=0).tolist() if pg else None)
        summary[role]=dict(groups=gstats,windows=len(rows),loss=float(np.mean([s['loss'] for s in gstats.values()])),rmse=np.mean([s['rmse'] for s in gstats.values()],axis=0).tolist(),mae=np.mean([s['mae'] for s in gstats.values()],axis=0).tolist(),bias=np.mean([s['bias'] for s in gstats.values()],axis=0).tolist(),phases=phases)
    return dict(summary=summary,windows=records)

def group_dependence(base,cand):
    b=base['summary']['check'];c=cand['summary']['check']
    if b is None or c is None:return dict(passed=False,reasons=['missing_check'])
    reasons=[]
    if c['rmse'][2]>b['rmse'][2]*1.25 and c['rmse'][2]-b['rmse'][2]>.05:reasons.append('check_macro_5s_regression')
    worse=[g for g in b['groups'] if c['groups'][g]['rmse'][2]>b['groups'][g]['rmse'][2]*1.2 and c['groups'][g]['rmse'][2]-b['groups'][g]['rmse'][2]>.05]
    if len(worse)>len(b['groups'])/2:reasons.append('majority_check_groups_regressed')
    return dict(passed=not reasons,reasons=reasons,worse_groups=worse,check_groups=len(b['groups']))

def train(output):
    output=new_dir(output);save(output/'started.json',provenance('train'));s=Store(output/'access.json')
    groups=sorted({r['group'] for r in s.records.values() if r['split']=='train'});check=set(groups[::4]);windows=[];inventory=[]
    for bag in s.plan['splits']['train']:
        events,refs=s.load(bag,'train');assert not any(refs.values())
        w,info=windows_for(events,bag,s.records[bag]['group']);windows.extend(w);inventory.append(info);print('TRAIN_WINDOWS',bag,len(w),flush=True)
    fit=[w for w in windows if w.group not in check];chk=[w for w in windows if w.group in check];phases=Counter(w.phase for w in windows)
    coverage=dict(fitting_groups=len({w.group for w in fit}),check_groups=len({w.group for w in chk}),fitting_windows=len(fit),check_windows=len(chk),phases=dict(phases))
    sufficient=(coverage['fitting_groups']>=8 and coverage['check_groups']>=3 and len(fit)>=30 and len(chk)>=9 and all(phases[p]>=5 for p in ('traction','coast','braking')))
    save(output/'windows.json',dict(inventory=inventory,check_groups=sorted(check),fitting_groups=sorted(set(groups)-check),coverage=coverage,sufficient=sufficient))
    if not sufficient:save(output/'decision.json',dict(verdict='INCONCLUSIVE',reason='insufficient_window_coverage'));return
    fast=predict_windows(THETA0,windows);slow=np.stack([original_rollout(THETA0,w) for w in windows])
    delta=float(np.max(abs(fast-slow)));assert delta<1e-10,delta
    save(output/'rollout_parity.json',dict(windows=len(windows),max_absolute_delta=delta,passed=True))
    base=summarize_proxy(THETA0,windows,check);save(output/'baseline_proxy.json',base)
    count=Counter(w.group for w in fit);ng=len(count);weights=np.array([1./(ng*count[w.group]*3) for w in fit])[:,None]
    y=np.stack([w.target for w in fit]);models={};started=time.perf_counter()
    for name,regularization in [('A',0.),('B',.01)]:
        calls=0
        def residual(x):
            nonlocal calls
            calls+=1;r=(predict_windows(x,fit)-y)/SIGMA
            z=(r*np.sqrt(2./(np.sqrt(1+r*r)+1))*np.sqrt(weights)).ravel()
            if regularization:z=np.r_[z,np.sqrt(regularization/7)*(x-THETA0)/SCALE]
            if calls%20==0:print('FIT_CALL',name,calls,'loss',float(z@z),flush=True)
            return z
        started_fit=time.perf_counter()
        result=least_squares(residual,THETA0,bounds=(LOW,HIGH),jac='2-point',method='trf',loss='linear',x_scale=SCALE,max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        theta=result.x;proxy=summarize_proxy(theta,windows,check);jac_singular=np.linalg.svd(result.jac*SCALE[None,:],compute_uv=False)
        models[name]=dict(theta=theta.tolist(),config=asdict(config_for(theta)),readout=asdict(ReadoutConfig()),regularization=regularization,success=bool(result.success),status=int(result.status),message=result.message,nfev=int(result.nfev),njev=int(result.njev),residual_calls=calls,objective=float(2*result.cost),elapsed_s=time.perf_counter()-started_fit,active_mask=result.active_mask.tolist(),near_bounds=[NAMES[j] for j in range(7) if min(theta[j]-LOW[j],HIGH[j]-theta[j])<=1e-5*(HIGH[j]-LOW[j])],scaled_jac_singular_values=jac_singular.tolist(),group_dependence=group_dependence(base,proxy),proxy=proxy)
        save(output/(name+'.json'),models[name]);export_yaml(output/(name+'.yaml'),config_for(theta));print('FIT_FINISHED',name,result.nfev,calls,models[name]['objective'],flush=True)
    save(output/'results.json',dict(**provenance('train_complete'),theta0=THETA0.tolist(),scale=SCALE.tolist(),low=LOW.tolist(),high=HIGH.tolist(),horizons_s=HORIZONS.tolist(),sigma=SIGMA.tolist(),check_groups=sorted(check),coverage=coverage,baseline_proxy=base,models=models,elapsed_s=time.perf_counter()-started))

def export_yaml(path,c):
    text=PROFILE.with_suffix('.yaml').read_text();lines=[]
    for line in text.splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith('model.'):line='    '+k+': '+str(asdict(c)[k[6:]])
        lines.append(line)
    Path(path).write_text('# H16 research calibration; canonical guarded executable, NOT auto-deployment\n'+'\n'.join(lines)+'\n')

class Trace:
    """External diagnostics only; fault metadata never reaches the estimator."""
    def __init__(self,fault=None,reference=None):
        self.fault=fault;self.modes=Counter();self.phases=Counter();self.digest=hashlib.sha256();self.trace=[];self.next_trace=-math.inf
        self.n=0;self.changed=0;self.reference=reference;self.values=[];self.d_limit=0
    def accept(self,o,e,args):
        self.n+=1;self.digest.update(struct.pack('d',e.t));self.modes[e.mode]+=1
        cmd=args[0] if args else None;u=cmd.value if cmd is not None and not e.command_stale else 0.
        self.phases['traction' if u>.04 else 'braking' if u<-.04 else 'coast']+=1
        if abs(e.disturbance)>=o.c.disturbance_limit_mps2-1e-12:self.d_limit+=1
        if self.reference is not None and self.n<=len(self.reference):self.changed+=int(abs(e.v-self.reference[self.n-1])>1e-10)
        self.values.append(e.v);f=self.fault
        if f and f['start']-2<=e.t<=f['end']+2 and e.t>=self.next_trace:
            self.next_trace=e.t+.5
            self.trace.append(dict(t=e.t,published_v=e.v,inner_v=o.v,drive_a=o.drive_a,disturbance=e.disturbance,published_s=e.s,mode=e.mode,front=e.front_status,rear=e.rear_status))
    def metadata(self):return dict(ticks=self.n,timestamp_sha256=self.digest.hexdigest(),modes=dict(self.modes),phases=dict(self.phases),changed_velocity_ticks=self.changed,disturbance_at_limit_ticks=self.d_limit,fault_trace=self.trace)

def paired(events,refs,theta,fault=None,diagnostics=True):
    sinks=[]
    def factory(config):
        sink=Trace(fault,sinks[0].values if sinks else None);sinks.append(sink)
        class Traced(GuardedReadoutObserver):
            def step(self,t,*args,**kw):
                e=super().step(t,*args,**kw);sink.accept(self,e,args);return e
        return Traced(config,readout=ReadoutConfig(1.,.5))
    prev=ev.Observer
    try:
        ev.Observer=factory if diagnostics else partial(GuardedReadoutObserver,readout=ReadoutConfig(1.,.5))
        result=ev.score(events,refs,{'baseline_v2':base_config(),'balanced_physics':config_for(theta)},OPS,fault)
    finally:ev.Observer=prev
    for metrics in result['receivers'].values():
        for key in ('front_scaled','mean_scaled'):metrics.pop(key,None)
        metrics['main']=metrics.pop('baseline_v2');metrics['candidate']=metrics.pop('balanced_physics')
    result['runtime']={('main' if k=='baseline_v2' else 'candidate'):v for k,v in result['runtime'].items()}
    if diagnostics:
        assert len(sinks)==2 and sinks[0].n==sinks[1].n and sinks[0].digest.digest()==sinks[1].digest.digest(),'Exact output grid changed'
        result['diagnostics']={k:s.metadata() for k,s in zip(('main','candidate'),sinks)}
    return result

def compare_bag(bag,role,theta,out):
    store=Store(out/'access_by_bag'/(bag+'.json'));events,refs=store.load(bag,role);meta=dict(bag=bag,group=store.records[bag]['group'],role=role)
    clean=dict(**meta,**paired(events,refs,theta));stress=[]
    for fault,window in gc.fault_windows(events):stress.append(dict(**meta,fault=fault,**paired(window,refs,theta,fault)))
    save(out/'bags'/(bag+'.json'),dict(clean=clean,stress=stress));print(role.upper(),bag,flush=True);return clean,stress,store.access

def gt(a,b,relative=0.):return a>b*(1+relative) if b!=0 else a>1e-12

def admission(clean,stress,require_gain=True):
    sums={n:v6.summary(clean,stress,n) for n in ('main','candidate')};b,c=sums['main'],sums['candidate'];reasons=[];changes={}
    for k,tol in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        if b[k] is None or c[k] is None:reasons.append('missing_aggregate:'+k);changes[k]=None;continue
        changes[k]=dict(absolute=c[k]-b[k],relative=c[k]/b[k]-1 if b[k] else None)
        if gt(c[k],b[k],tol):reasons.append('aggregate_regression:'+k)
    gain=any(changes.get(k) is not None and changes[k]['relative'] is not None and changes[k]['relative']<=-threshold for k,threshold in [('clean_rmse',.02),('fault_rmse',.05)])
    if require_gain and not gain:reasons.append('insufficient_gain')
    for rows,cl in [(clean,True),(stress,False)]:
        for row in rows:
            for n in ('main','candidate'):
                runtime=row['runtime'][n]
                if runtime['causal_errors'] or runtime['resets']:reasons.append('causality_or_reset:'+n+':'+row['bag'])
            for receiver,ms in row['receivers'].items():
                bm,cm=ms['main'],ms['candidate'];tag=row['bag']+'/'+receiver
                if bm['n']!=cm['n'] or bm['coverage']!=cm['coverage']:reasons.append('coverage:'+tag)
                if cm.get('false_stop_samples',0)>bm.get('false_stop_samples',0):reasons.append('false_stops:'+tag)
                if cl and bm['rmse'] is not None and (cm['rmse'] is None or cm['rmse']>bm['rmse']+max(.005,.05*bm['rmse'])):reasons.append('per_bag_clean:'+tag)
                if not cl and bm.get('event_rmse') is not None and bm.get('recovery_s') is not None and cm.get('recovery_s') is None:reasons.append('new_unrecovered:'+tag)
    for n in sums:
        sums[n]['clean_mae']=v6.macro(clean,n,'mae');sums[n]['clean_signed_bias']=v6.macro(clean,n,'bias')
        sums[n]['fault_window_mae']=v6.macro(stress,n,'mae');sums[n]['fault_window_signed_bias']=v6.macro(stress,n,'bias');sums[n]['recovery_mean_s']=v6.macro(stress,n,'recovery_s')
    return dict(eligible=not reasons,rejection_reasons=sorted(set(reasons)),summary=sums,change=changes,gain_passed=gain,require_gain=require_gain)

def csv_results(out,clean,stress):
    rows=[]
    for label,rs in [('clean',clean),('fault',stress)]:
        for row in rs:
            for receiver,models in row['receivers'].items():
                for n,m in models.items():
                    flat={k:v for k,v in m.items() if not isinstance(v,dict)};flat['distance_rmse']=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                    rows.append(dict(stage=label,bag=row['bag'],group=row['group'],receiver=receiver,model=n,**row.get('fault',{}),**flat))
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (out/'per_bag.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def replay_set(role,theta,out,require_gain):
    out=new_dir(out);save(out/'started.json',provenance(role));store=Store();clean=[];stress=[];access=[]
    for bag in store.plan['splits'][role]:
        c,fs,a=compare_bag(bag,role,theta,out);clean.append(c);stress.extend(fs);access.extend(a)
    decision=admission(clean,stress,require_gain)
    result=dict(**provenance(role+'_complete'),theta=list(map(float,theta)),clean=clean,stress=stress,decision=decision,access=access)
    save(out/'results.json',result);save(out/'decision.json',decision);save(out/'access.json',access);csv_results(out,clean,stress);return result

def develop(train_dir,output):
    output=new_dir(output);save(output/'started.json',provenance('development'));data=json.loads((train_dir/'results.json').read_text());choices={};eligible=[]
    for name in ('A','B'):
        model=data['models'][name];safety_env=os.environ.copy();safety_env['H16_CANDIDATE_FILE']=str((train_dir/(name+'.json')).resolve())
        with (output/(name+'-safety.log')).open('w') as log:
            safety=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(HERE),'-p','test_h16.py','-v'],cwd=ROOT,env=safety_env,stdout=log,stderr=subprocess.STDOUT)
        if safety.returncode:raise AssertionError('Enabled candidate safety suite failed: '+name)
        r=replay_set('development',model['theta'],output/name,False)
        changes=sum(x['diagnostics']['candidate']['changed_velocity_ticks'] for x in r['clean'])
        groups=len({x['group'] for x in r['clean'] if x['diagnostics']['candidate']['changed_velocity_ticks']>0})
        active=changes>=100 and groups>=3 and np.max(abs((np.array(model['theta'])-THETA0)/SCALE))>1e-8
        reasons=list(r['decision']['rejection_reasons'])
        if not model['group_dependence']['passed']:reasons+=model['group_dependence']['reasons']
        if not np.all(np.isfinite(model['theta'])):reasons.append('solver_nonfinite')
        if not active:reasons.append('mechanism_coverage')
        choices[name]=dict(safety_passed=True,safety_log_sha256=sha(output/(name+'-safety.log')),eligible=not reasons,active=bool(active),changed_ticks=int(changes),changed_groups=groups,reasons=reasons,decision=r['decision'],group_dependence=model['group_dependence'])
        if not reasons:eligible.append(name)
    chosen=min(eligible,key=lambda n:(choices[n]['decision']['summary']['candidate']['fault_rmse'],choices[n]['decision']['summary']['candidate']['clean_rmse'],n!='B')) if eligible else None
    verdict='READY_FOR_FREEZE' if chosen else 'REJECTED' if all(x['active'] for x in choices.values()) else 'INCONCLUSIVE'
    save(output/'selection.json',dict(selected=chosen,verdict=verdict,choices=choices,validation_accessed=False,train_results_sha256=sha(train_dir/'results.json')));print('SELECTION',chosen,verdict,flush=True)

def freeze(train_dir,dev_dir,output):
    selection=json.loads((dev_dir/'selection.json').read_text())
    if selection['selected'] is None:raise PermissionError('No admissible development candidate; validation prohibited')
    name=selection['selected']
    if not selection['choices'][name]['safety_passed']:raise PermissionError('Safety barrier failed')
    out=new_dir(output);m=json.loads((train_dir/(name+'.json')).read_text());export_yaml(out/'candidate.yaml',config_for(m['theta']))
    save(out/'candidate.json',dict(name='H16_'+name,theta=m['theta'],config=m['config'],readout=m['readout']))
    save(out/'freeze.json',dict(**provenance('freeze'),candidate=name,theta=m['theta'],candidate_sha256=sha(out/'candidate.json'),yaml_sha256=sha(out/'candidate.yaml'),train_results_sha256=sha(train_dir/'results.json'),development_selection_sha256=sha(dev_dir/'selection.json'),validation_accessed=False))

def validate(freeze_path,freeze_commit,output,workers):
    f=json.loads(freeze_path.read_text());assert f['stage']=='freeze';rel=str(freeze_path.resolve().relative_to(ROOT))
    archived=subprocess.check_output(['git','show',freeze_commit+':'+rel],cwd=ROOT)
    if archived!=freeze_path.read_bytes():raise ValueError('Freeze commit barrier mismatch')
    if f['source_sha256']!=source_hashes():raise ValueError('Frozen algorithm/evaluator/PLAN changed')
    r=replay_set('validation',f['theta'],output,True)
    save(output/'freeze_link.json',dict(freeze_commit=freeze_commit,freeze_sha256=sha(freeze_path),workers_requested=workers,actual_workers=1,reason='deterministic sequential evaluator'));return r

def benchmark(candidate,output):
    out=new_dir(output);save(out/'started.json',provenance('benchmark'));item=json.loads(candidate.read_text());theta=item['theta'];s=Store(out/'access.json')
    events,_=s.load(s.plan['splits']['development'][0],'development');events=events[events[:,0]<=60.];runs=[]
    for pair_no,order in enumerate([('main','candidate'),('candidate','main')]*3):
        for name in order:
            durations=[]
            class Timed(GuardedReadoutObserver):
                def step(self,t,*a,**kw):
                    start=time.perf_counter_ns();e=super().step(t,*a,**kw)
                    if t>=10:durations.append(time.perf_counter_ns()-start)
                    return e
            prev=ev.Observer;ev.Observer=partial(Timed,readout=ReadoutConfig(1.,.5));startw=time.perf_counter();startc=time.process_time()
            try:array,counters=ev.replay(events,base_config() if name=='main' else config_for(theta),OPS)
            finally:ev.Observer=prev
            wall=time.perf_counter()-startw;cpu=time.process_time()-startc
            runs.append(dict(pair=pair_no,order=list(order),name=name,wall_s=wall,cpu_s=cpu,n_outputs=len(array),step_us=dict(zip(('p50','p95','p99'),map(float,np.quantile(durations,[.5,.95,.99])/1000))),maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,counters=counters,output_sha256=hashlib.sha256(array.tobytes()).hexdigest()))
    save(out/'results.json',dict(runs=runs,real_development=True,ros_latency_measured=False,memory_scope='process high-water RSS includes offline data/library allocations; not estimator-only RSS'))

def sanity(output):
    out=new_dir(output);save(out/'started.json',provenance('sanity'));s=Store(out/'access.json');bag=s.plan['splits']['development'][0];events,refs=s.load(bag,'development')
    factory=partial(GuardedReadoutObserver,readout=ReadoutConfig(1.,.5))
    array,info=gc.predict(events,(factory,base_config()));off,offinfo=gc.predict(events,(lambda c:observer(enabled=False),base_config()))
    assert np.array_equal(array,off,equal_nan=True) and info==offinfo
    result=paired(events,refs,THETA0);independent=gc.compare(events,refs,{'main':(factory,base_config()),'candidate':(factory,base_config())});fields=0
    for recv,scores in independent['receivers'].items():
        for name,m in scores.items():
            for k,v in m.items():
                assert result['receivers'][recv][name][k]==v,(recv,name,k);fields+=1
    assert result['runtime']==independent['runtime']
    save(out/'baseline_reproduction.json',dict(baseline=BASE,bag=bag,outputs=len(array),published_array_exact=True,runtime_counters_equal=True,metric_fields_equal=fields,max_absolute_delta=0.,counters=info,output_sha256=hashlib.sha256(array.tobytes()).hexdigest(),independent_driver='unchanged guarded.compare',factory='GuardedReadoutObserver(ReadoutConfig(1.0,0.5), guarded_readout_v7 config)'))
    print('SANITY_BASELINE_PASS',bag,len(array),fields,flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['sanity','train','develop','freeze','validate','benchmark'])
    p.add_argument('--output',required=True,type=Path);p.add_argument('--train',type=Path);p.add_argument('--development',type=Path);p.add_argument('--freeze',type=Path);p.add_argument('--freeze-commit');p.add_argument('--candidate',type=Path);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();check_integrity()
    if a.stage=='sanity':sanity(a.output)
    elif a.stage=='train':train(a.output)
    elif a.stage=='develop':develop(a.train,a.output)
    elif a.stage=='freeze':freeze(a.train,a.development,a.output)
    elif a.stage=='validate':validate(a.freeze,a.freeze_commit,a.output,a.workers)
    elif a.stage=='benchmark':benchmark(a.candidate,a.output)
if __name__=='__main__':main()

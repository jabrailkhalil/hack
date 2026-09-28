"""R3-H22 data/predictor helpers, adapted from immutable H16 9b382e3.
Targets are wheel proxies; no fitting or validation entry point in this module.
"""
from collections import Counter
from dataclasses import asdict, dataclass
import datetime as dtm
from functools import lru_cache
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
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/finalization'),str(ROOT/'tools/research_guarded'),str(ROOT/'tools/research_v6'),str(ROOT/'src/reserve_odometry')]
import numpy as np
import scipy
import evaluate as ev
from reserve_odometry.core import Config,Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver,ReadoutConfig
from reserve_odometry.timeline import Timeline

def module_at(name,relative):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

gc=module_at('h22_guarded_compare','tools/research_guarded/compare.py')
v6=module_at('h22_v6_compare','tools/research_v6/compare.py')
BASE='e3b0c9c039d2953fbfcda51231263d38ef9f1024'
HERE=Path(__file__).resolve().parent
PROFILE=ROOT/'src/reserve_odometry/config/champion_v8.json'
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
    assert p['config']['common_mode_quarantine_s']==1.5
    yaml={}
    for line in PROFILE.with_suffix('.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith('model.'):yaml[k[6:]]=float(v)
    c=Config(**yaml)
    assert yaml==asdict(c)==p['config'],'Effective canonical YAML differs'
    return asdict(c)

def base_config():return Config(**_canonical_config())
def theta_from(c):
    return np.array([c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m/c.mass_kg,c.max_power_w/c.mass_kg,c.max_brake_force_n/c.mass_kg,c.rolling_force_n/c.mass_kg,c.quadratic_drag_n_s2_m2/c.mass_kg,c.command_exponent,c.actuator_tau_s])
THETA0=theta_from(base_config());SCALE=np.maximum(np.abs(THETA0),.1*(HIGH-LOW))

def config_for(theta=None,enabled=True):
    c=base_config()
    if not enabled or theta is None or np.array_equal(theta,THETA0):return c
    x=np.asarray(theta,dtype=float)
    if x.shape!=(7,) or not np.all(np.isfinite(x)) or np.any(x<LOW) or np.any(x>HIGH):raise ValueError('Invalid physical coefficients')
    f,p,b,r,d,g,t=map(float,x)
    c.total_motor_torque_nm=f*c.mass_kg*c.wheel_radius_m/(c.efficiency*c.gear_ratio)
    c.max_power_w=p*c.mass_kg;c.max_brake_force_n=b*c.mass_kg;c.rolling_force_n=r*c.mass_kg
    c.quadratic_drag_n_s2_m2=d*c.mass_kg;c.command_exponent=g;c.actuator_tau_s=t;c.__post_init__()
    assert all(asdict(c)[k]==_canonical_config()[k] for k in asdict(c) if k not in PHYSICAL)
    return c

def observer(theta=None,enabled=True):return GuardedReadoutObserver(config_for(theta,enabled),readout=ReadoutConfig(1.,.5))

def check_integrity():
    manifest=HERE/'manifest.json'
    if not manifest.exists():
        files=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
        selected=[p for p in files if p.startswith(('src/','tests/','research/tests/','tools/')) or p in ('research/plan_v3.json','research/split_v3.json','requirements-research.txt','Dockerfile.environment','reports/champion_v7/LOW_SPEED_REPORT.md','research/H11_COMMON_MODE_PLAN.md')]
        expected={p:hashlib.sha256(subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT)).hexdigest() for p in selected}
        save(manifest,dict(baseline=BASE,immutable_sha256=expected))
    m=json.loads(manifest.read_text());assert m['baseline']==BASE
    for p,digest in m['immutable_sha256'].items():
        if sha(ROOT/p)!=digest:raise ValueError('Immutable source mismatch: '+p)
    return m

def source_hashes():
    result=check_integrity()['immutable_sha256'].copy()
    for p in sorted(HERE.glob('*')):
        if p.is_file():result[str(p.relative_to(ROOT))]=sha(p)
    return result

def provenance(stage):
    return dict(stage=stage,round='R3-v8-fixed',hypothesis='R3-H22',baseline=BASE,
        source_ref=os.getenv('GITHUB_SHA','local-working-copy'),utc=dtm.datetime.now(dtm.timezone.utc).isoformat(),
        source_sha256=source_hashes(),python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,operations=OPS,test_evaluated=False)

class Store(ev.ex.Store):
    """Only train/development; check role and hash before read-only SQLite IO."""
    def __init__(self,journal=None):super().__init__();self.journal=journal
    def load(self,bag,purpose):
        row=self.records[bag]
        if purpose not in ('train','development') or row['split']!=purpose:raise PermissionError('H22 role denied: '+bag+'/'+purpose)
        topics=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose=='development' else [])
        self.access.append(dict(bag=bag,purpose=purpose,sha256=row['sha256'],topics=topics,read_only=True))
        if self.journal:save(self.journal,dict(test_evaluated=False,access=self.access))
        if purpose=='train':
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
        result.append(Window(bag,group,label,rows[i][0],rows[i-100:i+1],ts,[row[1][0] for row in rows[i+1:i+101]],y[i:i+101].copy()))
    return result,dict(bag=bag,group=group,windows=len(result),eligible_by_phase=counts)

def warm_states(theta,windows):
    c=config_for(theta);states=[]
    for w in windows:
        o=GuardedReadoutObserver(c,readout=ReadoutConfig(1.,.5))
        for t,held in w.warmup:o.step(t,*held)
        if not o.initialized:raise AssertionError('Causal warmup did not initialize')
        states.append((o.v,o.drive_a,o.disturbance,o._velocity_correction,o._blocked_until,
                       min(x.t+c.max_age_s for x in w.warmup[-1][1][1:]),o.last_estimate.v))
    return np.asarray(states,float)

def rollout_from_states(theta,states,times,commands,anchors):
    """Offline recurrence with retained pre-window readout; no wheel targets."""
    c=config_for(theta);v,drive,d,corr,blocked,expires,initial=states.T.copy();out=[];previous=anchors.copy()
    for j in range(times.shape[1]):
        delta=times[:,j]-previous;previous=times[:,j];u=commands[:,j]
        q=np.minimum(1.,np.maximum(0.,(np.abs(u)-c.command_deadband)/(1-c.command_deadband)))**c.command_exponent
        force=np.minimum(c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m,c.max_power_w/np.maximum(np.abs(v),1.))
        target=np.where(u>=0,c.travel_direction*q*force/c.mass_kg,-np.tanh(v/.20)*q*c.max_brake_force_n/c.mass_kg)
        drive+=(1-np.exp(-delta/c.actuator_tau_s))*(target-drive)
        resistance=(c.rolling_force_n*np.tanh(v/.20)+c.quadratic_drag_n_s2_m2*v*np.abs(v))/c.mass_kg
        acceleration=np.clip(drive-resistance+d,-c.max_accel_mps2,c.max_accel_mps2)
        predicted=np.clip(v+delta*acceleration,-c.max_speed_mps,c.max_speed_mps)
        v=np.where((u<=c.command_deadband)&(v*predicted<0),0.,predicted)
        healthy=(times[:,j]<=expires+1e-9) & np.isfinite(u)
        blocked=np.where(healthy,blocked,times[:,j]+.5)
        corr=np.where(healthy & (times[:,j]>=blocked),corr,0.)
        published=np.clip(v+corr,-c.max_speed_mps,c.max_speed_mps)
        published=np.where(v*published<=0.,v,published);corr=published-v
        out.append(published.copy())
    a=np.stack(out,axis=1)
    if not np.all(np.isfinite(a)):raise AssertionError('Nonfinite open loop')
    return a

def predict_windows(theta,windows):
    if not windows:return np.empty((0,101))
    states=warm_states(theta,windows);times=np.stack([w.times for w in windows]);anchors=np.array([w.anchor for w in windows])
    commands=[]
    for w in windows:
        row=[]
        for t,s in zip(w.times,w.commands):
            if s is None or not -1e-9<=t-s.t<=_canonical_config()['command_timeout_s'] or abs(s.value)>1.000001:
                raise ValueError('Selected training window requires fresh causal commands')
            row.append(min(1.,max(-1.,s.value)))
        commands.append(row)
    forecast=rollout_from_states(theta,states,times,np.asarray(commands),anchors)
    return np.column_stack((states[:,6],forecast))

def original_rollout(theta,w):
    o=observer(theta)
    for t,held in w.warmup:o.step(t,*held)
    f,r=w.warmup[-1][1][1:];out=[o.last_estimate.v]
    for t,u in zip(w.times,w.commands):out.append(o.step(float(t),u,f,r).v)
    return np.array(out)

def proxy_errors(theta,windows):
    prediction=predict_windows(theta,windows);target=np.stack([w.target for w in windows]);errors=prediction-target
    intervals=np.diff(np.column_stack(([w.anchor for w in windows],np.stack([w.times for w in windows]))),axis=1)
    integrals=np.cumsum((errors[:,1:]+errors[:,:-1])*.5*intervals,axis=1)
    return errors[:,np.array(HINDEX)+1],integrals[:,HINDEX],prediction

def collect_windows(store):
    windows=[];inventory=[]
    for bag in store.plan['splits']['train']:
        events,refs=store.load(bag,'train');assert not any(refs.values())
        rows,meta=windows_for(events,bag,store.records[bag]['group']);windows.extend(rows);inventory.append(meta)
        print('TRAIN_WINDOWS',bag,len(rows),flush=True)
    return windows,inventory

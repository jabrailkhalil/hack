"""Preregistered wheel-only fitting and grouped validation. No final-test loader.
Run from repo root with --stage fit or validate. Default ROS config is untouched.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import platform
import sqlite3
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/reserve_odometry'),str(ROOT/'tools')]
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import lfilter,savgol_filter
from reserve_odometry.core import Config,Observer,Sample
from reserve_odometry.timeline import Timeline
from export_bags import decode
from manifest import digest,freeze
CHANNELS={'/vehicle/driver_position_cmd':0,'/vehicle/front_bogie_velocity':1,'/vehicle/rear_bogie_velocity':2}
REFS={'/sensing/gnss/master/vel':'master','/sensing/gnss/rover/vel':'rover'}
REPORTS=ROOT/'reports/research_v3'
MODELS=ROOT/'src/reserve_odometry/config/candidates_v3'
NAMES=['force_per_mass','power_per_mass','brake_per_mass','rolling_per_mass','quadratic_per_mass','command_exponent','actuator_tau_s']
X0=np.array([1.8,7.5,1.625,.03,.0001,1.25,.35])
LOW=np.array([.05,1.,.05,0.,0.,.3,.05]); HIGH=np.array([5.,100.,5.,.4,.005,3.,3.])


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


class Store:
    """Role check is enforced before opening measurements; metadata is separate."""
    def __init__(self,root=ROOT/'dataset/data'):
        self.root=Path(root);self.plan=json.loads((ROOT/'research/plan_v3.json').read_text())
        path=ROOT/'research/split_v3.json'
        if not path.exists():freeze(self.root,path)
        if digest(path)!=self.plan['manifest_sha256']:raise ValueError('Frozen split hash mismatch')
        self.manifest=json.loads(path.read_text());self.records={r['bag']:r for r in self.manifest['records']};self.access=[]
        for role,names in self.plan['splits'].items():
            if set(names)!={r['bag'] for r in self.records.values() if r['split']==role}:raise ValueError('Split membership differs')

    def load(self,bag,purpose):
        r=self.records[bag]
        if purpose not in ('train','validation') or r['split']!=purpose:raise PermissionError('Measurement access denied: '+bag+' / '+purpose)
        path=self.root/bag/(bag+'_0.db3')
        if digest(path)!=r['sha256']:raise ValueError('DB checksum mismatch: '+bag)
        allowed=list(CHANNELS)+(list(REFS) if purpose=='validation' else [])
        events=[];refs={'master':[],'rover':[]};origin=r['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=decode(raw,typ);t=(stamp-origin)/1e9
                if topic in CHANNELS:
                    ch=CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[REFS[topic]].append((t,speed))
        self.access.append(dict(bag=bag,purpose=purpose,topics=allowed,sha256=r['sha256']))
        return np.asarray(events,float),refs


def grid_channels(events,dt=.1):
    series=[]
    for ch in range(3):
        a=events[events[:,1]==ch][:,[0,2]];a=a[np.argsort(a[:,0],kind='stable')]
        _,i=np.unique(a[:,0],return_index=True);series.append(a[i])
    if any(len(a)<2 for a in series):return None
    t=np.arange(0,events[:,0].max()+1e-8,dt);values=[];valid=np.ones(len(t),bool)
    for ch,a in enumerate(series):
        j=np.searchsorted(a[:,0],t,side='right')-1;ok=(j>=0);j=np.maximum(j,0)
        ok &= (t-a[j,0] <= (.5 if ch==0 else .25)) & np.isfinite(a[j,1])
        values.append(np.where(ok,a[j,1],0));valid &= ok
    return t,*values,valid


def training_set(store):
    result=[];stats=[]
    for bag in store.plan['splits']['train']:
        events,_=store.load(bag,'train');g=grid_channels(events)
        if g is None:stats.append(dict(bag=bag,selected=0));continue
        t,u,f,r,valid=g;v=(f+r)*.5
        if len(v)<11:stats.append(dict(bag=bag,selected=0));continue
        a=savgol_filter(v,11,2,deriv=1,delta=.1)
        clean=valid & (np.abs(f-r)<.15) & (v>.4) & (v<35) & (np.abs(u)<=1)
        clean=np.convolve(clean.astype(int),np.ones(11,int),mode='same')==11
        good=np.flatnonzero(clean & (t>2) & (np.abs(a)<2.5))
        rng=np.random.default_rng(int(hashlib.sha256((bag+store.plan['seed']).encode()).hexdigest()[:16],16))
        selected=np.sort(rng.choice(good,min(len(good),1500),replace=False))
        stats.append(dict(bag=bag,eligible=len(good),selected=len(selected)))
        if len(selected):result.append(dict(u=u,v=v,a=a,indices=selected,bag=bag,group=store.records[bag]['group']))
    if not result:raise ValueError('No training samples')
    return result,stats


def acceleration(theta,u,v,dt=.1):
    force,power,brake,roll,drag,gamma,tau=theta
    q=np.clip((np.abs(u)-.04)/.96,0,1)**gamma
    target=np.where(u>=0,q*np.minimum(force,power/np.maximum(abs(v),1)),-np.tanh(v/.2)*q*brake)
    alpha=1-np.exp(-dt/tau);drive=lfilter([alpha],[1,-(1-alpha)],target)
    return drive-roll*np.tanh(v/.2)-drag*v*np.abs(v)


def configuration(theta):
    force,power,brake,roll,drag,gamma,tau=map(float,theta);c=Config()
    # Fixed gauge, NOT separately identified real mass/radius/gear/torque.
    c.total_motor_torque_nm=force*c.mass_kg*c.wheel_radius_m/(c.efficiency*c.gear_ratio)
    c.max_power_w=power*c.mass_kg;c.max_brake_force_n=brake*c.mass_kg
    c.rolling_force_n=roll*c.mass_kg;c.quadratic_drag_n_s2_m2=drag*c.mass_kg
    c.command_exponent=gamma;c.actuator_tau_s=tau;c.__post_init__();return c


def fit_all(store):
    training,stats=training_set(store);group_n=Counter()
    for b in training:group_n[b['group']]+=len(b['indices'])
    modes=np.concatenate([np.sign(b['u'][b['indices']]) for b in training]);mode_n=Counter(modes)
    w=np.concatenate([np.full(len(b['indices']),1/math.sqrt(group_n[b['group']])) for b in training]);w/=np.sqrt(np.mean(w*w))
    balance=np.array([math.sqrt(len(modes)/(len(mode_n)*mode_n[x])) for x in modes])
    artifacts={'baseline_v2':dict(config=asdict(Config()),theta=X0.tolist(),fitted=False)}
    for name,cols,weight in [('gain_only',[0,1,2],w),('nonlinear_physics',list(range(7)),w),('balanced_physics',list(range(7)),w*balance)]:
        def residual(x):
            theta=X0.copy();theta[cols]=x
            return np.concatenate([(acceleration(theta,b['u'],b['v'])-b['a'])[b['indices']] for b in training])*weight
        start=time.perf_counter()
        fit=least_squares(residual,X0[cols],bounds=(LOW[cols],HIGH[cols]),loss='soft_l1',f_scale=.1,max_nfev=80,x_scale='jac')
        theta=X0.copy();theta[cols]=fit.x
        artifacts[name]=dict(fitted=True,config=asdict(configuration(theta)),theta=theta.tolist(),solver_success=bool(fit.success),
            status=int(fit.status),nfev=int(fit.nfev),cost=float(fit.cost),elapsed_s=time.perf_counter()-start,
            boundary_parameters=[NAMES[k] for k in cols if min(theta[k]-LOW[k],HIGH[k]-theta[k])<1e-5],
            weighted_accel_rmse=float(np.sqrt(np.mean(residual(fit.x)**2))))
        print('FIT',name,'theta',theta,'success',fit.success,flush=True)
    for name,model in artifacts.items():
        write_json(MODELS/(name+'.json'),model)
        text='reserve_odometry:\n  ros__parameters:\n    front_scale: 0.2777777777777778\n    rear_scale: 0.2777777777777778\n'
        text+=''.join('    model.'+k+': '+str(v)+'\n' for k,v in model['config'].items());(MODELS/(name+'.yaml')).write_text(text)
    write_json(REPORTS/'training.json',dict(stats=stats,parameters=NAMES,models=artifacts,train_access=store.access,
        train_samples=sum(x['selected'] for x in stats),label='Centered 1.1s Savitzky-Golay derivative of agreeing wheels; offline only',
        versions=dict(python=platform.python_version(),numpy=np.__version__,platform=platform.platform())))


def replay(events,config,fault=None,model_only=False):
    timeline=Timeline(Observer(config),rate_hz=20,delay_s=.06);outputs=[];model_only_started=False
    for t,ch,value in events:
        ch=int(ch)
        if fault and fault['start']<=t<fault['end']:
            if fault['kind']=='dropout' and ch in (1,2):continue
            if fault['kind']=='lock' and ch in (1,2):value=0.
            if fault['kind']=='bias' and ch==1:value+=5.
        if model_only and model_only_started and ch in (1,2):continue
        timeline.ingest(ch,Sample(t,value))
        for e,held in timeline.advance():
            if e.mode=='WAITING_FOR_INITIALIZATION':continue
            model_only_started=True
            wheels=[s.value if s is not None and 0<=e.t-s.t<=.25 else np.nan for s in held[1:]]
            outputs.append((e.t,e.v,e.s,wheels[0],sum(wheels)/2,int(e.mode=='STOPPED')))
    return np.asarray(outputs,float).reshape(-1,6),dict(resets=timeline.resets,dropped=timeline.dropped)


def match(reference,t):
    if not reference:return np.full(len(t),np.nan)
    ref=np.array(sorted(dict(reference).items()));j=np.clip(np.searchsorted(ref[:,0],t),0,len(ref)-1);prev=np.maximum(j-1,0)
    j=np.where(abs(ref[prev,0]-t)<abs(ref[j,0]-t),prev,j)
    return np.where(abs(ref[j,0]-t)<=.05,ref[j,1],np.nan)


def metrics(t,estimate,reference,mask):
    mask=mask & np.isfinite(estimate) & np.isfinite(reference);e=estimate[mask]-reference[mask]
    if not len(e):return dict(n=0,coverage=0.,rmse=None)
    edge=mask[1:] & mask[:-1] & (np.diff(t)<.051);er=estimate-reference
    return dict(n=len(e),coverage=float(mask.mean()),rmse=float(np.sqrt(np.mean(e*e))),mae=float(np.mean(abs(e))),
        bias=float(np.mean(e)),p95=float(np.quantile(abs(e),.95)),
        integrated_error_m_not_xyz=float(np.sum(((er[1:]+er[:-1])/2)[edge]*np.diff(t)[edge])))


def compare(events,refs,models,fault=None):
    predictions={};counts={};started=time.perf_counter()
    for name,c in models.items():predictions[name],counts[name]=replay(events,c,fault)
    baseline=predictions['baseline_v2'];t=baseline[:,0]
    if not len(t):return dict(outputs=0,receivers={},counts=counts)
    for name,a in predictions.items():
        if a.shape!=baseline.shape or not np.allclose(a[:,0],t,atol=1e-8,rtol=0):raise AssertionError('Candidate output schedule changed: '+name)
    results={}
    for receiver,reference in refs.items():
        target=match(reference,t);mask=np.isfinite(target)
        if fault:mask &= (t>=fault['start']) & (t<fault['end']+10)
        scores={name:metrics(t,a[:,1],target,mask) for name,a in predictions.items()}
        if not fault:
            for column,label in [(3,'front_scaled'),(4,'mean_scaled')]:
                common=mask & np.isfinite(baseline[:,column]);scores[label]=metrics(t,baseline[:,column],target,common)
                for name,a in predictions.items():scores[name]['on_wheel_common_rmse_'+label]=metrics(t,a[:,1],target,common)['rmse']
        else:
            for name,a in predictions.items():
                scores[name]['false_stop_samples']=int(np.sum(mask & (target>1) & (a[:,5]>0)))
                good=(abs(a[:,1]-target)<.25)&np.isfinite(target)&(t>=fault['end'])
                runs=np.convolve(good.astype(int),np.ones(20,int),mode='valid') if len(t)>=20 else np.array([])
                hits=np.flatnonzero(runs==20);scores[name]['recovery_s']=float(t[hits[0]]-fault['end']) if len(hits) else None
                scores[name]['event_rmse']=metrics(t,a[:,1],target,mask & (t<fault['end']))['rmse']
        results[receiver]=scores
    return dict(outputs=len(t),expected_ticks=int(np.floor((events[:,0].max()-events[:,0].min())*20))+1,
        source_duration_s=float(events[:,0].max()-events[:,0].min()),receivers=results,counts=counts,
        offline_compute_s=time.perf_counter()-started)


def select(clean,stress,names):
    """Preregistered gates. Missing reference is not zero error."""
    def usable(rows):
        return [(row,receiver,s) for row in rows for receiver,s in row['receivers'].items() if all(s[n]['rmse'] is not None for n in names)]
    pairs=usable(clean);fault_pairs=usable(stress)
    def macro(name,key='rmse',rows=pairs):
        groups={}
        for row,receiver,s in rows:
            if s[name].get(key) is not None:groups.setdefault(row['group'],[]).append(s[name][key])
        return float(np.mean([np.mean(x) for x in groups.values()])) if groups else None
    base=macro('baseline_v2');entries={}
    for name in names:
        score=macro(name);reasons=[]
        if name!='baseline_v2':
            if base is None or score is None or score>base*.98:reasons.append('less_than_2_percent_clean_gain')
            if any(s[name]['rmse']>s['baseline_v2']['rmse']+max(.01,.1*s['baseline_v2']['rmse']) for _,_,s in pairs):reasons.append('per_bag_regression')
            if any(s[name]['coverage']<s['baseline_v2']['coverage']-.005 for _,_,s in pairs):reasons.append('coverage_drop')
            b=macro('baseline_v2','event_rmse',fault_pairs);n=macro(name,'event_rmse',fault_pairs)
            if b is None or n is None or n>b*1.05:reasons.append('stress_event_rmse')
            if any(s[name]['false_stop_samples']>s['baseline_v2']['false_stop_samples'] for _,_,s in fault_pairs):reasons.append('false_stops')
        entries[name]=dict(macro_group_rmse=score,macro_fault_event_rmse=macro(name,'event_rmse',fault_pairs),
            relative_clean_gain=(base-score)/base if base and score is not None else None,rejection_reasons=reasons,eligible=not reasons)
    eligible=[n for n in names if entries[n]['eligible'] and entries[n]['macro_group_rmse'] is not None]
    winner=min(eligible,key=lambda n:entries[n]['macro_group_rmse']) if eligible else 'baseline_v2'
    return dict(selected=winner,validation_receiver_pairs=len(pairs),stress_receiver_cases=len(fault_pairs),candidates=entries,
        test_evaluated=False,requires_ros_validation_before_default_change=True)


def validate_bag(bag):
    store=Store()
    files=sorted(MODELS.glob('*.json'));models={f.stem:Config(**json.loads(f.read_text())['config']) for f in files}
    if set(models)!=set(store.plan['hypotheses']):raise ValueError('Unexpected candidate set')
    events,refs=store.load(bag,'validation');clean=dict(bag=bag,group=store.records[bag]['group'],**compare(events,refs,models))
    stress=[];g=grid_channels(events)
    if g is not None:
        t,u,f,r,valid=g;indices=np.flatnonzero(valid & ((f+r)/2>2) & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
        if len(indices):
            anchor=float(t[indices[0]])
            for kind,duration in [('bias',5.),('dropout',5.),('dropout',10.),('lock',3.)]:
                window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
                fault=dict(kind=kind,start=anchor,end=anchor+duration)
                stress.append(dict(bag=bag,group=store.records[bag]['group'],fault=fault,**compare(window,refs,models,fault)))
    print('VALIDATE',bag,{r:v['baseline_v2']['rmse'] for r,v in clean['receivers'].items()},flush=True)
    return clean,stress,store.access


def validate_all(store):
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=4) as pool:
        result=list(pool.map(validate_bag,store.plan['splits']['validation']))
    clean=[r[0] for r in result];stress=[s for r in result for s in r[1]];access=[a for r in result for a in r[2]]
    write_json(REPORTS/'validation.json',dict(clean=clean,stress=stress,access=access,test_evaluated=False,
        defaults_changed=False,split_sha256=store.plan['manifest_sha256']))
    decision=select(clean,stress,store.plan['hypotheses']);write_json(REPORTS/'decision.json',decision)
    print(json.dumps(decision,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['fit','validate'],required=True)
    args=p.parse_args();store=Store();(fit_all if args.stage=='fit' else validate_all)(store)

if __name__=='__main__':main()

"""One frozen H40 candidate, all development groups, unchanged official scorer.

Validation is intentionally not implemented: a separate published freeze and
explicit later authorization are required after every prospective R3 gate.
"""
import argparse, collections, copy, csv, datetime, hashlib, importlib.util, json, os, platform, sys, time, math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import common as cm
from common import np
from factory import candidate

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
v6=module('h40_fixed_v6_scoring',cm.ROOT/'tools/research_v6/compare.py')
h11=module('h40_fixed_h11_windows',cm.ROOT/'tools/research_h11/compare.py')
NAMES=('baseline_v8','H40_implicit_coulomb','feature_off')

def neutral(v):
    from dataclasses import is_dataclass,asdict
    if is_dataclass(v):return asdict(v)
    if isinstance(v,(tuple,list)):return [neutral(x) for x in v]
    if isinstance(v,dict):return {k:neutral(x) for k,x in v.items()}
    return v

class CheckedOff:
    def __init__(self):self.on=candidate(False);self.ref=cm.baseline();self.checked=0
    def __getattr__(self,k):return getattr(self.on,k)
    def reset(self):self.on.reset();self.ref.reset();self.checked=0
    def step(self,*args):
        out=self.on.step(*args);ref=self.ref.step(*args)
        if neutral(out)!=neutral(ref):raise AssertionError('Feature-off Estimate differs')
        for k,v in vars(self.ref).items():
            if neutral(v)!=neutral(getattr(self.on,k)):raise AssertionError('Feature-off state differs: '+k)
        self.checked+=1;return out

def low_windows(events):
    # Exact published PR13 low_speed.py predicate at f10e3cfc, reused on DEVELOPMENT.
    grid=cm.ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2) & (u>=0)
                      & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            yield dict(kind='lock',start=anchor,end=anchor+duration),events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]

def identity(row,receiver):
    return dict(bag=row['bag'],group=row['group'],receiver=receiver,fault=row.get('fault'))

def aggregate_rows(rows):
    return {n:dict(event_rmse=v6.macro(rows,n,'event_rmse'),window_rmse=v6.macro(rows,n,'rmse'),
       false_stops=v6.total(rows,n,'false_stop_samples'),unrecovered=v6.unrecovered(rows,n)) for n in NAMES[:2]}

def export(clean,stress,extras,output):
    records=[]
    for suite,rows in [('clean',clean),('original',stress),*extras.items()]:
        for row in rows:
            for recv,scores in row['receivers'].items():
                for n in NAMES[:2]:
                    m=scores[n];f=row.get('fault',{})
                    rec=dict(suite=suite,bag=row['bag'],group=row['group'],receiver=recv,model=n,
                      kind=f.get('kind'),duration_s=f.get('end',0)-f.get('start',0),start_s=f.get('start'),
                      **{k:m.get(k) for k in ('n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples')},
                      distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m'))
                    records.append(rec)
    with (output/'per_bag_receiver_fault.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    group_rows=[]
    for suite,rows in [('clean',clean),('original',stress),*extras.items()]:
        for g in sorted(set(r['group'] for r in rows)):
            subset=[r for r in rows if r['group']==g]
            for n in NAMES[:2]:group_rows.append(dict(suite=suite,group=g,model=n,
                **{k:v6.macro(subset,n,k) for k in ('rmse','mae','bias','event_rmse','distance')},
                false_stops=v6.total(subset,n,'false_stop_samples'),unrecovered=v6.unrecovered(subset,n)))
    cm.save(output/'per_group.json',group_rows)

class Timer:
    def __init__(self,obs):self.obs=obs;self.step_ns=0;self.calls=0
    def __getattr__(self,k):return getattr(self.obs,k)
    def reset(self):self.obs.reset();self.step_ns=0;self.calls=0
    def step(self,*args):
        start=time.process_time_ns();out=self.obs.step(*args);self.step_ns+=time.process_time_ns()-start;self.calls+=1;return out

def cost(output):
    bag=cm.ev.ex.Store().plan['splits']['development'][0]
    events,_,_=cm.load(bag,output/'cost-access.json',reference=False)
    rows=[]
    for repeat in range(-1,6):
        order=NAMES[:2] if repeat%2==0 else NAMES[1::-1]
        for name in order:
            obs=Timer(cm.baseline() if name==NAMES[0] else candidate())
            cpu,wall=time.process_time_ns(),time.perf_counter_ns();arr,info=cm.predict(events,obs)
            cpu,wall=time.process_time_ns()-cpu,time.perf_counter_ns()-wall
            if repeat>=0:rows.append(dict(repeat=repeat,model=name,step_cpu_ns=obs.step_ns,step_calls=obs.calls,
                replay_cpu_ns=cpu,replay_wall_ns=wall,outputs=len(arr),output_sha256=hashlib.sha256(arr.tobytes()).hexdigest()))
    summary={}
    for metric in ('step_cpu_ns','replay_cpu_ns','replay_wall_ns'):
        ratios=[]
        for j in range(6):
            x={r['model']:r[metric] for r in rows if r['repeat']==j};ratios.append(x[NAMES[1]]/x[NAMES[0]]-1)
        summary[metric+'_median_paired_overhead']=float(np.median(ratios))
    for name in NAMES[:2]:
        if len(set(r['output_sha256'] for r in rows if r['model']==name))!=1:raise AssertionError('Cost non-deterministic output')
    cm.save(output/'COST.json',dict(bag=bag,warmup_pairs=1,measured_pairs=6,order='AB/BA alternating',
       threads={k:os.getenv(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
       summary=summary,measurements=rows,qualification='Offline Python CPU/wall, not installed ROS latency/RSS'))


class Traced:
    """Offline collector only. Telemetry never becomes candidate input."""
    def __init__(self,obs):
        self.obs=obs;self.rows=[];self.counts=collections.Counter()
    def __getattr__(self,k):return getattr(self.obs,k)
    def reset(self):self.obs.reset();self.rows=[];self.counts=collections.Counter()
    def step(self,t,command=None,front=None,rear=None):
        from factory import prediction,clamp
        o=self.obs;dt=0 if o.t is None else t-o.t;v=o.v;d=o.disturbance
        ok=o._valid(command,t,o.c.command_timeout_s)
        stale=not ok or abs(command.value)>1.000001
        u=0 if stale else clamp(command.value,-1,1)
        drive=o.drive_a+(1-math.exp(-dt/o.c.actuator_tau_s))*(o.drive_target(u,v)-o.drive_a)
        a=clamp(drive-o.resistance(v)+d,-o.c.max_accel_mps2,o.c.max_accel_mps2)
        old=clamp(v+dt*a,-o.c.max_speed_mps,o.c.max_speed_mps)
        _,new=prediction(o.c,v,dt,drive,d)
        if u<=o.c.command_deadband:
            if v*old<0:old=0.
            if v*new<0:new=0.
        if dt>0 and 0<abs(v)<=.5 and abs(new-old)>=1e-4:self.counts['near_changed_predictions']+=1
        e=o.step(t,command,front,rear)
        if e.mode!='WAITING_FOR_INITIALIZATION':
            pair=all(o._valid(s,t,o.c.max_age_s) for s in (front,rear))
            healthy=pair and not stale and abs(front.value-rear.value)<.15
            speed=.5*(front.value+rear.value) if pair else 0.
            self.rows.append((t,u,healthy,speed,d,v,e.v==0.,e.mode=='STOPPED'))
        return e

def pair(events,refs,fault=None,*,full=False,clean_delta=None):
    bs,cs=Traced(cm.baseline()),Traced(candidate())
    observers={'baseline_v2':bs,'balanced_physics':cs}
    if not full:observers['feature_off']=CheckedOff()
    configs={n:o.c for n,o in observers.items()};by_config={id(configs[n]):observers[n] for n in observers}
    arrays={};old_obs,old_replay=cm.ev.Observer,cm.ev.replay
    def recording(e,c,ops,f=None):
        a,r=old_replay(e,c,ops,f);arrays[id(c)]=(a,r);return a,r
    try:
        cm.ev.Observer=lambda c:by_config[id(c)];cm.ev.replay=recording
        result=cm.ev.score(events,refs,configs,cm.OPS,fault)
    finally:cm.ev.Observer,cm.ev.replay=old_obs,old_replay
    b,br=arrays[id(configs['baseline_v2'])];c,cr=arrays[id(configs['balanced_physics'])]
    if not full:
        off,ofr=arrays[id(configs['feature_off'])]
        if not np.array_equal(b,off,equal_nan=True) or br!=ofr:raise AssertionError('Disabled replay differs')
    if b.shape!=c.shape or not np.array_equal(b[:,0],c[:,0]):raise AssertionError('Output schedule differs')
    for r in (br,cr):
        if r['causal_errors'] or r['resets']:raise AssertionError('Causality/reset failure')
    for src,dst in [('baseline_v2',NAMES[0]),('balanced_physics',NAMES[1])]:
        result['runtime'][dst]=result['runtime'].pop(src)
        for values in result['receivers'].values():values[dst]=values.pop(src)
    t=b[:,0];tele=np.asarray(bs.rows,float)
    if len(t)!=len(tele) or not np.array_equal(t,tele[:,0]):raise AssertionError('Telemetry schedule differs')
    phase_masks={'slow_roll':(tele[:,2]>0)&(tele[:,3]>=.07)&(tele[:,3]<=.5),
      'start':(tele[:,2]>0)&(tele[:,3]>=.07)&(tele[:,3]<=1)&(tele[:,1]>.09),
      'braking':(tele[:,2]>0)&(tele[:,3]>=.07)&(tele[:,1]<-.09),
      'coast':(tele[:,2]>0)&(tele[:,3]>=.07)&(abs(tele[:,1])<=.04)}
    masks={};phases={};low=[];dist={}
    for recv,vals in refs.items():
        target=cm.ev.ex.match(vals,t);valid=np.isfinite(target);mask=valid.copy()
        if fault:mask&=(t>=fault['start'])&(t<fault['end']+10.)
        masks[recv]=hashlib.sha256(mask.tobytes()).hexdigest()
        for n,a in zip(NAMES[:2],(b,c)):
            m=result['receivers'][recv][n]
            m['low_speed_stopped_proxy']=int(np.sum(mask&(target>=.07)&(target<=.5)&(a[:,5]>0)))
            m['zero_velocity_moving_proxy']=int(np.sum(mask&(target>=.07)&(target<=.5)&(a[:,1]==0)))
        if not fault:
            for phase,pm in phase_masks.items():
                phases.setdefault(phase,{})[recv]={n:cm.ev.ex.metrics(t,a[:,1],target,valid&pm) for n,a in zip(NAMES[:2],(b,c))}
        if full:
            dist[recv]={n:cm.ev.distance_surrogate(a,target) for n,a in zip(NAMES[:2],(b,c))}
            recovery=result['receivers'][recv][NAMES[0]].get('recovery_s')
            if recovery is not None:
                idx=int(np.searchsorted(t,fault['end']+recovery));idx=min(idx,len(t)-1)
                dist[recv]['delta_s_at_baseline_recovery_m']=float(c[idx,2]-b[idx,2])
            else:dist[recv]['delta_s_at_baseline_recovery_m']=None
    result['phases']=phases
    if full:
        result['full_safety']={}
        for recv,vals in refs.items():
            target=cm.ev.ex.match(vals,t); valid=np.isfinite(target)
            result['full_safety'][recv]={n:dict(false_stops=int(np.sum(valid&(target>1)&(a[:,5]>0))),low_stops=int(np.sum(valid&(target>=.07)&(target<=.5)&(a[:,5]>0)))) for n,a in zip(NAMES[:2],(b,c))}
    result['audit']=dict(schedule_sha256=hashlib.sha256(t.tobytes()).hexdigest(),reference_masks_sha256=masks,
      baseline_array_sha256=hashlib.sha256(b.tobytes()).hexdigest(),candidate_array_sha256=hashlib.sha256(c.tobytes()).hexdigest(),
      feature_off_exact=not full,feature_off_checked_ticks=observers['feature_off'].checked if not full else 0,
      max_output_velocity_difference=float(np.max(abs(c[:,1]-b[:,1]))) if len(t) else None,
      changed_outputs=int(np.sum(abs(c[:,1]-b[:,1])>1e-9)))
    result['activation']=dict(cs.counts)
    if full:
        idx=min(int(np.searchsorted(t,fault['end'])),len(t)-1)
        idx10=min(int(np.searchsorted(t,fault['end']+10)),len(t)-1)
        result['full_distance']=dist
        result['distance_residual']=dict(event_end_delta_s_m=float(c[idx,2]-b[idx,2]),
            recovery_window_end_delta_s_m=float(c[idx10,2]-b[idx10,2]),end_delta_s_m=float(c[-1,2]-b[-1,2]))
        at=min(int(np.searchsorted(t,fault['start'])),len(t)-1)
        result['load_proxy_at_fault']=dict(d=float(tele[at,4]),v=float(tele[at,5]),
          abs_d_ge_r0=bool(abs(tele[at,4])>=bs.c.rolling_force_n/bs.c.mass_kg),qualification='model state, not independent measured load')
    return result

def worker(arg):
    bag,output=arg;path=output/'bags'/(bag+'.json')
    if path.exists():raise FileExistsError('Existing checkpoint '+str(path))
    events,refs,group=cm.load(bag,output/'access'/(bag+'.json'),reference=True)
    meta=dict(bag=bag,group=group,role='development')
    clean=dict(**meta,**pair(events,refs));stress=[];low=[];common=[];full=[]
    for suite,windows in [('original',cm.legacy.fault_windows(events)),('low_speed',low_windows(events)),('common_mode',h11.common_fault_windows(events))]:
        for f,w in windows:
            changed=h11.inject_common(w,f) if suite=='common_mode' else w
            row=dict(**meta,fault=f,**pair(changed,refs,f))
            {'original':stress,'low_speed':low,'common_mode':common}[suite].append(row)
            whole=h11.inject_common(events,f) if suite=='common_mode' else events
            full.append(dict(**meta,suite=suite,fault=f,**pair(whole,refs,f,full=True)))
    data=dict(clean=clean,original=stress,low_speed=low,common_mode=common,full_faulted=full)
    cm.save(path,data);print(bag,'complete; full-faulted cases',len(full),flush=True)
    return data

def decide(clean,stress,extras,full):
    ac,af=copy.deepcopy(clean),copy.deepcopy(stress)
    for row in ac+af:
        row['runtime']['v5_adaptive_05s']=row['runtime'][NAMES[0]];row['runtime']['v4_default']=row['runtime'][NAMES[0]]
        for scores in row['receivers'].values():scores['v5_adaptive_05s']=scores[NAMES[0]];scores['v4_default']=scores[NAMES[0]]
    legacy=v6.decide(ac,af,['v4_default','v5_adaptive_05s',NAMES[1]])['candidates'][NAMES[1]]
    reasons=list(legacy['rejection_reasons']);violations=[]
    stats={n:v6.summary(clean,stress,n) for n in NAMES[:2]};b,c=stats[NAMES[0]],stats[NAMES[1]]
    expected={'clean_rmse':.09266814298282507,'fault_rmse':.2375486120563008,'pooled_rmse':.1293056944774334,'distance_rmse':5.310295004801444,'samples':394221}
    if any(b[k]!=val for k,val in expected.items()):raise AssertionError('Canonical fingerprint differs: '+str(b))
    if c['pooled_rmse']>b['pooled_rmse']*1.005:reasons.append('pooled_regression')
    suites=[('clean',clean),('original',stress),*extras.items(),('full_faulted',full)]
    for suite,rows in suites:
        for row in rows:
            for recv,s in row['receivers'].items():
                bm,cm_=s[NAMES[0]],s[NAMES[1]];checks=[]
                if bm['n']!=cm_['n'] or bm['coverage']!=cm_['coverage']:checks.append('coverage')
                for k in ('false_stop_samples','low_speed_stopped_proxy'):
                    if cm_[k]>bm[k]:checks.append('added_'+k)
                if bm.get('event_rmse') is not None and bm.get('recovery_s') is not None and cm_.get('recovery_s') is None:checks.append('new_individual_unrecovered')
                if checks:violations.append(dict(suite=suite,**identity(row,recv),violations=checks));reasons.extend(suite+':'+k for k in checks)
    for row in full:
        for recv,models in row['full_safety'].items():
            for key in ('false_stops','low_stops'):
                if models[NAMES[1]][key]>models[NAMES[0]][key]:
                    reasons.append('full_faulted:added_'+key)
                    violations.append(dict(suite='full_faulted',**identity(row,recv),violations=['added_'+key]))
    es={}
    for suite,rows in extras.items():
        es[suite]=aggregate_rows(rows);x,y=es[suite][NAMES[0]],es[suite][NAMES[1]]
        if x['event_rmse'] is None or y['event_rmse'] is None:reasons.append(suite+':missing_reference')
        elif y['event_rmse']>x['event_rmse']*1.005:reasons.append(suite+':event_regression')
    phase_stats={};phase_missing=False
    for phase in ('slow_roll','start','braking','coast'):
        phase_stats[phase]={}
        for name in NAMES[:2]:
            grouped=collections.defaultdict(list);ns=0
            for row in clean:
                for recv,models in row['phases'][phase].items():
                    m=models[name]
                    if m['rmse'] is not None:grouped[row['group']].append(m['rmse']);ns+=m['n']
            phase_stats[phase][name]=dict(rmse=float(np.mean([np.mean(v) for v in grouped.values()])) if grouped else None,groups=len(grouped),samples=ns)
        x,y=[phase_stats[phase][n]['rmse'] for n in NAMES[:2]]
        if x is None or y is None:
            if phase in ('slow_roll','start'):phase_missing=True;reasons.append(phase+':insufficient_reference')
        elif y>x*1.005:reasons.append(phase+':phase_rmse_regression')
    full_stats={}
    for suite in ('original','low_speed','common_mode'):
        rows=[r for r in full if r['suite']==suite];full_stats[suite]={}
        for n in NAMES[:2]:
            groups=collections.defaultdict(list)
            for row in rows:
                for recv,s in row['full_distance'].items():
                    val=s[n]['reanchored_span_rmse_m']
                    if val is not None:groups[row['group']].append(val)
            full_stats[suite][n]=float(np.mean([np.mean(v) for v in groups.values()])) if groups else None
        x,y=[full_stats[suite][n] for n in NAMES[:2]]
        if x is None or y is None:reasons.append(suite+':full_distance_missing')
        elif y>x*1.01:reasons.append(suite+':full_distance_regression')
    act=collections.Counter();groups=collections.Counter();changed=0
    for row in clean:
        act.update(row['activation']);groups[row['group']]+=row['activation'].get('near_changed_predictions',0);changed+=row['audit']['changed_outputs']
    covered=act['near_changed_predictions']>=100 and sum(v>=20 for v in groups.values())>=3 and changed>=100
    if not covered:reasons.append('insufficient_activation')
    scientific='REJECTED' if reasons else 'DEVELOPMENT_ADMITTED'
    if (not covered or phase_missing) and not violations:scientific='INCONCLUSIVE'
    return dict(summary=stats,baseline_fingerprint_exact=True,additional_suites=es,phase_metrics=phase_stats,
      full_faulted_distance_macro_rmse_m=full_stats,legacy_decision=legacy,contract_reasons=sorted(set(reasons)),
      individual_violations=violations,activation=dict(act),activation_groups=dict(groups),changed_outputs=changed,
      coverage_status='SUFFICIENT' if covered else 'INSUFFICIENT',scientific_verdict=scientific,
      accuracy_contract_evaluated=True,accuracy_contract_passed=not reasons,validation_opened=False,test_opened=False,
      freeze_sha=None,enabled_runtime_verified=False,ready_to_merge=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['development','cost','summarize'],default='development')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    p.add_argument('--begin',type=int,default=0);p.add_argument('--end',type=int,default=17)
    p.add_argument('--foundation',type=Path,required=True);a=p.parse_args()
    cm.verify();found=json.loads(a.foundation.read_text())
    if not found['foundation_passed']:raise RuntimeError('Failed prospective prerequisite')
    files=sorted(p for p in cm.HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    hashes={str(p.relative_to(cm.ROOT)):cm.sha(p) for p in files}
    started=a.output/'STARTED.json'
    if not started.exists():
        a.output.mkdir(parents=True,exist_ok=False)
        o=candidate();from dataclasses import asdict
        cm.save(started,dict(measured_source_sha=os.getenv('H40_SOURCE_SHA'),source_hashes=hashes,
          baseline_sha=cm.BASELINE,role='development',foundation_sha256=cm.sha(a.foundation),
          observer_class=type(o).__module__+'.'+type(o).__name__,factory_file=str(sys.modules[type(o).__module__].__file__),
          runtime_module_files={m.__name__:m.__file__ for m in (sys.modules['_r4_h40_runtime.core'],sys.modules['_r4_h40_runtime.guarded_readout'])},
          config=asdict(o.c),readout=asdict(o.readout),enabled=o._h40_enabled,python=platform.python_version(),numpy=np.__version__,
          created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    elif json.loads(started.read_text())['source_hashes']!=hashes:raise AssertionError('Resume source changed')
    if a.stage=='cost':cost(a.output);return
    bags=cm.ev.ex.Store().plan['splits']['development']
    if a.stage=='development':
        if not 0<=a.begin<a.end<=17:raise ValueError('Invalid fixed development slice')
        with ProcessPoolExecutor(max_workers=a.workers) as pool:list(pool.map(worker,[(b,a.output) for b in bags[a.begin:a.end]]))
    if a.stage=='summarize':
        if (a.output/'SUMMARY.json').exists():raise FileExistsError('Summary already published')
        rows=[json.loads((a.output/'bags'/(b+'.json')).read_text()) for b in bags]
        clean=[r['clean'] for r in rows];stress=[s for r in rows for s in r['original']]
        extras={n:[s for r in rows for s in r[n]] for n in ('low_speed','common_mode')}
        full=[s for r in rows for s in r['full_faulted']]
        result=decide(clean,stress,extras,full)
        result['counts']=dict(bags=17,groups=len(set(r['group'] for r in clean)),original_faults=len(stress),low_speed_faults=len(extras['low_speed']),common_mode_faults=len(extras['common_mode']),full_faulted_bag_replays=len(full),feature_off_checked_ticks=sum(r['audit']['feature_off_checked_ticks'] for r in clean+stress+sum(extras.values(),[])))
        cm.save(a.output/'SUMMARY.json',result);export(clean,stress,extras,a.output)
        print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()

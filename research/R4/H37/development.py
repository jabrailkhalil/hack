"""One preregistered H37 candidate, unchanged score and full-stream distance audit."""
import argparse, collections, gzip, hashlib, json, math
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from common import *
NAMES=('R4_v8','H37','off')
ALIASES=dict(baseline_v2='R4_v8',balanced_physics='H37',feature_off='off')

class Collector:
    """Offline instrumentation only. Runtime receives only the three Samples."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.out=[];self.trace=[];self.target_ticks=0
    def step(self,t,command=None,front=None,rear=None):
        oldv,oldd,oldt=self.v,self.disturbance,self.t
        valid=self._valid(command,t,self.c.command_timeout_s) and abs(command.value)<=1.000001
        u=max(-1.,min(1.,command.value)) if valid else 0.
        q,f,cap,a,b=targets(self.c,u,oldv)
        delta=b-a if u>0 else 0.
        if oldt is not None and valid and 0<q<1 and cap<f and abs(delta)>.02:self.target_ticks+=1
        e=super().step(t,command,front,rear)
        if e.mode!='WAITING_FOR_INITIALIZATION':
            self.out.append((e.t,e.v,e.s,int(e.mode=='STOPPED')))
            self.trace.append((t,u,oldv,oldd,self.drive_a,self.disturbance,delta,e.v,e.s,e.mode,e.front_status,e.rear_status))
        return e

class OffCheck:
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.reference=baseline(self.c)
    def reset(self,**kwargs):
        super().reset(**kwargs)
        if hasattr(self,'reference'):self.reference.reset(**kwargs)
    def step(self,*args,**kwargs):
        e=super().step(*args,**kwargs);ref=self.reference.step(*args,**kwargs)
        assert e==ref
        for k,v in vars(self.reference).items():assert v==getattr(self,k),k
        return e

def scored(events,refs,fault=None):
    # Import only after the prerequisite; no alternate formula hidden in score().
    from reserve_odometry.traction_power import TractionPowerObserver
    c,r=profile();models={key:Config(**asdict(c)) for key in ALIASES};instances={}
    def factory(cfg):
        key=next(k for k,v in models.items() if v is cfg);name=ALIASES[key]
        cls=GuardedReadoutObserver if name=='R4_v8' else TractionPowerObserver
        parents=(Collector,cls) if name!='off' else (Collector,OffCheck,cls)
        typ=type('H37Recorded'+name,parents,{})
        kw={} if name=='R4_v8' else {'enabled':name=='H37'}
        x=typ(cfg,readout=r,**kw);instances[name]=x;return x
    previous=ev.Observer
    try:
        ev.Observer=factory
        result=ev.score(events,refs,models,OPS,fault)
    finally:ev.Observer=previous
    for key,name in ALIASES.items():
        result['runtime'][name]=result['runtime'].pop(key)
        for metrics in result['receivers'].values():metrics[name]=metrics.pop(key)
    arrays={n:np.asarray(o.out,float).reshape(-1,4) for n,o in instances.items()}
    a=arrays['R4_v8']
    for n,v in arrays.items():
        assert v.shape==a.shape and np.array_equal(v[:,0],a[:,0]),'schedule'
        if result['runtime'][n]['causal_errors'] or result['runtime'][n]['resets']:raise AssertionError('causality/reset')
    assert np.array_equal(a,arrays['off'],equal_nan=True)
    assert result['runtime']['off']==result['runtime']['R4_v8']
    delta=arrays['H37'][:,1]-a[:,1]
    result['activation']=dict(target_ticks=instances['R4_v8'].target_ticks,
        effective_output_ticks=int(np.sum(np.abs(delta)>1e-6)),max_abs_v_delta=float(np.max(np.abs(delta))) if len(delta) else 0.)
    result['output_sha256']={n:hashlib.sha256(v.tobytes()).hexdigest() for n,v in arrays.items()}
    return result,arrays,instances

def windows(events):
    for fault,window in guarded.fault_windows(events):yield 'original',fault,window
    grid=ev.ex.grid_channels(events)
    if grid is not None:
        t,u,f,r,valid=grid
        low=np.flatnonzero(valid&(np.abs(f-r)<.15)&((f+r)/2>1)&((f+r)/2<2)&(u>=0)&(t>np.maximum(25.,.1*t[-1]))&(t<t[-1]-25))
        if len(low):
            start=float(t[low[0]])
            for duration in (3.,5.):
                fault=dict(kind='lock',start=start,end=start+duration)
                yield 'low_speed',fault,events[(events[:,0]>=start-20)&(events[:,0]<=start+duration+10.1)]
        neutral=np.abs(u)<=profile()[0].command_deadband
        traction=u>profile()[0].command_deadband
        hit=np.flatnonzero(neutral&np.r_[False,traction[:-1]]&valid&(np.abs(f-r)<.15)&((f+r)/2>.4)&(t>25)&(t<t[-1]-25))
        if len(hit):
            start=float(t[hit[0]])-.3;fault=dict(kind='dropout',start=start,end=start+5.)
            yield 'transition',fault,events[(events[:,0]>=start-20)&(events[:,0]<=start+5+10.1)]
    for f,w in h11.common_fault_windows(events):yield 'common_mode',f,w

def do_case(events,refs,suite,fault):
    changed=h11.inject_common(events,fault) if suite=='common_mode' else events
    # The old replay has no branch for common_bias: it only applies the supplied event mask.
    return scored(changed,refs,fault)

def full_audit(arrays,refs,fault):
    t=arrays['R4_v8'][:,0];b=arrays['R4_v8'];c=arrays['H37'];delta=c[:,2]-b[:,2]
    metrics={};residuals={}
    for recv,values in refs.items():
        target=ev.ex.match(values,t);mask=np.isfinite(target);metrics[recv]={}
        joint=mask&(t>=fault['end'])&(np.abs(b[:,1]-target)<.25)&(np.abs(c[:,1]-target)<.25)
        runs=np.convolve(joint.astype(int),np.ones(20,int),mode='valid') if len(t)>=20 else np.array([])
        hits=np.flatnonzero(runs==20);i=int(hits[0]) if len(hits) else None
        j=min(len(t)-1,int(np.searchsorted(t,t[i]+10))) if i is not None else None
        residuals[recv]=dict(common_recovery_s=float(t[i]-fault['end']) if i is not None else None,
            delta_s_at_recovery_m=float(delta[i]) if i is not None else None,
            delta_s_10s_later_or_end_m=float(delta[j]) if j is not None else None)
        for n,a in arrays.items():
            m=ev.ex.metrics(t,a[:,1],target,mask)
            m['false_stop_samples']=int(np.sum(mask&(target>1)&(a[:,3]>0)))
            m['distance_surrogate']=ev.distance_surrogate(a,target)
            metrics[recv][n]=m
    return dict(receivers=metrics,delta_s_end_m=float(delta[-1]) if len(delta) else None,
        max_abs_delta_s_m=float(np.max(np.abs(delta))) if len(delta) else None,residual_after_recovery=residuals)

def phase_metrics(events,refs,arrays):
    t=arrays['R4_v8'][:,0];grid=ev.ex.grid_channels(events)
    if grid is None:return {}
    tg,u,f,r,valid=grid;c,_=profile();modes=np.where(u>c.command_deadband,1,np.where(u< -c.command_deadband,-1,0))
    changes=np.flatnonzero(np.r_[False,modes[1:]!=modes[:-1]])
    mode_time=tg[changes];mode_value=modes[changes];j=np.searchsorted(mode_time,t,side='right')-1
    slices={}
    for value,name in ((1,'traction_first2s'),(0,'coast_first2s'),(-1,'brake_first2s')):
        slices[name]=(j>=0)&((t-mode_time[np.maximum(j,0)]<2) if len(mode_time) else False)&((mode_value[np.maximum(j,0)]==value) if len(mode_time) else False)
    g=np.searchsorted(tg,t,side='right')-1;g=np.maximum(g,0)
    force=c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m
    slices['partial_high_speed']=valid[g]&(u[g]>c.command_deadband)&(u[g]<1)&((f[g]+r[g])/2>c.max_power_w/force)
    result={}
    for name,phase in slices.items():
        result[name]={}
        for recv,values in refs.items():
            target=ev.ex.match(values,t);mask=np.isfinite(target)&phase
            result[name][recv]={n:ev.ex.metrics(t,a[:,1],target,mask) for n,a in arrays.items()}
    return result

def worker(args):
    bag,out=args;store=Store(out/'access'/f'{bag}.json');events,refs=store.load(bag,'development');meta=dict(bag=bag,group=store.records[bag]['group'])
    row,a,instances=scored(events,refs);clean=dict(**meta,**row)
    phases=phase_metrics(events,refs,a);rows=[]
    for i,(suite,fault,window) in enumerate(windows(events)):
        scored_row,_,obs=do_case(window,refs,suite,fault)
        with gzip.open(out/'traces'/f'{bag}-{i}.json.gz','wt') as f:
            json.dump(dict(suite=suite,fault=fault,columns=['t','u','old_v','old_d','drive_a','new_d','target_delta_same_state','v','s','mode','front_status','rear_status'],
                           traces={n:o.trace for n,o in obs.items() if n!='off'}),f,allow_nan=False)
        full,full_arrays,_=do_case(events,refs,suite,fault)
        audit=full_audit(full_arrays,refs,fault)
        rows.append(dict(**meta,suite=suite,fault=fault,**scored_row,full=dict(score=full,**audit)))
    result=dict(clean=clean,faults=rows,phases=phases,access=store.access)
    save(out/'bags'/f'{bag}.json',result);print('DEVELOPMENT',bag,len(rows),clean['activation'],flush=True);return result

def safety(rows):
    reasons=[]
    for row in rows:
        for recv,scores in row['receivers'].items():
            b,c=scores['R4_v8'],scores['H37'];key=row['bag']+'/'+recv
            if b['n']!=c['n'] or b['coverage']!=c['coverage']:reasons.append('coverage:'+key)
            if c.get('false_stop_samples',0)>b.get('false_stop_samples',0):reasons.append('false_stops:'+key)
            if b.get('recovery_s') is not None and c.get('recovery_s') is None:reasons.append('new_unrecovered:'+key)
    return sorted(set(reasons))

def decision(clean,rows):
    original=[r for r in rows if r['suite']=='original'];summary={n:group.summary(clean,original,n) for n in NAMES};b,c=summary['R4_v8'],summary['H37']
    fingerprint=dict(clean_rmse=.09266814298282507,fault_rmse=.2375486120563008,pooled_rmse=.1293056944774334,distance_rmse=5.310295004801444,samples=394221)
    errors={k:abs(b[k]-v) for k,v in fingerprint.items()}
    if any(d>1e-12 for d in errors.values()):raise AssertionError(('baseline_fingerprint',errors))
    reasons=safety(clean+rows)
    for row in rows:
        full=row['full'];reasons+=['full:'+s for s in safety([dict(bag=row['bag'],receivers=full['score']['receivers'])])]
        reasons+=['full_stream:'+s for s in safety([dict(bag=row['bag'],receivers=full['receivers'])])]
    gains={k:1-c[k]/b[k] for k in ('clean_rmse','fault_rmse')}
    if gains['clean_rmse']<.02 and gains['fault_rmse']<.05:reasons.append('insufficient_gain')
    for k,lim in (('clean_rmse',1.005),('fault_rmse',1.005),('pooled_rmse',1.005),('distance_rmse',1.01)):
        if c[k]>b[k]*lim:reasons.append('aggregate_regression:'+k)
    for r in clean:
        for recv,s in r['receivers'].items():
            bb,cc=s['R4_v8'],s['H37']
            if bb['rmse'] is not None and (cc['rmse'] is None or cc['rmse']>bb['rmse']+max(.005,.05*bb['rmse'])):reasons.append('per_bag:'+r['bag']+'/'+recv)
    suites={}
    for suite in ('original','low_speed','common_mode','transition'):
        subset=[r for r in rows if r['suite']==suite]
        suites[suite]={n:dict(event_rmse=group.macro(subset,n,'event_rmse'),mae=group.macro(subset,n,'mae'),p95=group.macro(subset,n,'p95'),bias=group.macro(subset,n,'bias'),recovery_s=group.macro(subset,n,'recovery_s'),unrecovered=group.unrecovered(subset,n)) for n in NAMES}
        if suite in ('low_speed','common_mode'):
            x=suites[suite]['R4_v8']['event_rmse'];y=suites[suite]['H37']['event_rmse']
            if x is None or y is None or y>x*1.005:reasons.append('v8_veto:'+suite)
    full_rows=[dict(bag=r['bag'],group=r['group'],receivers=r['full']['receivers']) for r in original]
    full_dist={n:group.macro(full_rows,n,'distance') for n in NAMES}
    if any(v is None for v in full_dist.values()):reasons.append('missing_full_distance')
    elif full_dist['H37']>full_dist['R4_v8']*1.01:reasons.append('full_faulted_distance_regression')
    active=[r for r in clean if r['activation']['effective_output_ticks']>0 and any(s['R4_v8']['rmse'] is not None for s in r['receivers'].values())]
    groups=sorted(set(r['group'] for r in active));ticks=sum(r['activation']['effective_output_ticks'] for r in active)
    coverage=ticks>=200 and len(groups)>=3
    if not coverage:reasons.append('insufficient_mechanism_coverage')
    return dict(aggregates=summary,gains=gains,suites=suites,full_original_distance=full_dist,baseline_reproduction=errors,
        activation=dict(effective_reference_ticks=ticks,groups=groups,passed=coverage),rejection_reasons=sorted(set(reasons)),
        scientific_verdict='REJECTED' if reasons and coverage else ('INCONCLUSIVE' if reasons else 'DEVELOPMENT_PASSED_REQUIRES_FREEZE'),
        accuracy_contract_evaluated=True,accuracy_contract_passed=not reasons,coverage_status='SUFFICIENT' if coverage else 'INSUFFICIENT',
        selected=None if reasons else 'H37',validation_opened=False,test_opened=False,enabled_runtime_verified=False,ready_to_merge=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--foundation',type=Path,required=True);p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    foundation=json.loads(a.foundation.read_text());assert foundation['coverage_passed'] and foundation['train_bags']==64
    if not 1<=a.workers<=8:raise ValueError('workers')
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'traces').mkdir();start=pins()
    import reserve_odometry.traction_power as mod
    start.update(candidate_module=mod.__file__,candidate_class='TractionPowerObserver',enabled=True,candidate_sha256=sha(mod.__file__),foundation_sha256=sha(a.foundation))
    save(a.output/'started.json',start);store=Store()
    with ProcessPoolExecutor(a.workers) as pool:raw=list(pool.map(worker,[(b,a.output) for b in store.plan['splits']['development']]))
    clean=[r['clean'] for r in raw];rows=[x for r in raw for x in r['faults']];d=decision(clean,rows)
    d.update(hypothesis_id='R4-H37',baseline_sha=BASELINE,measured_source_sha=os.getenv('H37_MEASURED_SHA'),mechanism_status='ACTIVE' if d['activation']['effective_reference_ticks'] else 'INACTIVE',
        clean_bags=len(clean),fault_cases=dict(collections.Counter(r['suite'] for r in rows)))
    save(a.output/'SUMMARY.json',d);save(a.output/'results.json',dict(clean=clean,faults=rows,summary=d))
    print(json.dumps(d,indent=2),flush=True)
if __name__=='__main__':main()

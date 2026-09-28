"""One fixed-profile AUDIT; no fitting, validation, parameter selection or runtime promotion.

Only the two explicitly named offline interventions use fault boundaries. Primary
main/h36 factories never do. Output collection is not part of a runtime observer.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import datetime
import hashlib
import os
from pathlib import Path
import platform
import time
from common import *

MODE = ('WAITING_FOR_INITIALIZATION','INITIALIZED','MODEL_ONLY','FUSED','SINGLE_WHEEL','REACQUIRING','STOPPED')
STATUS = ('MISSING_OR_STALE','RANGE','DUPLICATE_OR_OLD','RATE_ANOMALY','CANDIDATE','MODEL_DISAGREEMENT','AMBIGUOUS_PAIR','ACCEPTED','REACQUIRE_ACCEPTED','ZERO_LOCK_SUSPECT','COMMON_MODE_QUARANTINE')
COLS = ('t','v','s','inner_v','drive_a','d','pv','readout_v','readout_s','model_a_unclipped',
        'predicted_unclipped','previous_v','previous_d','previous_drive','phase','mode','front_status',
        'rear_status','stop','d_at_limit','a_clipped','v_clipped','command','intervened','front_t','rear_t',
        'variance_v','variance_s')
IDX = {n:i for i,n in enumerate(COLS)}
FAULT_BINS = [('pre5',-5.,0.,'start'),('event0_1',0.,1.,'event'),('event1_2',1.,2.,'event'),
              ('event2_3',2.,3.,'event'),('event3_5',3.,5.,'event'),('event5_10',5.,10.,'event'),
              ('post0_1',0.,1.,'end'),('post1_3',1.,3.,'end'),('post3_10',3.,10.,'end'),
              ('post10_end',10.,None,'end')]


class Capture:
    """Passive recorder, or explicitly labeled non-deployable state intervention."""
    def __init__(self, config, name='main', fault=None):
        self.name, self.fault = name, fault
        self.o=GuardedReadoutObserver(config,readout=profile()[1])
        self.reset()
    @property
    def t(self): return self.o.t
    @property
    def c(self): return self.o.c
    def reset(self, **kw):
        self.o.reset(**kw); self.rows=[]; self.started=False; self.held_d=None
        self.hold_allowed=True; self.switch_t=None; self.prefix=hashlib.sha256()
        self.pre_switch=None; self.hold_ticks=0
    def step(self,t,command=None,front=None,rear=None):
        o=self.o; old_t=o.t
        if self.name in ('coherent','hold_d') and not self.started and t>=self.fault['start']:
            self.pre_switch=dict(t=t,previous_output_t=old_t,v=o.v,drive_a=o.drive_a,d=o.disturbance,
                                 s=o.s,pv=o.pv,readout_v=o._velocity_correction,readout_s=o._distance_correction)
            self.held_d=o.disturbance; self.started=True; self.switch_t=t
            o.c=profile(HERE/'profiled.yaml')[0]
        holding=(self.name=='hold_d' and self.started and t<self.fault['end'] and self.hold_allowed)
        if holding: o.disturbance=self.held_d; self.hold_ticks+=1
        old_v,old_d,old_drive=o.v,o.disturbance,o.drive_a
        e=o.step(t,command,front,rear)
        if holding:
            if e.mode=='STOPPED': self.hold_allowed=False
            else:
                o.disturbance=self.held_d
                e=replace(e,disturbance=self.held_d);o.last_estimate=e
        if self.fault and t<self.fault['start']:
            self.prefix.update(repr(vars(o)).encode())
        if e.mode=='WAITING_FOR_INITIALIZATION': return e
        u=math.nan if e.command_stale else command.value
        phase=2 if e.command_stale else 1 if u>.04 else -1 if u<-.04 else 0
        model_a=o.drive_a-o.resistance(old_v)+old_d
        dt=0. if old_t is None else t-old_t
        pred=old_v+dt*clip(model_a,-o.c.max_accel_mps2,o.c.max_accel_mps2)
        self.rows.append((t,e.v,e.s,o.v,o.drive_a,e.disturbance,o.pv,o._velocity_correction,o._distance_correction,
            model_a,pred,old_v,old_d,old_drive,phase,MODE.index(e.mode),STATUS.index(e.front_status),STATUS.index(e.rear_status),
            int(e.mode=='STOPPED'),int(abs(e.disturbance)>=o.c.disturbance_limit_mps2-1e-12),
            int(abs(model_a)>o.c.max_accel_mps2),int(abs(pred)>o.c.max_speed_mps),u,int(self.started),
            math.nan if front is None else front.t,math.nan if rear is None else rear.t,e.variance_v,e.variance_s))
        return e
    def array(self): return np.asarray(self.rows,float).reshape(-1,len(COLS))


def inject(events, fault):
    a=events.copy(); mask=(a[:,0]>=fault['start'])&(a[:,0]<fault['end'])
    if fault['kind']=='dropout': return a[~(mask&(a[:,1]!=0))]
    if fault['kind']=='lock': a[mask&(a[:,1]!=0),2]=0.
    elif fault['kind']=='bias': a[mask&(a[:,1]==1),2]+=5.
    else: raise ValueError('Unsupported original fault')
    return a


def signed_integral(t, error, start, end):
    """Exact piecewise-linear integral on valid edges; no fabricated reference gaps."""
    if len(t)<2: return dict(integral_on_covered_edges_m=None,full_integral_m=None,covered_s=0.,requested_s=max(0.,end-start),edge_count=0)
    left=np.maximum(t[:-1],start);right=np.minimum(t[1:],end);dt=np.diff(t)
    good=(right>left)&(dt>0)&(dt<.051)&np.isfinite(error[:-1])&np.isfinite(error[1:])
    if not good.any(): val=0.;covered=0.
    else:
        slopes=(error[1:][good]-error[:-1][good])/dt[good]
        ea=error[:-1][good]+slopes*(left[good]-t[:-1][good])
        eb=error[:-1][good]+slopes*(right[good]-t[:-1][good])
        val=float(np.sum((ea+eb)*.5*(right[good]-left[good])))
        covered=float(np.sum(right[good]-left[good]))
    requested=max(0.,end-start);complete=abs(covered-requested)<=1e-7 and requested>0
    return dict(integral_on_covered_edges_m=val if covered else None,full_integral_m=val if complete else None,
                covered_s=covered,requested_s=requested,edge_count=int(good.sum()),complete=complete)


def clean_json(v):
    if isinstance(v,dict):return {str(k):clean_json(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean_json(x) for x in v]
    if isinstance(v,np.generic):return clean_json(v.item())
    if isinstance(v,float) and not math.isfinite(v):return None
    return v


def diag_scores(t,a,target,mask):
    m=ev.ex.metrics(t,a[:,IDX['v']],target,mask)
    m.update(model_a_clipped=int(np.sum(mask&(a[:,IDX['a_clipped']]>0))),
             speed_clipped=int(np.sum(mask&(a[:,IDX['v_clipped']]>0))),
             disturbance_at_limit=int(np.sum(mask&(a[:,IDX['d_at_limit']]>0))),
             modes={label:int(np.sum(mask&(a[:,IDX['mode']]==i))) for i,label in enumerate(MODE)})
    return m


def diagnose(arrays, refs, fault, context):
    base=arrays['main'];t=base[:,0];targets={k:ev.ex.match(v,t) for k,v in refs.items()}
    result=dict(slices=[],integrals=[],landmarks=[],state={},reference={})
    both=np.isfinite(targets['master'])&np.isfinite(targets['rover'])
    gap=abs(targets['master']-targets['rover'])
    reference_masks={'agreement':both&(gap<=.5),'disagreement':both&(gap>.5),
                     'zero_versus_moving':both&(np.minimum(targets['master'],targets['rover'])<=1e-9)&(np.maximum(targets['master'],targets['rover'])>2.)}
    masks={}
    # Masks below are fixed across models and partitioned within each family.
    for label,code in [('traction',1),('braking',-1),('coast',0),('stale',2)]:
        masks['command:'+label]=base[:,IDX['phase']]==code
    edges=[0,.07,.5,2,5,10,math.inf]
    for lo,hi in zip(edges,edges[1:]):masks[f'speed:{lo}_{hi}']=(abs(base[:,1])>=lo)&(abs(base[:,1])<hi)
    if fault:
        for label,lo,hi,anchor in FAULT_BINS:
            origin=fault['start'] if anchor!='end' else fault['end']
            upper=t[-1]+1e-9 if hi is None else origin+hi
            mask=(t>=origin+lo)&(t<upper)
            if anchor=='event': mask &= t<fault['end']
            masks['time:'+label]=mask
    main_scope=np.ones(len(t),bool) if fault is None or context=='full' else (t>=fault['start'])&(t<fault['end']+10)
    for recv,target in targets.items():
        valid=np.isfinite(target)
        rm=dict(reference_masks,peer_missing=valid&~both)
        for label,mask in rm.items():
            m=mask&valid&main_scope
            result['reference'][recv+':'+label]=int(m.sum())
            row=dict(receiver=recv,family='reference',bin=label,scores={n:diag_scores(t,a,target,m) for n,a in arrays.items()})
            result['slices'].append(row)
        # Main mask unchanged. The union of command bins exactly covers the chosen scope.
        for key,mask in masks.items():
            family,label=key.split(':',1)
            # Fault-relative pre/post bins include their named interval, not primary event crop.
            m=mask&valid&(True if family=='time' else main_scope)
            result['slices'].append(dict(receiver=recv,family=family,bin=label,scores={n:diag_scores(t,a,target,m) for n,a in arrays.items()}))
        intervals=[('full_available',t[0],t[-1])] if fault is None else [
            ('event',fault['start'],min(fault['end'],t[-1])),
            ('event_plus10',fault['start'],min(fault['end']+10,t[-1])),
            ('event_to_end',fault['start'],t[-1])]
        for label,lo,hi in intervals:
            for n,a in arrays.items():result['integrals'].append(dict(receiver=recv,model=n,interval=label,start=lo,end=hi,
                      **signed_integral(t,a[:,1]-target,lo,hi)))
    max_error=0.
    for n,a in arrays.items():
        ds=a[:,2]-base[:,2];delta_v=a[:,1]-base[:,1]
        predicted=ds[0]+np.r_[0,np.cumsum(.5*(delta_v[1:]+delta_v[:-1])*np.diff(t))]
        err=float(np.max(abs(ds-predicted)));max_error=max(max_error,err)
        if err>1e-8:raise AssertionError(('distance identity',context,n,err))
        pre_idx=max(0,int(np.searchsorted(t,fault['start'],side='left')-1)) if fault else 0
        result['state'][n]={COLS[k]:clean_json(x) for k,x in enumerate(a[pre_idx])}
        times=[('end_bag',t[-1])] if not fault else [('event_end',fault['end']),('post10',fault['end']+10),('end_bag',t[-1])]
        for label,query in times:
            j=min(len(t)-1,max(0,int(np.searchsorted(t,query,side='right')-1)))
            result['landmarks'].append(dict(model=n,label=label,requested_t=query,t=float(t[j]),
                delta_s_vs_v8_m=float(ds[j]),incremental_delta_s_vs_v8_m=float(ds[j]-ds[pre_idx]),
                delta_v_vs_v8_mps=float(delta_v[j]),sample_covers_query=bool(t[0]<=query<=t[-1]+1e-9)))
    result['integral_identity_max_abs_error_m']=max_error
    return result,targets


def scored(events,refs,fault,context):
    captures={};base,read=profile();alt,_=profile(HERE/'profiled.yaml')
    names=['main','h36']+(['coherent','hold_d'] if fault else [])
    model_set={}
    for n in names:
        def factory(c,n=n):
            obj=Capture(c,n,fault);captures[n]=obj;return obj
        model_set[n]=(factory,alt if n=='h36' else base)
    scoring_fault=fault if context=='crop' else None
    result=gc.compare(events,refs,model_set,scoring_fault)
    arrays={n:o.array() for n,o in captures.items()}
    checks=dict(schedule=True,passive_direct=False,prefault_shared_state=False)
    for n,a in arrays.items():
        if not np.array_equal(a[:,0],arrays['main'][:,0]):raise AssertionError('Trace schedule mismatch')
        if result['runtime'][n]['causal_errors'] or result['runtime'][n]['resets']:raise AssertionError('Causality/reset failure')
        for scores in result['receivers'].values():
            if scores[n]['n']!=scores['main']['n'] or scores[n]['coverage']!=scores['main']['coverage']:raise AssertionError('Reference coverage mismatch')
    if context=='clean':
        for n in names:
            a,counters=gc.predict(events,(lambda c:GuardedReadoutObserver(c,readout=read),model_set[n][1]))
            if not np.array_equal(a[:,:3],arrays[n][:,:3]) or counters!=result['runtime'][n]:raise AssertionError('Passive capture differs')
        checks['passive_direct']=True
    if fault:
        expected=captures['main'].prefix.digest()
        for n in ('coherent','hold_d'):
            if captures[n].prefix.digest()!=expected:raise AssertionError('Ablation prefault state not equal')
        checks['prefault_shared_state']=True
    result['checks']=checks
    result['interventions']={n:dict(switch_t=o.switch_t,pre_switch=o.pre_switch,hold_ticks=o.hold_ticks) for n,o in captures.items()}
    diag,targets=diagnose(arrays,refs,fault,context)
    return result,arrays,diag,targets


def run_bag(args):
    bag,data_root,out=args;out=Path(out);store=DevelopmentStore(Path(data_root))
    events,refs=store.load(bag,'development');meta=dict(bag=bag,group=store.records[bag]['group'],role='development')
    rows=[];dest=out/'bags';dest.mkdir(exist_ok=True)
    def add(context,es,f=None,index='clean'):
        result,arrays,diag,targets=scored(es,refs,f,context)
        ident=bag+'-'+context+'-'+str(index)
        row=dict(**meta,case_id=ident,context=context,fault=f,**result,diagnostics=diag)
        # Complete main/H36 trajectories; all intervention trajectories retained too.
        p=out/'traces'/(ident+'.npz');p.parent.mkdir(exist_ok=True)
        np.savez_compressed(p,**arrays,ref_master=targets['master'],ref_rover=targets['rover'])
        row['trace_path']=str(p.relative_to(out));rows.append(row)
    add('clean',events)
    for i,(f,window) in enumerate(gc.fault_windows(events)):
        add('crop',window,f,i);add('full',inject(events,f),f,i)
    save(dest/(bag+'.json'),clean_json(rows));save(out/'access'/(bag+'.json'),store.access)
    print('COMPLETED_BAG',bag,'cases',len(rows),flush=True)
    return dict(bag=bag,cases=len(rows),json=str(dest/(bag+'.json')))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    p.add_argument('--source-sha',required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    identities=integrity();store=DevelopmentStore(args.data_root)
    files={str(f.relative_to(ROOT)):sha(f) for f in HERE.iterdir() if f.is_file()}
    started=dict(hypothesis_id='R5-H43',kind='AUDIT',source_sha=args.source_sha,plan_commit=PLAN_COMMIT,
                 baseline=BASE,tree=TREE,h36_source=H36,execution_backend='LOCAL',
                 started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 identities=identities,source_hashes=files,python=platform.python_version(),numpy=np.__version__,
                 observer_module=__import__('reserve_odometry.guarded_readout',fromlist=['x']).__file__,
                 development_bags=store.plan['splits']['development'],validation_opened=False,test_opened=False,
                 new_optimizer_calls=0,columns=COLS,mode=MODE,status=STATUS)
    save(args.output/'started.json',started);start=time.perf_counter()
    jobs=[(bag,str(args.data_root),str(args.output)) for bag in store.plan['splits']['development']]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        completed=list(pool.map(run_bag,jobs))
    clean=[];stress=[];full=[]
    for b in completed:
        for r in json.loads(Path(b['json']).read_text()):
            {'clean':clean,'crop':stress,'full':full}[r['context']].append(r)
    summary={n:v6.summary(clean,stress,n) for n in ('main','h36')}
    expected=dict(clean_rmse=.09266814298282507,fault_rmse=.2375486120563008,
                  pooled_rmse=.1293056944774334,distance_rmse=5.310295004801444,samples=394221)
    for k,value in expected.items():
        if summary['main'][k]!=value:raise AssertionError(('Baseline fingerprint',k,summary['main'][k],value))
    assert len(clean)==17 and len(stress)==56 and len(full)==56
    for rel,expected_hash in files.items():
        if sha(ROOT/rel)!=expected_hash:raise AssertionError('Diagnostic source changed during execution')
    integrity()
    evidence=dict(**started,elapsed_s=time.perf_counter()-start,completed=completed,summary=summary,
                  counts=dict(clean=len(clean),crop=len(stress),full=len(full)),baseline_reproduction=expected,
                  scientific_verdict='AUDIT_MEASUREMENTS_COMPLETE',runtime_candidate_implemented=False,
                  ablation_summary={n:v6.summary([],stress,n) for n in ('coherent','hold_d')},
                  full_distance={n:v6.macro(full,n,'distance') for n in ('main','h36','coherent','hold_d')},
                  integral_identity_max_abs_error_m=max(r['diagnostics']['integral_identity_max_abs_error_m'] for r in clean+stress+full))
    save(args.output/'MEASUREMENT_SUMMARY.json',clean_json(evidence))
    print(json.dumps(evidence['summary'],indent=2),flush=True)

if __name__=='__main__':main()

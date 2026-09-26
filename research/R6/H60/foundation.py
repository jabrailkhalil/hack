"""H60 train-fit foundation. Frozen FD2 anchors, canonical arrival schedule.

The prefix checkpoint is an OFFLINE acceleration, never runtime data. The full
suffix is replayed until an exact velocity-state rejoin is verified, or EOF.
"""
import os,sys,math,time,copy,json,argparse,zipfile
from pathlib import Path
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
FD1=ROOT/'Odometry_Failure_Discovery_v1';WORK=FD1/'.work'
sys.path[:0]=[str(FD1),str(ROOT/'fd2/code')]
from failure_discovery.common import sha,write_json,write_csv,save_npz,pool_map,digest_obj
from failure_discovery.data import selected_bags,load_vehicle,teacher_at
from failure_discovery.baseline import api,replay,command_mode,MODES
from failure_discovery.faults import stream_fault
_,Sample,Observer,_,Timeline,_,cfg,readout=api(str(WORK))
from instrument import InstrumentedObserver,COLUMNS,dynamical_state
from real import schedule

PHASES=(0.,.25,.5,1.,2.,5.,10.)

def state_key(o,tl):
    return (dynamical_state(o),tuple(tl.held),tuple(tuple(q) for q in tl.queues),
            tl.latest,tl.next_tick,tl.grid_origin,tl.tick_index,tl._catchup_active)

def clean_instrument(events,sch):
    o=InstrumentedObserver(cfg,readout=readout);tl=Timeline(o,20,0)
    # Earliest arrival at or beyond boundary is conservative under reordering.
    starts=sorted({f['start'] for f,_,_,_ in sch})
    idxs={s:next((i for i,x in enumerate(events) if x[0]>=s),len(events)) for s in starts}
    wanted=set(idxs.values());snap={};rows=[];feats=[];diags=[];modes=[];keys=[]
    last_mode=None;last_trans=0.
    for i,(t,ch,val) in enumerate(events):
        if i in wanted:snap[i]=(copy.deepcopy(tl),len(rows),last_mode,last_trans)
        tl.ingest(int(ch),Sample(float(t),float(val)))
        for e,held in tl.advance():
            if e.mode=='WAITING_FOR_INITIALIZATION':continue
            vals=[x.value if x is not None else math.nan for x in held]
            ages=[e.t-x.t if x is not None else math.nan for x in held]
            cm=command_mode(vals[0])
            if cm!=last_mode:last_mode=cm;last_trans=e.t
            sk=abs(held[1].t-held[2].t) if held[1] and held[2] else math.nan
            wheels=[x.value if x is not None and 0<=e.t-x.t<=cfg.max_age_s else math.nan for x in held[1:]]
            rows.append((e.t,e.v,e.s,wheels[0],sum(wheels)/2,float(e.mode=='STOPPED')))
            feats.append([*vals,*ages,sk,o.v,o.drive_a,o.disturbance,o.pv,
                          o.drive_a-o.resistance(o.v)+o.disturbance,e.t-last_trans,e.v-o.v])
            diags.append(o.diag.copy());modes.append(MODES.index(e.mode));keys.append(state_key(o,tl))
    return {'output':np.asarray(rows,float).reshape(-1,6),'features':np.asarray(feats,float).reshape(-1,14),
            'diag':np.asarray(diags,float).reshape(-1,len(COLUMNS)),'modes':np.asarray(modes,np.int8),
            'snapshots':snap,'indices':idxs,'keys':keys,
            'runtime':{'resets':tl.resets,'dropped':tl.dropped,'catchups':tl.catchup_events}}

def suffix(events,clean,fault,full=False):
    idx=clean['indices'][fault['start']]
    tl,offset,lm,lt=copy.deepcopy(clean['snapshots'][idx])
    a=clean['output'];o=tl.observer;out=[];diag=[];mode=[]
    # Prior values are irrelevant for FD2 dropout/bias/drift/lock families.
    if fault['kind'] not in ('dropout','bias','drift','lock','natural'):raise ValueError('unregistered family')
    joined=False;join_tick=None;first_trust=None
    f=None if fault['kind']=='natural' else fault
    for t,ch,val in stream_fault(events[idx:],f):
        tl.ingest(int(ch),Sample(float(t),float(val)))
        for e,held in tl.advance():
            if e.mode=='WAITING_FOR_INITIALIZATION':continue
            j=offset+len(out)
            if j>=len(a) or e.t!=a[j,0]:raise AssertionError('output grid mismatch')
            if any(x is not None and x.t>e.t+1e-9 for x in held):raise AssertionError('future observation')
            wheels=[x.value if x is not None and 0<=e.t-x.t<=cfg.max_age_s else math.nan for x in held[1:]]
            out.append((e.t,e.v,e.s,wheels[0],sum(wheels)/2,float(e.mode=='STOPPED')))
            diag.append(o.diag.copy());mode.append(MODES.index(e.mode))
            if e.t>=fault['end'] and first_trust is None and o.diag[10] and o.diag[12]:first_trust=e.t
            # No estimated tolerance rejoin: every velocity-driving field exact.
            after=max(fault['end']+15.,(first_trust+10. if first_trust is not None else fault['end']+15.))
            if not full and e.t>=after and state_key(o,tl)==clean['keys'][j]:
                joined=True;join_tick=j;break
        if joined:break
    b=np.asarray(out,float).reshape(-1,6);g=np.asarray(diag,float).reshape(-1,len(COLUMNS))
    delta=b[:,1]-a[offset:offset+len(b),1]
    ds=b[:,2]-a[offset:offset+len(b),2]
    # Include the last identical prefix tick for the initial trapezoid.
    tt=np.r_[a[offset-1,0],b[:,0]] if offset else b[:,0]
    vv=np.r_[0.,delta] if offset else delta
    ss=np.r_[0.,ds] if offset else ds
    integ=np.r_[0.,np.cumsum(.5*(vv[:-1]+vv[1:])*np.diff(tt))]
    defect=float(np.max(np.abs(ss-ss[0]-integ))) if len(ss) else 0.
    if defect>1e-6:raise AssertionError(f'integral defect {defect}')
    return {'output':b,'diag':g,'modes':np.asarray(mode,np.int8),'offset':offset,
            'joined':joined,'join_tick':join_tick,'terminal_delta_s':float(ds[-1]) if len(ds) else None,
            'integral_defect':defect,'future_errors':0,'resets':tl.resets}

def at(t,v,q):
    if not len(t) or q<t[0]-1e-8 or q>t[-1]+1e-8:return math.nan
    return float(np.interp(q,t,v))

def episode(clean,res,fault,meta,ref):
    a=clean['output'];b=res['output'];g=res['diag'];off=res['offset'];end=fault['end'];t=b[:,0]
    ds=b[:,2]-a[off:off+len(b),2];dv=b[:,1]-a[off:off+len(b),1]
    out=dict(meta,**fault,integral_defect=res['integral_defect'],joined=res['joined'],
             terminal_delta_s=res['terminal_delta_s'],natural=fault['kind']=='natural')
    new=(t>=end-1e-9)
    ai=np.flatnonzero(new&(g[:,11]>0));ti=np.flatnonzero(new&(g[:,10]>0)&(g[:,12]>0));fi=np.flatnonzero(t<end)
    marks={'last_fault':int(fi[-1]) if len(fi) else None,'first_accepted':int(ai[0]) if len(ai) else None,
           'first_trusted':int(ti[0]) if len(ti) else None}
    for label,i in marks.items():
        out[label+'_t']=float(t[i]) if i is not None else None
        if i is not None:
            for k,v in zip(COLUMNS,g[i]):out[label+'_'+k]=float(v)
            out[label+'_published_v']=float(b[i,1]);out[label+'_published_s']=float(b[i,2])
    out['recovery_delay_accepted_s']=out['first_accepted_t']-end if len(ai) else None
    out['recovery_delay_trusted_s']=out['first_trusted_t']-end if len(ti) else None
    phases=[]
    for anchor,origin in [('fault_end',end),('trusted',out['first_trusted_t'])]:
        if origin is None:continue
        for l,r in zip(PHASES[:-1],PHASES[1:]):
            d0=at(t,ds,origin+l);d1=at(t,ds,origin+r)
            # Once rejoined, future velocity differences are exactly zero.
            if res['joined']:
                if origin+l>t[-1] and origin+l<=a[-1,0]+1e-9:d0=float(ds[-1])
                if origin+r>t[-1] and origin+r<=a[-1,0]+1e-9:d1=float(ds[-1])
            phases.append(dict(meta,anchor=anchor,phase_start=l,phase_end=r,
                               origin_t=origin,covered=bool(np.isfinite(d0) and np.isfinite(d1)),
                               delta_s_increment=d1-d0,delta_s_begin=d0,delta_s_end=d1))
        total=[x for x in phases if x['anchor']==anchor]
        out[anchor+'_remaining_integral_10s']=sum(x['delta_s_increment'] for x in total) if len(total)==6 and all(x['covered'] for x in total) else None
    fmask=(t>=fault['start'])&(t<end);rr=ref[off:off+len(b)]
    fvalid=fmask&np.isfinite(rr)
    out['fault_proxy_n']=int(fvalid.sum());out['fault_ticks']=int(fmask.sum())
    out['fault_proxy_rmse']=float(np.sqrt(np.mean((np.abs(b[fvalid,1])-rr[fvalid])**2))) if fvalid.any() else None
    out['fault_counterfactual_rmse']=float(np.sqrt(np.mean(dv[fmask]**2))) if fmask.any() else None
    out['fault_delta_s']=at(t,ds,end)-at(t,ds,fault['start'])
    out['terminal_is_exact_rejoin_or_full_replay']=True
    # No teacher is read by the observer; signed counterfactual is not truth.
    mask=(t>=fault['start']-1)&(t<=min(a[-1,0],max(end+10.,(out['first_trusted_t'] or end)+10.)))
    trace={'output':b[mask],'clean_output':a[off:off+len(b)][mask],
           'diag':g[mask],'modes':res['modes'][mask],'teacher':rr[mask]}
    return out,phases,trace

def bag_job(job):
    row,root,verify=job;root=Path(root);bag=row['bag'];out=root/'bags'/bag;out.mkdir(parents=True,exist_ok=True)
    begin=time.perf_counter();events,j=load_vehicle(WORK,bag,out/'ACCESS.json')
    canon=replay(events,str(WORK));sch=schedule(canon,bag);clean=clean_instrument(events,sch)
    for key in ('output','features','modes'):
        if not np.array_equal(canon[key],clean[key],equal_nan=True):raise AssertionError('instrumentation changes '+key)
    for key in ('resets','dropped','catchups'):
        if canon['runtime'][key]!=clean['runtime'][key]:raise AssertionError('runtime counter mismatch')
    a=clean['output'];ref=teacher_at(WORK,bag,a[:,0]) if len(a) else np.zeros(0)
    save_npz(out/'CLEAN.npz',output=a,features=clean['features'],diag=clean['diag'],modes=clean['modes'],teacher=ref)
    results=[];phases=[];checks=[];verified=set()
    for n,(fault,cid,source,_) in enumerate(sch):
        r=suffix(events,clean,fault)
        # Original full FD1 replay, not our full flag, is the independent oracle.
        vk='dropout10' if fault['kind']=='dropout' and fault['target']=='both' and fault['end']-fault['start']==10 else ('bias' if fault['kind']=='bias' else None)
        if verify and vk and vk not in verified:
            full=replay(events,str(WORK),fault)['output'];b=r['output'];off=r['offset'];stop=off+len(b)
            if not np.array_equal(full[off:stop],b,equal_nan=True):raise AssertionError('prefix replay not exact')
            if not np.array_equal(full[:off],a[:off],equal_nan=True):raise AssertionError('prefault not identical')
            if r['joined'] and not np.array_equal(full[stop:,1],a[stop:,1]):raise AssertionError('rejoin velocity mismatch')
            terminal_defect=abs((full[-1,2]-a[-1,2])-r['terminal_delta_s'])
            if terminal_defect>1e-6:raise AssertionError('rejoin terminal error')
            checks.append({'family':vk,'event_id':cid,'full_ticks':len(full),'replayed_suffix_ticks':len(b),
                           'all_computed_outputs_exact':True,'rejoined_velocity_exact':True,'terminal_defect':terminal_defect})
            verified.add(vk)
        meta={'event_id':cid,'bag':bag,'group':row['group'],'label':row.get('vehicle_manifest_label',row.get('label')),
              'fold':'fit','source':source,'anchor_id':digest_obj({'bag':bag,'start':fault['start']})[:20],
              'command_mode':command_mode(clean['features'][np.searchsorted(a[:,0],fault['start']),0])}
        m,p,tr=episode(clean,r,fault,meta,ref);results.append(m);phases.extend(p)
        save_npz(out/'traces'/(cid+'.npz'),**tr)
    write_json(out/'EPISODES.json',results);write_csv(out/'PHASES.csv',phases)
    summary={'bag':bag,'group':row['group'],'label':row.get('vehicle_manifest_label'),
             'events':len(results),'ticks':len(a),'instrumentation_exact':True,'replay_checks':checks,
             'runtime':canon['runtime'],'wall_s':time.perf_counter()-begin,
             'status':'COMPLETE' if len(a) else 'NO_INITIALIZED_OUTPUT'}
    write_json(out/'SUMMARY.json',summary)
    return summary

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--limit',type=int,default=0);args=ap.parse_args()
    lock=json.loads((ROOT/'research/DEPENDENCIES.lock').read_text());assert lock['combined_verified']
    rows=lock['selected_fit'];rows=rows[:args.limit] if args.limit else rows
    verifybags=[r['bag'] for r in rows if next(x for x in lock['fit_database_preflight']['extracted'] if x['bag']==r['bag'])][:3]
    args.output.mkdir(parents=True,exist_ok=True)
    manifest={'plan_commit':lock['plan_commit'],'lock_sha256':sha(ROOT/'research/DEPENDENCIES.lock'),
              'source_hashes':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
              'rows':rows,'started_unix':time.time(),'workers':args.workers,'candidate':False,'verification_bags':verifybags}
    mp=args.output/'RUN.json'
    if mp.exists():raise FileExistsError('choose a fresh execution directory')
    write_json(mp,manifest)
    summaries=[]
    for s in pool_map(bag_job,[(r,str(args.output),r['bag'] in verifybags) for r in rows],args.workers):
        summaries.append(s);print(len(summaries),'/',len(rows),s['bag'],s['events'],round(s['wall_s'],2),flush=True)
    write_json(args.output/'SUMMARY.json',{'bags':summaries,'candidate':False,'complete':True})

if __name__=='__main__':main()

"""One H32 candidate, genuine development, immutable scorer and strict gates.

No validation/test CLI or hidden evaluation. A positive decision would require
another published freeze before any separately authorized validation loader.
"""
import argparse, collections, csv, hashlib, importlib.util, json, math, os
from pathlib import Path
import resource, sys, time
from concurrent.futures import ProcessPoolExecutor
from support import *
from factory import candidate, CommandEventObserver, CommandEventTimeline, PATCHED_CORE, HOOK_PATCH

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
legacy=load_module('h32_guarded_metrics',ROOT/'tools/research_guarded/compare.py')
v6=load_module('h32_v6_metrics',ROOT/'tools/research_v6/compare.py')
h11=load_module('h32_h11_suite',ROOT/'tools/research_h11/compare.py')
NAMES=('main','candidate')

class CheckedOff(CommandEventObserver):
    def __init__(self,config):
        self.reference=baseline(config)
        super().__init__(config,readout=ReadoutConfig(gain=1.,holdoff_s=.5),enabled=False)
    def reset(self,**kw):
        super().reset(**kw);self.reference.reset(**kw);self.checked=0
    def step(self,*args,**kw):
        a=super().step(*args,**kw);b=self.reference.step(*args,**kw)
        if a!=b:raise AssertionError('Feature-off Estimate mismatch')
        for k,v in vars(self.reference).items():
            if getattr(self,k)!=v:raise AssertionError('Feature-off state: '+k)
        self.checked+=1;return a


def paired(events,refs,fault=None):
    configurations={n:profile()[0] for n in ('baseline_v2','balanced_physics','feature_off')}
    models={'baseline_v2':baseline(configurations['baseline_v2']),
            'balanced_physics':candidate(configurations['balanced_physics']),
            'feature_off':CheckedOff(configurations['feature_off'])}
    by_config={id(configurations[n]):models[n] for n in models}
    arrays={};old_observer,old_timeline,old_replay=ev.Observer,ev.Timeline,ev.replay
    def timeline(o,**kw):
        return (CommandEventTimeline if isinstance(o,CommandEventObserver) else Timeline)(o,**kw)
    def collect(e,c,ops,f=None):
        a,info=old_replay(e,c,ops,f);arrays[id(c)]=(a,info);return a,info
    try:
        ev.Observer=lambda c:by_config[id(c)];ev.Timeline=timeline;ev.replay=collect
        row=ev.score(events,refs,configurations,OPS,fault)
    finally:
        ev.Observer,ev.Timeline,ev.replay=old_observer,old_timeline,old_replay
    b,br=arrays[id(configurations['baseline_v2'])]
    c,cr=arrays[id(configurations['balanced_physics'])]
    off,offr=arrays[id(configurations['feature_off'])]
    if not np.array_equal(b,off,equal_nan=True) or br!=offr:
        raise AssertionError('Feature-off arrays/counters differ')
    if b.shape!=c.shape or not np.array_equal(b[:,0],c[:,0]):
        raise AssertionError('Schedule mismatch')
    if any(x['causal_errors'] or x['resets'] for x in (br,cr,offr)):
        raise AssertionError('Causality/reset failure')
    for old,new in [('baseline_v2','main'),('balanced_physics','candidate')]:
        row['runtime'][new]=row['runtime'].pop(old)
        for scores in row['receivers'].values():scores[new]=scores.pop(old)
    mask_hash={}
    for receiver,values in refs.items():
        target=ev.ex.match(values,b[:,0]);mask=np.isfinite(target)
        if fault:mask&=(b[:,0]>=fault['start'])&(b[:,0]<fault['end']+10.)
        mask_hash[receiver]=hashlib.sha256(mask.tobytes()).hexdigest()
    ob=models['balanced_physics']
    row['audit']=dict(feature_off_exact=True,checked_ticks=models['feature_off'].checked,
        changed_outputs=int(np.sum(abs(c[:,1]-b[:,1])>1e-9)),
        max_velocity_delta_mps=float(np.max(abs(c[:,1]-b[:,1]))) if len(b) else None,
        schedule_sha256=hashlib.sha256(b[:,0].tobytes()).hexdigest(),mask_sha256=mask_hash,
        baseline_array_sha256=hashlib.sha256(b.tobytes()).hexdigest(),
        candidate_array_sha256=hashlib.sha256(c.tobytes()).hexdigest())
    row['activation']=dict(ob.h32_counts);row['max_commands']=ob.h32_max_commands
    return row,dict(main=b,candidate=c)


def low_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=np.flatnonzero(valid&(abs(f-r)<.15)&((f+r)/2>1)&((f+r)/2<2)&(u>=0)
                      &(t>max(25,.1*t[-1]))&(t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            f=dict(kind='lock',start=anchor,end=anchor+duration)
            yield f,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


def transitions(events):
    changes=[];prev=None;begin=float(events[:,0].min());end=float(events[:,0].max())
    for t,ch,v in events:
        if ch!=0:continue
        if prev is not None and abs(v-prev)>=.1 and begin+20<t<end-20:
            changes.append(float(t))
        prev=v
    return changes


def diagnostics(events):
    last=-math.inf;count=0
    for transition in transitions(events):
        if transition-last<10:continue
        last=transition;count+=1;start=transition+.05
        f=dict(kind='dropout',start=start,end=start+1.)
        yield f,events[(events[:,0]>=start-20)&(events[:,0]<=start+11.1)]
        if count>=3:break


def canonical_check(events,refs,row):
    # Same pinned canonical driver but no H32 Timeline/hook. No copied metrics.
    c=profile()[0];model=(baseline,c)
    independent=legacy.compare(events,refs,dict(main=model,candidate=model))
    if independent['runtime']['main']!=row['runtime']['main']:
        raise AssertionError('Canonical driver counter mismatch')
    count=0
    for receiver,scores in independent['receivers'].items():
        for key,value in scores['main'].items():
            if row['receivers'][receiver]['main'][key]!=value:
                raise AssertionError(('Canonical score mismatch',receiver,key))
            count+=1
    return count


def worker(arg):
    bag,output=arg;store=Store(output/'access'/(bag+'.json'))
    events,refs=store.load(bag,'development');group=store.records[bag]['group']
    meta=dict(bag=bag,group=group,role='development')
    clean,arrays=paired(events,refs);clean.update(meta)
    clean['audit']['canonical_driver_fields']=canonical_check(events,refs,clean)
    trace_dir=output/'arrays';trace_dir.mkdir(exist_ok=True)
    np.savez_compressed(trace_dir/(bag+'-clean.npz'),**arrays)
    phase={};t=arrays['main'][:,0];pmask=np.zeros(len(t),bool)
    for tc in transitions(events):pmask|=(t>=tc)&(t<=tc+2.)
    for receiver,values in refs.items():
        target=ev.ex.match(values,t)
        phase[receiver]={n:ev.ex.metrics(t,a[:,1],target,pmask) for n,a in arrays.items()}
    result=dict(clean=clean,original=[],low_speed=[],common_mode=[],diagnostic=[],full_faulted=[],phase=phase)
    for suite,windows in [('original',legacy.fault_windows(events)),('low_speed',low_windows(events)),
                          ('common_mode',h11.common_fault_windows(events)),('diagnostic',diagnostics(events))]:
        for index,(fault,window) in enumerate(windows):
            window=h11.inject_common(window,fault) if suite=='common_mode' else window
            row,arr=paired(window,refs,fault);row.update(meta,fault=fault)
            result[suite].append(row)
            np.savez_compressed(trace_dir/(bag+'-'+suite+'-'+str(index)+'.npz'),**arr)
            if suite=='original':
                full,fa=paired(events,refs,fault);full.update(meta,fault=fault)
                full['distance_full']={}
                for receiver,values in refs.items():
                    target=ev.ex.match(values,fa['main'][:,0])
                    for n,a in fa.items():
                        m=full['receivers'][receiver][n]
                        m['distance_surrogate']=ev.distance_surrogate(a,target)
                        m['full_false_stops']=int(np.sum(np.isfinite(target)&(target>1)&(a[:,5]>0)))
                t=fa['main'][:,0];delta=fa['candidate'][:,2]-fa['main'][:,2]
                j=int(np.searchsorted(t,fault['end']+10.))
                full['residual_delta_s_m']=dict(
                    at_end_plus_10=float(delta[j]) if j<len(t) else None,
                    terminal=float(delta[-1]) if len(t) else None)
                result['full_faulted'].append(full)
                np.savez_compressed(trace_dir/(bag+'-full-'+str(index)+'.npz'),**fa)
    save(output/'bags'/(bag+'.json'),result)
    print('DEVELOPMENT',bag,'changed',clean['audit']['changed_outputs'],flush=True)
    return result


def supplemental(rows):
    return {n:dict(event_rmse=v6.macro(rows,n,'event_rmse'),window_rmse=v6.macro(rows,n,'rmse'),
                   false_stops=v6.total(rows,n,'false_stop_samples'),unrecovered=v6.unrecovered(rows,n)) for n in NAMES}


def decide(rows):
    clean=[r['clean'] for r in rows]
    suites={s:[x for r in rows for x in r[s]] for s in
            ('original','low_speed','common_mode','diagnostic','full_faulted')}
    summary=legacy.aggregate(clean,suites['original']);b,c=summary['main'],summary['candidate']
    reasons=[];violations=[]
    gain=1-c['macro_rmse']/b['macro_rmse'];fault_gain=1-c['fault_macro']/b['fault_macro']
    if gain<.02 and fault_gain<.05:reasons.append('insufficient_gain')
    for key,factor in [('macro_rmse',1.005),('fault_macro',1.005),('pooled_rmse',1.005),('distance_macro',1.01)]:
        if c[key]>b[key]*factor:reasons.append('aggregate_regression:'+key)
    for row in clean:
        for receiver,scores in row['receivers'].items():
            a,z=scores['main'],scores['candidate']
            if a['rmse'] is not None and (z['rmse'] is None or z['rmse']>a['rmse']+max(.005,.05*a['rmse'])):
                reasons.append('per_bag_clean:'+row['bag']+'/'+receiver)
    for suite,entries in [('clean',clean),*suites.items()]:
        for row in entries:
            for receiver,scores in row['receivers'].items():
                a,z=scores['main'],scores['candidate'];bad=[]
                if (a['n'],a['coverage'])!=(z['n'],z['coverage']):bad.append('coverage')
                if z['false_stop_samples']>a['false_stop_samples']:bad.append('new_false_stop')
                if z.get('full_false_stops',0)>a.get('full_false_stops',0):bad.append('full_new_false_stop')
                if a.get('event_rmse') is not None and a.get('recovery_s') is not None and z.get('recovery_s') is None:
                    bad.append('new_individual_unrecovered')
                if bad:
                    violations.append(dict(suite=suite,bag=row['bag'],receiver=receiver,fault=row.get('fault'),reasons=bad))
                    reasons.extend(suite+':'+v for v in bad)
    extras={s:supplemental(suites[s]) for s in ('low_speed','common_mode','diagnostic')}
    for s in ('low_speed','common_mode'):
        a,z=extras[s]['main']['event_rmse'],extras[s]['candidate']['event_rmse']
        if a is None or z is None:reasons.append(s+':missing_reference')
        elif z>a*1.005:reasons.append(s+':event_regression')
    full_distance={n:v6.macro(suites['full_faulted'],n,'distance') for n in NAMES}
    if full_distance['main'] is None or full_distance['candidate'] is None:
        reasons.append('full_faulted_distance_missing')
    elif full_distance['candidate']>full_distance['main']*1.01:
        reasons.append('full_faulted_distance_regression')
    drive=sum(r['activation'].get('material_drive_steps',0) for r in clean)
    changed=sum(r['audit']['changed_outputs'] for r in clean);groups=collections.Counter()
    for r in clean:groups[r['group']]+=r['activation'].get('material_drive_steps',0)
    activation=drive>=100 and changed>=100 and sum(v>=10 for v in groups.values())>=3
    if not activation:reasons.append('insufficient_activation')
    verdict='REJECTED' if reasons else 'CONFIRMED'
    if reasons==['insufficient_activation']:verdict='INCONCLUSIVE'
    return dict(round='R4-v8-fixed',hypothesis_id='R4-H32',baseline_sha=BASE,baseline_tree=TREE,
        zip_sha256='a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2',
        source_status='VERIFIED',data_status='AVAILABLE',execution_status='COMPLETED',
        publication_status='NOT_ATTEMPTED',mechanism_status='ACTIVE' if drive else 'INACTIVE',
        coverage_status='SUFFICIENT' if activation else 'INSUFFICIENT',scientific_verdict=verdict,
        accuracy_contract_evaluated=True,accuracy_contract_passed=not reasons,candidate_implemented=True,
        measured_source_sha=os.environ.get('GITHUB_SHA'),report_sha=None,freeze_sha=None,
        validation_opened=False,test_opened=False,enabled_runtime_verified=False,ready_to_merge=False,
        variants_tested=['H32_event_time'],run_ids=[os.environ.get('GITHUB_RUN_ID')],
        rejection_reasons=sorted(set(reasons)),missing_evidence=[],
        next_resume_step='No validation after rejection' if reasons else 'Publish exact freeze before validation',
        summary=summary,clean_gain=gain,fault_gain=fault_gain,supplemental=extras,
        full_faulted_distance=full_distance,violations=violations,
        activation=dict(material_drive_steps=drive,changed_outputs=changed,groups=dict(groups)),
        max_commands=max(r['max_commands'] for r in clean),
        enabled_ros='NOT_RUN_AFTER_REJECTION' if reasons else 'NOT_RUN_PENDING_VALIDATION')


def write_tables(rows,out):
    records=[]
    for item in rows:
        for suite in ('clean','original','low_speed','common_mode','diagnostic','full_faulted'):
            entries=[item['clean']] if suite=='clean' else item[suite]
            for row in entries:
                for receiver,scores in row['receivers'].items():
                    for n in NAMES:
                        m=scores[n];rec=dict(bag=row['bag'],group=row['group'],suite=suite,receiver=receiver,model=n)
                        rec.update(fault_kind=row.get('fault',{}).get('kind'),start=row.get('fault',{}).get('start'),
                                   end=row.get('fault',{}).get('end'))
                        for k in ('n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples'):
                            rec[k]=m.get(k)
                        rec['distance_rmse']=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                        rec['residual_delta_s_terminal']=row.get('residual_delta_s_m',{}).get('terminal')
                        records.append(rec)
    with (out/'per_bag.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)


def benchmark(events,out):
    # Identical replay/output collectors; no feature-off audit in timed path.
    events=events[events[:,0]<=events[:,0].min()+70.]
    first=float(events[:,0].min());records=[]
    original_observer,original_timeline=ev.Observer,ev.Timeline
    def once(kind,save_row):
        o=baseline() if kind=='main' else candidate(profile()[0]);dur=[]
        original_step=o.step
        def step(t,*args):
            st=time.process_time_ns();a=original_step(t,*args);ns=time.process_time_ns()-st
            if t>=first+10.:dur.append(ns)
            return a
        o.step=step
        try:
            ev.Observer=lambda c:o
            ev.Timeline=lambda ob,**kw:(Timeline if kind=='main' else CommandEventTimeline)(ob,**kw)
            st=time.process_time();wall=time.perf_counter();a,_=original_replay(events,o.c,OPS)
            cpu=time.process_time()-st;wall=time.perf_counter()-wall
        finally:ev.Observer,ev.Timeline=original_observer,original_timeline
        if save_row:records.append(dict(model=kind,replay_cpu_s=cpu,replay_wall_s=wall,
            step_cpu_us=float(np.mean(dur))/1000,outputs=len(a),
            output_sha256=hashlib.sha256(a.tobytes()).hexdigest()))
    original_replay=ev.replay
    once('main',False);once('candidate',False)
    for repeat in range(6):
        for kind in (('main','candidate') if repeat%2==0 else ('candidate','main')):once(kind,True)
    s={n:{k:float(np.median([r[k] for r in records if r['model']==n])) for k in
          ('step_cpu_us','replay_cpu_s','replay_wall_s')} for n in NAMES}
    save(out/'COST.json',dict(repeats=records,median=s,warmup_seconds=10,span_seconds=70,
        replay_scope='whole 70s replay includes initial warmup; step cost excludes first 10s; warmup replay before repeats',
        rss_high_water_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        rss_scope='entire research process, not installed node',threads=1))


def run(out,workers):
    out.mkdir(parents=True,exist_ok=False)
    prov=provenance();prov.update(candidate_class=CommandEventObserver.__name__,candidate_module_file=sys.modules[CommandEventObserver.__module__].__file__,
        candidate_config=vars(profile()[0]),candidate_readout=vars(profile()[1]),candidate_enabled=True,
        isolated_core_sha256=hashlib.sha256(PATCHED_CORE.encode()).hexdigest(),
        research_sha256={str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*') if p.is_file()},
        plan_commit='abacda82c1856e921a940894a1c8265b249c06e9',validation_opened=False)
    save(out/'started.json',prov);(out/'isolated_core.py').write_text(PATCHED_CORE);(out/'core_hook.patch').write_text(HOOK_PATCH)
    save(out/'candidate.json',dict(config=vars(profile()[0]),readout=vars(profile()[1]),enabled=True))
    store=Store(out/'inventory-access.json');bags=store.plan['splits']['development']
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows=list(pool.map(worker,[(b,out) for b in bags]))
    result=decide(rows)
    b=result['summary']['main']
    expected=dict(macro_rmse=.09266814298282507,fault_macro=.2375486120563008,
        pooled_rmse=.1293056944774334,distance_macro=5.310295004801444,n=394221)
    for k,v in expected.items():
        if abs(b[k]-v)>1e-12:raise AssertionError(('Baseline fingerprint mismatch',k,b[k],v))
    result['baseline_reproduced']=True
    result['counts']=dict(development_bags=len(rows),groups=len(set(r['clean']['group'] for r in rows)),
       clean_receivers=sum(m['main']['rmse'] is not None for r in rows for m in r['clean']['receivers'].values()),
       suites={s:sum(len(r[s]) for r in rows) for s in ('original','low_speed','common_mode','diagnostic','full_faulted')},
       checked_off_ticks=sum(x['audit']['checked_ticks'] for r in rows for x in
         [r['clean']]+r['original']+r['low_speed']+r['common_mode']+r['diagnostic']+r['full_faulted']))
    save(out/'results.json',dict(provenance=prov,bags=rows));save(out/'SUMMARY.json',result);write_tables(rows,out)
    phase=[dict(group=r['clean']['group'],receivers=r['phase']) for r in rows]
    save(out/'PHASE.json',{n:{k:v6.macro(phase,n,k) for k in ('rmse','mae','bias','p95')} for n in NAMES})
    groups=[]
    for group in sorted(set(r['clean']['group'] for r in rows)):
        subset=[r for r in rows if r['clean']['group']==group]
        groups.append(dict(group=group,summary=legacy.aggregate([r['clean'] for r in subset],
            [x for r in subset for x in r['original']]),
            full_faulted_distance={n:v6.macro([x for r in subset for x in r['full_faulted']],n,'distance') for n in NAMES}))
    save(out/'per_group.json',groups)
    coststore=Store(out/'cost_access.json');events,_=coststore.load(bags[0],'development');benchmark(events,out)
    print('VERDICT',result['scientific_verdict'],result['rejection_reasons'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    if not 1<=a.workers<=2:raise ValueError('workers must be 1 or 2')
    run(a.output,a.workers)

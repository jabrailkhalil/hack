"""H12 isolated fixed-v7 driver. No final-test access, no model fitting."""
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
import resource
import sqlite3
import sys
import time
import csv
import build
from build import ROOT, HERE, BASELINE, sha, config, load
sys.path.insert(0,str(ROOT/'tools/finalization'))
import evaluate as ev
np=ev.np
from checks import AuditedCandidate, Baseline, Candidate, CandidateConfig, equal
from reserve_odometry.core import Config, Sample
from reserve_odometry.timeline import Timeline
spec=importlib.util.spec_from_file_location('h12_original_guarded_compare',ROOT/'tools/research_guarded/compare.py')
cg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=cg;spec.loader.exec_module(cg)
OPS={'rate_hz':20.,'alignment_delay_s':0.}
NAMES=('main','candidate')


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def csvwrite(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def provenance():
    files={str(p.relative_to(ROOT)):sha(p) for p in sorted(HERE.iterdir()) if p.is_file()}
    return dict(baseline=BASELINE,profile='guarded_readout_v7',observer='GuardedReadoutObserver',
        source_ref=os.environ.get('GITHUB_SHA','local'),source_sha256=files,baseline_manifest=build.verify(),
        parameters=asdict(config()),readout=dict(gain=1.,holdoff_s=.5,integral_age=True),operational=OPS,
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=platform.python_version(),
        numpy=np.__version__,test_evaluated=False,parameters_fitted=False)


class Store(ev.ex.Store):
    """Only a genuine development role extends the original train/validation IO."""
    def __init__(self,journal):
        super().__init__();self.journal=Path(journal)
    def load(self,bag,purpose):
        row=self.records[bag]
        if purpose not in ('train','development','validation') or row['split']!=purpose:
            raise PermissionError('Role denied before measurement IO: '+bag+'/'+purpose)
        path=self.root/bag/(bag+'_0.db3')
        allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose!='train' else [])
        self.access.append(dict(bag=bag,purpose=purpose,topics=allowed,sha256=row['sha256']))
        save(self.journal,dict(test_evaluated=False,access=self.access))
        if sha(path)!=row['sha256']:raise ValueError('Bag hash mismatch: '+bag)
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs


def transitions(events):
    """Source-clock controller transitions, independent of reference/error."""
    commands=events[events[:,1]==0];out=[];old=None
    def regime(u):return 1 if u>.04 else -1 if u<-.04 else 0
    for t,_,u in commands:
        if old is not None and (regime(u)!=regime(old) or abs(u-old)>=.1):
            if not out or t-out[-1]>=5.:out.append(float(t))
        old=u
    return out


def in_phase(t,anchors):
    if not anchors:return False
    k=int(np.searchsorted(anchors,t,side='right'))-1
    return k>=0 and t-anchors[k]<=2.


class ModelSpec:
    def __init__(self,name):self.name=name;self.c=config()
    def __getattr__(self,key):return getattr(self.c,key)


def pair(events,refs,fault=None,anchors=(),trace_path=None,reproduce=False):
    """Execute ORIGINAL ev.score and ev.replay; only algorithm factory differs."""
    instances={};arrays={};diag=Counter();maxima={};traces=[]
    def sink(o,e,b,args):
        d=o.audit_last
        if d:
            diag['updates']+=1
            age=d['max_age'];skew=d['skew'];delta=abs(d['increment_delta'])
            agekey='age_le_05' if age<=.05 else 'age_05_10' if age<=.1 else 'age_gt_10'
            skewkey='skew_le_025' if skew<=.025 else 'skew_gt_025'
            diag[agekey]+=1;diag[skewkey]+=1
            if delta>1e-9:
                diag['changed']+=1;diag['changed_'+agekey]+=1;diag['changed_'+skewkey]+=1
                if in_phase(e.t,anchors):diag['changed_phase']+=1
            maxima['max_age_s']=max(maxima.get('max_age_s',0.),age)
            maxima['max_skew_s']=max(maxima.get('max_skew_s',0.),skew)
        if in_phase(e.t,anchors):diag['phase_ticks']+=1
        if trace_path is not None:
            # Original fault warmup/failure/recovery: all ticks, no cherry-picking by error.
            traces.append(dict(t=e.t,base_v=b.v,candidate_v=e.v,inner_v=o.v,inner_s=o.s,
                disturbance=o.disturbance,drive_a=o.drive_a,pv=o.pv,mode=e.mode,
                front_status=e.front_status,rear_status=e.rear_status,
                base_correction=o.reference._velocity_correction,correction=o._velocity_correction,
                blocked_until=o._blocked_until if math.isfinite(o._blocked_until) else None,
                update=d is not None,increment_delta=d['increment_delta'] if d else None))
    def factory(s):
        o=Baseline(s.c) if s.name=='main' else AuditedCandidate(s.c)
        if s.name=='candidate':o.sink=sink
        instances[s.name]=o;return o
    original_observer,original_replay=ev.Observer,ev.replay
    def capture(events,c,ops,fault=None):
        a,r=original_replay(events,c,ops,fault);arrays[c.name]=a;return a,r
    try:
        ev.Observer=factory;ev.replay=capture
        raw=ev.score(events,refs,{'baseline_v2':ModelSpec('main'),'balanced_physics':ModelSpec('candidate')},OPS,fault)
    finally:
        ev.Observer=original_observer;ev.replay=original_replay
    row={k:v for k,v in raw.items() if k not in ('receivers','runtime')}
    row['runtime']={name:raw['runtime'][old] for old,name in [('baseline_v2','main'),('balanced_physics','candidate')]}
    row['receivers']={r:{'main':scores['baseline_v2'],'candidate':scores['balanced_physics']} for r,scores in raw['receivers'].items()}
    a,b=arrays['main'],arrays['candidate']
    assert a.shape==b.shape and np.array_equal(a[:,0],b[:,0])
    assert row['runtime']['main']==row['runtime']['candidate']
    assert not row['runtime']['main']['causal_errors'] and not row['runtime']['main']['resets']
    row['audit']=instances['candidate'].stats()|dict(timing_bins=dict(diag),maxima=maxima)
    row['output_hashes']={n:hashlib.sha256(x.tobytes()).hexdigest() for n,x in arrays.items()}
    row['schedule_sha256']=hashlib.sha256(a[:,0].tobytes()).hexdigest()
    if reproduce:
        # Independent canonical v7 driver, NOT cg.models() (its historical pins name v5 main).
        independent=cg.compare(events,refs,{'main':(Baseline,config()),'candidate':(Baseline,config())},fault)
        checked=0
        for receiver,scores in independent['receivers'].items():
            for k,v in scores['main'].items():
                assert equal(v,row['receivers'][receiver]['main'][k]),(receiver,k,v,row['receivers'][receiver]['main'][k])
                checked+=1
        assert independent['runtime']['main']==row['runtime']['main']
        row['baseline_reproduction']=dict(passed=True,compared_fields=checked,driver='unchanged research_guarded.compare + canonical v7 factory')
    row['phase_metrics']={}
    if len(a):
        phase=np.array([in_phase(t,anchors) for t in a[:,0]],bool)
        for receiver,values in refs.items():
            target=ev.ex.match(values,a[:,0]);mask=np.isfinite(target)&phase
            row['phase_metrics'][receiver]={n:ev.ex.metrics(x[:,0],x[:,1],target,mask) for n,x in arrays.items()}
    if trace_path is not None:csvwrite(trace_path,traces)
    return row


def diagnostics_windows(events,anchors):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid;count=0
    for anchor in anchors:
        if not 25.<anchor<events[:,0].max()-15.:continue
        i=max(0,int(np.searchsorted(t,anchor,side='right'))-1)
        if not valid[i] or (f[i]+r[i])*.5<=.4:continue
        fault=dict(kind='dropout',start=anchor,end=anchor+1.)
        window=events[(events[:,0]>=anchor-20.)&(events[:,0]<=anchor+11.1)]
        yield fault,window;count+=1
        if count==3:break


def macro(rows,name,key):
    groups={}
    for row in rows:
        for scores in row['receivers'].values():
            v=scores[name].get(key)
            if v is not None:groups.setdefault(row['group'],[]).append(v)
    return float(np.mean([np.mean(x) for x in groups.values()])) if groups else None


def summarize(clean,stress):
    s=cg.aggregate(clean,stress)
    for name in NAMES:
        s[name].update(mae=macro(clean,name,'mae'),signed_bias=macro(clean,name,'bias'),
            p95=macro(clean,name,'p95'),fault_mae=macro(stress,name,'mae'),fault_signed_bias=macro(stress,name,'bias'))
    return s


def guards(clean,stress,s,require_gain):
    reasons=[];missing=False;b,c=s['main'],s['candidate'];deltas={}
    for key,limit in [('macro_rmse',.005),('fault_macro',.005),('pooled_rmse',.005),('distance_macro',.01)]:
        x,y=b[key],c[key]
        if x is None or y is None:missing=True;reasons.append('missing:'+key);continue
        deltas[key]=dict(absolute=y-x,relative=(y/x-1) if x else None)
        if x==0:
            if y>1e-12:reasons.append('zero_baseline_guard:'+key)
        elif y>x*(1+limit):reasons.append('aggregate_regression:'+key)
    cgain=1-c['macro_rmse']/b['macro_rmse'] if b['macro_rmse'] and c['macro_rmse'] is not None else 0.
    fgain=1-c['fault_macro']/b['fault_macro'] if b['fault_macro'] and c['fault_macro'] is not None else 0.
    if require_gain and cgain<.02 and fgain<.05:reasons.append('insufficient_gain')
    for rows,clean_role in ((clean,True),(stress,False)):
        for row in rows:
            tag=row['bag']+(':'+str(row['fault']) if not clean_role else '')
            for name,rt in row['runtime'].items():
                if rt['causal_errors'] or rt['resets']:reasons.append('causality_or_reset:'+tag)
            for receiver,scores in row['receivers'].items():
                a,z=scores['main'],scores['candidate'];tagr=tag+'/'+receiver
                if a['n']!=z['n'] or a['coverage']!=z['coverage']:reasons.append('coverage:'+tagr)
                if z.get('false_stop_samples',0)>a.get('false_stop_samples',0):reasons.append('false_stop:'+tagr)
                if clean_role and a['rmse'] is not None:
                    if z['rmse'] is None or z['rmse']>a['rmse']+max(.005,.05*a['rmse']):reasons.append('per_bag:'+tagr)
                if not clean_role and a.get('event_rmse') is not None and a['recovery_s'] is not None and z['recovery_s'] is None:
                    reasons.append('new_unrecovered:'+tagr)
    return dict(passed=not reasons,reasons=sorted(set(reasons)),missing=missing,deltas=deltas,
                clean_gain=cgain,fault_gain=fgain)


def export_metrics(output,clean,stress,s):
    csvwrite(output/'aggregate.csv',[dict(model=n,**{k:v for k,v in m.items() if not isinstance(v,(dict,list))}) for n,m in s.items()])
    rows=[]
    for section,items in [('clean',clean),('fault',stress)]:
        for row in items:
            for receiver,scores in row['receivers'].items():
                for name,m in scores.items():
                    flat={k:v for k,v in m.items() if not isinstance(v,dict)}
                    flat['distance_rmse_m']=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                    rows.append(dict(section=section,bag=row['bag'],group=row['group'],receiver=receiver,model=name,
                        fault=row.get('fault',{}).get('kind'),fault_start=row.get('fault',{}).get('start'),
                        fault_end=row.get('fault',{}).get('end'),**flat))
    csvwrite(output/'per_bag.csv',rows)


def train(output):
    store=Store(output/'access.json');rows=[]
    for bag in store.plan['splits']['train']:
        events,refs=store.load(bag,'train');assert not any(refs.values())
        events=events[events[:,0]<=180.]
        if not len(events):rows.append(dict(bag=bag,input_events=0));continue
        row=pair(events,refs);rows.append(dict(bag=bag,input_events=len(events),**row))
        save(output/'progress.json',dict(rows=rows,access=store.access,test_evaluated=False))
        print('TRAIN',bag,len(events),row['audit']['checked_ticks'],flush=True)
    save(output/'results.json',dict(rows=rows,access=store.access,labels_used=False,parameters_fitted=False,test_evaluated=False))


def cost(events,output):
    """Fixed stream, warmup then six AB/BA pairs; no audit in timed code."""
    events=events[events[:,0]<=70.]
    timeline=Timeline(Baseline(config()),rate_hz=20.,delay_s=0.)
    requests=[]
    for t,ch,v in events:
        timeline.ingest(int(ch),Sample(float(t),float(v)))
        for e,held in timeline.advance():requests.append((e.t,*held))
    def cls(name):
        return Baseline(config()) if name=='main' else Candidate(config(),readout=CandidateConfig(integral_age=True))
    rows=[]
    for mode in ('step','replay'):
        for repeat in range(6):
            order=NAMES if repeat%2==0 else tuple(reversed(NAMES))
            for name in order:
                o=cls(name);collected=[]
                if mode=='step':
                    split=next((i for i,r in enumerate(requests) if r[0]>=10.),len(requests))
                    for args in requests[:split]:o.step(*args)
                    p,w=time.process_time(),time.perf_counter()
                    for args in requests[split:]:collected.append(o.step(*args))
                else:
                    tl=Timeline(o,rate_hz=20.,delay_s=0.)
                    split=next((i for i,row in enumerate(events) if row[0]>=10.),len(events))
                    for t,ch,v in events[:split]:
                        tl.ingest(int(ch),Sample(float(t),float(v)))
                        for _ in tl.advance():pass
                    p,w=time.process_time(),time.perf_counter()
                    for t,ch,v in events[split:]:
                        tl.ingest(int(ch),Sample(float(t),float(v)))
                        collected.extend(e for e,_ in tl.advance())
                cpu=time.process_time()-p;wall=time.perf_counter()-w
                digest=hashlib.sha256(repr(collected).encode()).hexdigest()
                rows.append(dict(mode=mode,repeat=repeat,order='AB' if repeat%2==0 else 'BA',model=name,
                    cpu_s=cpu,wall_s=wall,outputs=len(collected),cpu_us_per_output=cpu*1e6/len(collected),
                    wall_us_per_output=wall*1e6/len(collected),outputs_sha256=digest))
    summary={}
    for mode in ('step','replay'):
        summary[mode]={name:{key:float(np.median([r[key] for r in rows if r['mode']==mode and r['model']==name]))
                       for key in ('cpu_us_per_output','wall_us_per_output')} for name in NAMES}
        for name in NAMES:
            selected=[r for r in rows if r['mode']==mode and r['model']==name]
            assert len({r['outputs_sha256'] for r in selected})==1
        assert len({r['outputs'] for r in rows if r['mode']==mode})==1
    save(output/'cost.json',dict(rows=rows,summary=summary,
        process_rss_high_water_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        rss_scope='entire research Python process high water, NOT separate candidate ROS RSS',
        threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')},warmup_s=10.,measured_until_s=70.))
    csvwrite(output/'cost.csv',rows)


def evaluate_role(role,output):
    output.mkdir(parents=True,exist_ok=False);save(output/'started.json',provenance())
    store=Store(output/'access.json');clean=[];stress=[];special=[]
    for bag in store.plan['splits'][role]:
        events,refs=store.load(bag,role);anchors=transitions(events);group=store.records[bag]['group']
        meta=dict(bag=bag,group=group,role=role)
        c=dict(**meta,**pair(events,refs,anchors=anchors,reproduce=True));clean.append(c)
        fs=[]
        for i,(fault,window) in enumerate(cg.fault_windows(events)):
            row=dict(**meta,fault=fault,**pair(window,refs,fault,anchors,
                trace_path=output/'traces'/(bag+'-original-'+str(i)+'.csv')))
            stress.append(row);fs.append(row)
        ds=[]
        if role=='development':
            for i,(fault,window) in enumerate(diagnostics_windows(events,anchors)):
                row=dict(**meta,fault=fault,suite='transition_dropout_1s',**pair(window,refs,fault,anchors,
                    trace_path=output/'traces'/(bag+'-transition-'+str(i)+'.csv')))
                ds.append(row);special.append(row)
        save(output/'bags'/(bag+'.json'),dict(clean=c,stress=fs,diagnostic=ds,controller_anchors=anchors))
        print(role.upper(),bag,c['audit'],flush=True)
        if role=='development' and bag==sorted(store.plan['splits'][role])[0]:cost(events,output)
    s=summarize(clean,stress);g=guards(clean,stress,s,require_gain=role=='validation')
    changed=sum(r['audit']['materially_changed_updates'] for r in clean)
    updates=sum(r['audit']['readout_updates'] for r in clean)
    phase=sum(r['audit']['timing_bins'].get('changed_phase',0) for r in clean)
    groups=sorted({r['group'] for r in clean if r['audit']['materially_changed_updates']})
    activation=dict(changed=changed,readout_updates=updates,changed_fraction=changed/updates if updates else 0,
        changed_phase=phase,changed_groups=groups,passed=changed>=1000 and len(groups)>=3 and phase>=100,
        required=dict(changed=1000,groups=3,changed_phase=100,delta_threshold_mps=1e-9))
    if role=='development':
        verdict='REJECTED' if not g['passed'] and not g['missing'] else 'INCONCLUSIVE' if not activation['passed'] or g['missing'] else 'READY_TO_FREEZE'
    else:verdict='INCONCLUSIVE' if g['missing'] else 'ACCURACY_PASS_REQUIRES_ROS' if g['passed'] else 'REJECTED'
    decision=dict(verdict=verdict,activation=activation,accuracy_guards=g,
        validation_allowed=role=='development' and activation['passed'] and g['passed'],merge_ready=False,
        mechanism='sufficient_activation' if activation['passed'] else 'insufficient_natural_activation',
        test_evaluated=False,ros_enabled_measured=False)
    result=dict(**provenance(),role=role,clean=clean,stress=stress,summary=s,decision=decision,access=store.access)
    save(output/'results.json',result);save(output/'decision.json',decision);export_metrics(output,clean,stress,s)
    phase_rows=[dict(bag=r['bag'],group=r['group'],receivers=r['phase_metrics']) for r in clean]
    save(output/'phase_metrics.json',dict(rows=phase_rows,summary={n:{k:macro(phase_rows,n,k) for k in ('rmse','mae','bias','p95')} for n in NAMES},admission=False))
    if special:
        save(output/'diagnostic.json',dict(rows=special,summary=summarize([],special),admission=False))
    print(json.dumps(decision,indent=2),flush=True)
    return decision


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['development','freeze','validation'],required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output
    build.verify();config();load()
    if args.stage=='development':
        out.mkdir(parents=True,exist_ok=False);save(out/'started.json',provenance())
        (out/'candidate_guarded_readout.py').write_bytes(load().source)
        save(out/'candidate.json',dict(config=asdict(config()),readout=dict(gain=1.,holdoff_s=.5,integral_age=True)))
        train(out/'train');evaluate_role('development',out/'development')
    elif args.stage=='freeze':
        d=json.loads((out/'development/decision.json').read_text())
        if not d['validation_allowed']:raise PermissionError('No validation: development activation/safety guard')
        path=out/'FREEZE.json'
        if path.exists():raise FileExistsError(path)
        save(path,dict(**provenance(),development_results_sha256=sha(out/'development/results.json'),
            development_access_sha256=sha(out/'development/access.json'),train_results_sha256=sha(out/'train/results.json'),
            validation_opened=False,selected='H12_piecewise_integral',candidates_considered=1))
    else:
        frozen=json.loads((out/'FREEZE.json').read_text());current=provenance()
        for k in ('baseline','baseline_manifest','source_sha256','parameters','readout','operational'):
            if frozen[k]!=current[k]:raise ValueError('Freeze changed: '+k)
        assert frozen['development_results_sha256']==sha(out/'development/results.json')
        if not (out/'FREEZE_COMMIT.txt').exists():raise PermissionError('Publish freeze commit before validation')
        evaluate_role('validation',out/'validation')

if __name__=='__main__':main()

"""Fixed R2 H18 experiment; imports immutable score/masks/fault placement.

No validation is opened unless train/development safety+activation gates pass
and a separate committed freeze is supplied. No test measurement access.
"""
import argparse
from collections import defaultdict
import csv
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
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/finalization'))
import evaluate as ev
np,ex=ev.np,ev.ex
from reserve_odometry.core import Config, Sample, clip
from reserve_odometry.timeline import Timeline
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.outage_covariance import OutageCovarianceObserver, trusted_residual
spec=importlib.util.spec_from_file_location('guarded_metrics',ROOT/'tools/research_guarded/compare.py')
gc=importlib.util.module_from_spec(spec);spec.loader.exec_module(gc)
BASE='65bba39ed05c781f3f69a65c02f69931152cbfd9'
OPS=dict(rate_hz=20.,alignment_delay_s=0.)
PROFILE=json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())
PIN_PATHS=['src/reserve_odometry/reserve_odometry/'+n for n in
           ('core.py','guarded_readout.py','timeline.py','node.py','guarded_node.py')]
PIN_PATHS += ['src/reserve_odometry/config/guarded_readout_v7.'+x for x in ('yaml','json')]
PIN_PATHS += ['src/reserve_odometry/launch/odometry.launch.py','tools/finalization/evaluate.py',
             'tools/research_v3/experiment.py','tools/research_v3/manifest.py','tools/research_guarded/compare.py',
             'tools/export_bags.py','tools/get_dataset.py','research/plan_v3.json','research/split_v3.json','requirements-research.txt']
NEW_PATHS=['src/reserve_odometry/reserve_odometry/outage_covariance.py',
           'research/R2/H18/run.py','research/R2/H18/test_covariance.py','research/R2/H18/PLAN.md']
VARIANCE=.0025
PROBES=[]
RECORD=False
TRAIN=False


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):ev.save(p,obj)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def config():return Config(**PROFILE['config'])
def canonical(c=None):return GuardedReadoutObserver(c or config(),readout=ReadoutConfig(**PROFILE['readout']))
def candidate(c=None,enabled=True):
    return OutageCovarianceObserver(c or config(),readout=ReadoutConfig(**PROFILE['readout']),enabled=enabled,disturbance_variance=VARIANCE)


def provenance():
    for path in PIN_PATHS:
        if (ROOT/path).read_bytes()!=git('show',BASE+':'+path):raise AssertionError('changed pinned source: '+path)
    actual={};readout={};ops={}
    for line in (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text().splitlines():
        k,sep,v=line.strip().partition(':')
        if sep and k.startswith('model.'):actual[k[6:]]=float(v)
        if sep and k.startswith('readout.'):readout[k[8:]]=float(v)
        if k in ('rate_hz','alignment_delay_s'):ops[k]=float(v)
    assert actual==PROFILE['config'] and readout==PROFILE['readout'] and ops==OPS
    assert config().wheel_time_compensation==0 and config().adaptation_tau_s==.5
    assert 'guarded_odometry_node' in (ROOT/'src/reserve_odometry/launch/odometry.launch.py').read_text()
    return dict(round='R2-v7-fixed',hypothesis='H18',baseline_sha=BASE,
        source_commit=os.getenv('GITHUB_SHA',git('rev-parse','HEAD').decode().strip()),
        source_sha256={p:sha(ROOT/p) for p in PIN_PATHS+NEW_PATHS},profile=PROFILE,ops=OPS,
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=platform.python_version(),
        numpy=np.__version__,final_test_opened=False)


class RoleStore(ex.Store):
    """Same split/decoding/ordering, with an explicit real development role."""
    def __init__(self,journal):super().__init__();self.journal=journal
    def load(self,bag,purpose):
        row=self.records[bag]
        if purpose not in ('train','development','validation') or row['split']!=purpose:
            raise PermissionError('Role denied BEFORE measurement IO: '+bag+'/'+purpose)
        topics=list(ex.CHANNELS)+(list(ex.REFS) if purpose!='train' else [])
        self.access.append(dict(bag=bag,purpose=purpose,topics=topics,sha256=row['sha256'],status='opening'))
        save(self.journal,dict(final_test_opened=False,access=self.access))
        path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=row['sha256']:raise ValueError('Bag checksum mismatch')
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            sql='SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name IN ('+','.join('?' for _ in topics)+') ORDER BY m.timestamp,m.id'
            for topic,typ,raw in con.execute(sql,topics):
                stamp,values=ex.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ex.CHANNELS:
                    ch=ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ex.REFS[topic]].append((t,speed))
        self.access[-1]['status']='loaded';save(self.journal,dict(final_test_opened=False,access=self.access))
        return np.asarray(events,float).reshape(-1,3),refs


class Probe:
    """OFFLINE instrumentation; never supplies diagnostics/reference to runtime."""
    def __init__(self,inner):self.inner=inner;self.c=inner.c;self.reset()
    def __getattr__(self,k):return getattr(self.inner,k)
    def reset(self,**kw):
        self.inner.reset(**kw);self.rows=[];self.n=0;self.ss=0.;self.clipped=0;self.active_ticks=0;self.added=0.
    def step(self,t,command=None,front=None,rear=None):
        o=self.inner;old,old_d,oldpv,oldt=o.adapt_previous,o.disturbance,o.pv,o.t
        stale=not o._valid(command,t,o.c.command_timeout_s) or abs(command.value)>1.000001
        prior=oldpv+o.c.process_noise_v*(0 if oldt is None else t-oldt)*(4 if stale else 1)
        e=o.step(t,command,front,rear)
        if TRAIN:
            residual=trusted_residual(o,old,old_d,e,front,rear)
            if residual is not None:
                cap=(2*o.c.disturbance_limit_mps2)**2;self.n+=1;self.ss+=min(residual*residual,cap);self.clipped+=residual*residual>cap
        added=getattr(o,'h18_added_variance',0.)
        self.active_ticks+=int(added>0);self.added+=added
        if RECORD:
            if hasattr(o,'h18_prior'):prior=o.h18_prior
            gain=clip(1-o.pv/prior,0,1) if e.mode in ('FUSED','SINGLE_WHEEL') else 0.
            self.rows.append(dict(t=t,v=e.v,s=e.s,pvv=o.pv,pvd=getattr(o,'h18_pvd',0.),pdd=getattr(o,'h18_pdd',0.),
                active=getattr(o,'h18_active',False),added=added,gain=gain,d=o.disturbance,
                mode=e.mode,front_status=e.front_status,rear_status=e.rear_status,
                front_t=front.t if front else None,rear_t=rear.t if rear else None))
        return e


def factory(c):
    kind=getattr(c,'_h18_kind','main')
    o=canonical(c) if kind=='main' else candidate(c,enabled=kind!='off')
    p=Probe(o);PROBES.append(p);return p


def replay_plain(events,kind,fault=None):
    previous=ev.Observer
    try:
        ev.Observer=canonical if kind=='main' else lambda c:candidate(c,kind!='off')
        return ev.replay(events,config(),OPS,fault)
    finally:ev.Observer=previous


def paired(events,refs,metadata,out,label,fault=None,compatibility=False):
    global RECORD
    RECORD=fault is not None;PROBES.clear();previous=ev.Observer
    models={}
    for internal,kind in [('baseline_v2','main'),('balanced_physics','candidate')]:
        c=config();c._h18_kind=kind;models[internal]=c
    try:
        ev.Observer=factory;result=ev.score(events,refs,models,OPS,fault)
    finally:ev.Observer=previous
    probes=list(PROBES);trace={}
    for internal,name in [('baseline_v2','main'),('balanced_physics','candidate')]:
        result['runtime'][name]=result['runtime'].pop(internal)
        for scores in result['receivers'].values():scores[name]=scores.pop(internal)
    for name,p in zip(('main','candidate'),probes):
        trace[name]=p.rows
        result.setdefault('activation',{})[name]=dict(active_ticks=p.active_ticks,episodes=getattr(p.inner,'h18_episodes',0),added_variance=p.added)
        if fault:
            path=out/'traces'/f"{metadata['bag']}_{label}_{name}.csv";path.parent.mkdir(parents=True,exist_ok=True)
            if p.rows:
                with path.open('w') as f:
                    w=csv.DictWriter(f,fieldnames=list(p.rows[0]));w.writeheader();w.writerows(p.rows)
    if compatibility:
        a,ai=replay_plain(events,'main',fault);b,bi=replay_plain(events,'off',fault)
        if not np.array_equal(a,b,equal_nan=True) or ai!=bi:raise AssertionError('Disabled/canonical trajectory mismatch')
        # Check the actual driver result against the independent direct factory.
        for receiver,values in refs.items():
            target=ex.match(values,a[:,0]);mask=np.isfinite(target)
            if fault:mask&=(a[:,0]>=fault['start'])&(a[:,0]<fault['end']+10.)
            m=ex.metrics(a[:,0],a[:,1],target,mask)
            for key,value in m.items():
                if result['receivers'][receiver]['main'][key]!=value:raise AssertionError('Canonical driver mismatch')
        result['disabled_and_canonical_reproduced']=True
    result.update(metadata)
    if fault:result['fault']=fault
    return result,trace


def gate(clean,stress,summary,require_gain=True):
    reasons=[];b,c=summary['main'],summary['candidate']
    def worsened(a,z,relative):return z>a*(1+relative)+1e-12 if a else z>1e-12
    required=['macro_rmse','fault_macro','pooled_rmse','distance_macro']
    if any(b[k] is None or c[k] is None for k in required):return ['missing_reference']
    gains=[1-c[k]/b[k] if b[k]>0 else 0 for k in ('macro_rmse','fault_macro')]
    if require_gain and gains[0]<.02 and gains[1]<.05:reasons.append('insufficient_gain')
    for k,r in [('macro_rmse',.005),('fault_macro',.005),('pooled_rmse',.005),('distance_macro',.01)]:
        if worsened(b[k],c[k],r):reasons.append('aggregate_regression:'+k)
    for rows,isclean in ((clean,True),(stress,False)):
        for row in rows:
            for name in ('main','candidate'):
                rt=row['runtime'][name]
                if rt['causal_errors'] or rt['resets']:reasons.append('causality_or_reset:'+row['bag'])
            for receiver,scores in row['receivers'].items():
                x,y=scores['main'],scores['candidate'];tag=row['bag']+'/'+receiver
                if x['n']!=y['n'] or x['coverage']!=y['coverage']:reasons.append('coverage:'+tag)
                if y['false_stop_samples']>x['false_stop_samples']:reasons.append('false_stops:'+tag)
                if not isclean and x.get('recovery_s') is not None and y.get('recovery_s') is None:reasons.append('new_unrecovered:'+tag)
                if isclean and x['rmse'] is not None and (y['rmse'] is None or y['rmse']>x['rmse']+max(.005,.05*x['rmse'])):reasons.append('per_pair_clean:'+tag)
    return sorted(set(reasons))


def csv_metrics(out,clean,stress):
    rows=[]
    for kind,items in [('clean',clean),('fault',stress)]:
        for row in items:
            for receiver,m in row['receivers'].items():
                z=dict(bag=row['bag'],group=row['group'],receiver=receiver,role=row['role'],kind=kind,
                       fault=row.get('fault',{}).get('kind',''),start=row.get('fault',{}).get('start'),end=row.get('fault',{}).get('end'))
                for metric in ('rmse','mae','bias','p95','event_rmse','n','coverage','false_stop_samples','recovery_s'):
                    for name in ('main','candidate'):z[name+'_'+metric]=m[name].get(metric)
                for name in ('main','candidate'):z[name+'_distance']=m[name].get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                rows.append(z)
    if rows:
        with (out/'per_bag_receiver_fault.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def train(out):
    global TRAIN,RECORD
    TRAIN=True;RECORD=False;store=RoleStore(out/'access.json');stats=[];groups=defaultdict(lambda:[0,0.])
    for bag in store.plan['splits']['train']:
        events,_=store.load(bag,'train');p=Probe(canonical());old=ev.Observer
        try:ev.Observer=lambda c:p;arr,info=ev.replay(events,config(),OPS)
        finally:ev.Observer=old
        group=store.records[bag]['group'];groups[group][0]+=p.n;groups[group][1]+=p.ss
        stats.append(dict(bag=bag,group=group,n=p.n,squares=p.ss,clipped=p.clipped,outputs=len(arr),runtime=info));print('TRAIN',bag,p.n,flush=True)
    means={g:ss/n for g,(n,ss) in groups.items() if n}
    n=sum(r['n'] for r in stats);enough=n>=1000 and len(means)>=5
    variance=float(np.clip(np.quantile(list(means.values()),.9),.0025,.36)) if enough else None
    save(out/'training.json',dict(stats=stats,group_means=means,n=n,groups=len(means),eligible=enough,disturbance_variance=variance,
        method='causal trusted residual; clipped squares; group-mean 90th percentile; fixed range',train_reference_loaded=False))
    TRAIN=False


def diagnostic_events(events,anchor,kind,duration):
    a=events.copy();wheel=np.isin(a[:,1],(1,2));t=a[:,0]
    end=anchor+duration;corrupt_begin=anchor
    if kind=='after_dropout_false_pair':
        drop=wheel&(t>=anchor)&(t<anchor+5)
        add=wheel&(t>=anchor+5)&(t<end);a[add,2]+=2.;a=a[~drop];corrupt_begin=anchor+5
    else:
        mask=wheel&(t>=anchor)&(t<end)
        a[mask,2]+=5. if kind=='common_step' else np.minimum(1.,t[mask]-anchor)
    window=a[(a[:,0]>=anchor-20)&(a[:,0]<=end+10.1)]
    return window,dict(kind=kind,start=anchor,end=end),corrupt_begin


def diagnose(row,traces,refs,corrupt_begin):
    for name,trace in traces.items():
        bad=0;gains=[]
        for x in trace:
            for ch in ('front','rear'):
                stamp=x[ch+'_t']
                if stamp is not None and corrupt_begin<=stamp<row['fault']['end'] and x[ch+'_status'] in ('ACCEPTED','REACQUIRE_ACCEPTED'):bad+=1
            if x['t']>=row['fault']['end'] and x['gain']>0:gains.append(x['gain'])
        ratios={}
        if trace:
            target_times=np.array([x['t'] for x in trace]);v=np.array([x['v'] for x in trace]);p=np.array([x['pvv'] for x in trace])
            for receiver,values in refs.items():
                target=ex.match(values,target_times);mask=np.isfinite(target)&(target_times>=row['fault']['start'])
                ratios[receiver]=float(np.mean((v[mask]-target[mask])**2/np.maximum(p[mask],1e-12))) if mask.any() else None
        row.setdefault('diagnostics',{})[name]=dict(corrupted_acceptances=bad,first_recovery_gains=gains[:10],mean_squared_error_over_internal_variance=ratios)


def cost(events,out):
    warm=10.+float(events[0,0]);sequence=[];tl=Timeline(canonical(),20.,0.)
    for t,ch,v in events:
        tl.ingest(int(ch),Sample(float(t),float(v)))
        for e,held in tl.advance():sequence.append((e.t,held))
    def once(kind,level):
        o=canonical() if kind=='main' else candidate();outputs=[];start=None
        if level=='step':
            for t,held in sequence:
                if start is None and t>=warm:start=(time.process_time(),time.perf_counter())
                e=o.step(t,*held);outputs.append((e.t,e.v,e.s))
        else:
            timeline=Timeline(o,20.,0.)
            for t,ch,v in events:
                if start is None and t>=warm:start=(time.process_time(),time.perf_counter())
                timeline.ingest(int(ch),Sample(float(t),float(v)))
                for e,_ in timeline.advance():outputs.append((e.t,e.v,e.s))
        array=np.asarray(outputs);end=(time.process_time(),time.perf_counter())
        return dict(cpu_s=end[0]-start[0],wall_s=end[1]-start[1],outputs=len(array),postwarm_outputs=int(np.sum(array[:,0]>=warm))),array
    result=[];references={}
    for level in ('replay','step'):
        for block in range(6):
            for name in (('main','candidate') if block%2==0 else ('candidate','main')):
                metrics,a=once(name,level);key=(name,level)
                if key in references:assert np.array_equal(a,references[key])
                references[key]=a
                result.append(dict(level=level,block=block,name=name,**metrics))
    assert np.array_equal(references['main','step'],references['main','replay'])
    assert np.array_equal(references['candidate','step'],references['candidate','replay'])
    save(out/'cost.json',dict(runs=result,warmup_s=10,order='AB BA AB BA AB BA, separately step/replay',
        process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        rss_scope='whole offline process including scientific libraries and evaluation; not installed runtime RSS',
        installed_ros_latency_measured=False,omp=os.getenv('OMP_NUM_THREADS'),openblas=os.getenv('OPENBLAS_NUM_THREADS')))


def evaluate_role(role,out,training):
    global VARIANCE
    if not training['eligible']:
        save(out/'decision.json',dict(verdict='INCONCLUSIVE',admit_validation=False,reason='insufficient_train_residuals'));return
    VARIANCE=training['disturbance_variance'];store=RoleStore(out/'access.json')
    clean=[];stress=[];extra=[];coverage_groups=set();episodes=active=0;first_events=None
    for bag in store.plan['splits'][role]:
        events,refs=store.load(bag,role)
        if first_events is None:first_events=events.copy()
        meta=dict(bag=bag,group=store.records[bag]['group'],role=role)
        c,_=paired(events,refs,meta,out,'clean',compatibility=role=='development');clean.append(c)
        faults=list(gc.fault_windows(events));sf=[];diag=[]
        for idx,(fault,window) in enumerate(faults):
            row,traces=paired(window,refs,meta,out,'original'+str(idx),fault,compatibility=role=='development')
            diagnose(row,traces,refs,fault['end']) # original faults: recovery gains, not common corruption admission.
            stress.append(row);sf.append(row)
        if faults:
            anchor=faults[0][0]['start']
            for idx,(kind,duration) in enumerate([('common_step',.7),('common_step',1.2),('common_ramp',2.),('after_dropout_false_pair',6.)]):
                window,fault,corrupt_begin=diagnostic_events(events,anchor,kind,duration)
                row,traces=paired(window,refs,meta,out,'diagnostic'+str(idx),fault)
                diagnose(row,traces,refs,corrupt_begin);extra.append(row);diag.append(row)
        for row in [c]+sf:
            a=row['activation']['candidate'];episodes+=a['episodes'];active+=a['active_ticks']
            if a['episodes']:coverage_groups.add(meta['group'])
        save(out/'bags'/(bag+'.json'),dict(clean=c,stress=sf,diagnostic=diag))
        print(role.upper(),bag,'original',len(sf),'diagnostic',len(diag),flush=True)
    summary=gc.aggregate(clean,stress);rejections=gate(clean,stress,summary)
    safety=[r for r in gate(clean,stress,summary,False) if not r.startswith(('aggregate_regression:','per_pair_clean:'))]
    for row in extra:
        if row['diagnostics']['candidate']['corrupted_acceptances']>row['diagnostics']['main']['corrupted_acceptances']:
            safety.append('increased_common_mode_acceptance:'+row['bag']+':'+row['fault']['kind']+':'+str(row['fault']['end']-row['fault']['start']))
        for scores in row['receivers'].values():
            b,c=scores['main'],scores['candidate']
            if b['n']!=c['n'] or b['coverage']!=c['coverage']:safety.append('diagnostic_coverage:'+row['bag'])
            if c['false_stop_samples']>b['false_stop_samples']:safety.append('diagnostic_false_stops:'+row['bag'])
            if b['recovery_s'] is not None and c['recovery_s'] is None:safety.append('diagnostic_new_unrecovered:'+row['bag'])
        if any(row['runtime'][n]['causal_errors'] or row['runtime'][n]['resets'] for n in ('main','candidate')):safety.append('diagnostic_causality')
    enough=episodes>=10 and len(coverage_groups)>=3 and active>=100
    admit=enough and not safety
    verdict=('REJECTED' if safety else ('PENDING_VALIDATION' if admit else 'INCONCLUSIVE')) if role=='development' else ('REJECTED' if rejections or safety else 'ACCURACY_PASSED_ROS_PENDING')
    decision=dict(verdict=verdict,admit_validation=admit if role=='development' else False,disturbance_variance=VARIANCE,
        admission_rejections=rejections,safety_rejections=sorted(set(safety)),activation=dict(episodes=episodes,active_ticks=active,groups=len(coverage_groups),sufficient=enough),
        summary=summary,ready_to_merge=False,final_test_opened=False)
    save(out/'results.json',dict(role=role,clean=clean,stress=stress,diagnostic=extra,summary=summary,config=PROFILE,disturbance_variance=VARIANCE))
    save(out/'decision.json',decision);csv_metrics(out,clean,stress)
    diagpath=out/'diagnostics';diagpath.mkdir();csv_metrics(diagpath,[],extra)
    if role=='development':cost(first_events,out)
    else:
        old=json.loads((ROOT/'reports/champion_v7/PROMOTION.json').read_text())['combined_validation']['champion_v7']
        for new,previous in [('macro_rmse','clean_macro_rmse_mps'),('fault_macro','fault_macro_rmse_mps'),('distance_macro','distance_macro_rm')]:
            if abs(summary['main'][new]-old[previous])>1e-10:raise AssertionError('Executed canonical v7 differs from published cross-check')
        save(out/'baseline_reproduction.json',dict(executed=True,published_aggregates_matched=True,samples=summary['main']['n']))
    print(json.dumps(decision,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['train','development','freeze','validation'],required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--training',type=Path)
    parser.add_argument('--development',type=Path);parser.add_argument('--freeze',type=Path);parser.add_argument('--freeze-commit')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False);prov=provenance();save(args.output/'started.json',prov)
    if args.stage=='train':train(args.output);return
    if args.stage=='freeze':
        training=json.loads((args.training/'training.json').read_text());d=json.loads((args.development/'decision.json').read_text())
        if not d['admit_validation']:raise PermissionError('Development safety/coverage denies validation')
        store=ex.Store();save(args.output/'FREEZE.json',dict(**prov,training=training,
            training_sha256=sha(args.training/'training.json'),development_decision_sha256=sha(args.development/'decision.json'),
            data_sha256={r['bag']:r['sha256'] for r in store.records.values() if r['split']!='test'},validation_opened=False));return
    if args.stage=='validation':
        if not args.freeze_commit:raise PermissionError('A separate prevalidation freeze commit is mandatory')
        frozen=json.loads(args.freeze.read_text());rel=args.freeze.resolve().relative_to(ROOT)
        if git('show',args.freeze_commit+':'+str(rel))!=args.freeze.read_bytes():raise AssertionError('Freeze not committed')
        if frozen['source_sha256']!=prov['source_sha256']:raise AssertionError('Source changed after freeze')
        training=frozen['training']
    else:traininging=None;training=json.loads((args.training/'training.json').read_text())
    evaluate_role(args.stage,args.output,training)

if __name__=='__main__':main()

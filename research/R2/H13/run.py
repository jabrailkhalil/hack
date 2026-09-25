"""H13 isolated v7 factory. Legacy score, replay, matching and faults are unedited."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import csv
import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/finalization'),str(Path(__file__).parent)]
import evaluate as ev
import test_h13 as impl
from reserve_odometry.core import Config
from reserve_odometry.interval_readout import IntervalReadoutObserver
np=ev.np

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path); m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
v6=module('h13_v6_metrics','tools/research_v6/compare.py')
guarded=module('h13_guarded_faults','tools/research_guarded/compare.py')
BASE=impl.BASE; PROFILE=impl.PROFILE; OPS=dict(rate_hz=20.,alignment_delay_s=0.)
B='baseline_v2'; C='balanced_physics'; OFF='feature_off'; CTRL='skip_control'
LABELS={B:'R2_guarded_v7',C:'H13_interval_linear_v1',OFF:'H13_off',CTRL:'endpoint_same_skips'}
PLAN=ROOT/'research/R2/H13/PLAN.json'
SAVE=ev.save
FACTORY={}; PROBES={}; COLLECT=True; FULL_TRACE=False

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def head():return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def hashes():
    pin_record=json.loads((ROOT/'research/R2/H13/BASE_PINS.json').read_text())
    if __import__('hashlib').sha256(impl.original_source().encode()).hexdigest()!=pin_record['baseline_core_sha256']:raise ValueError('Independent baseline core mismatch')
    pins=pin_record['protected']
    for path,h in pins.items():
        if ev.sha(ROOT/path)!=h:raise ValueError('Protected baseline file changed: '+path)
    files=list(pins)+['src/reserve_odometry/reserve_odometry/core.py','src/reserve_odometry/reserve_odometry/interval_disturbance.py','src/reserve_odometry/reserve_odometry/interval_readout.py']
    files += [str(p.relative_to(ROOT)) for p in (ROOT/'research/R2/H13').glob('*') if p.is_file() and p.suffix in ('.py','.json','.patch','.wl','.md','.txt')]
    return {p:ev.sha(ROOT/p) for p in sorted(set(files))}

class RoleStore(ev.ex.Store):
    def __init__(self,journal):super().__init__();self.journal=journal
    def load(self,bag,purpose):
        row=self.records[bag]
        if purpose not in ('train','development','validation') or row['split']!=purpose:
            raise PermissionError('Forbidden role '+purpose)
        if purpose=='validation' and not os.environ.get('H13_FREEZE_COMMIT'):
            raise PermissionError('Missing published freeze barrier')
        path=self.root/bag/(bag+'_0.db3'); allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose!='train' else [])
        if ev.sha(path)!=row['sha256']:raise ValueError('DB checksum mismatch')
        self.access.append(dict(bag=bag,purpose=purpose,sha256=row['sha256'],topics=allowed,at_utc=now()))
        SAVE(self.journal,dict(test_opened=False,access=self.access))
        if purpose!='development':
            previous=self.access.copy(); answer=super().load(bag,purpose);self.access=previous;return answer
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

class Probe:
    """Offline recorder, never supplies reference/fault knowledge to the observer."""
    def __init__(self,inner,label):self.inner=inner;self.label=label;self.reset()
    @property
    def c(self):return self.inner.c
    @property
    def t(self):return self.inner.t
    def reset(self):
        self.inner.reset();self.rows=[];self.phase_rows=[];self.last_class=None;self.transition=-math.inf
        self.transition_updates=0;self.transitions=0;self.n=0;self.max_segments=0
        self.fingerprint=__import__('hashlib').sha256()
    def step(self,t,command=None,front=None,rear=None):
        old_adapt=self.inner.adapt_previous;old_v=self.inner.v
        e=self.inner.step(t,command,front,rear);self.n+=1
        # Same returned Estimate drives scoring, fingerprint and all diagnostics.
        self.fingerprint.update(repr(tuple(asdict(e).values())).encode())
        if command is not None and not e.command_stale:
            cls=1 if command.value>self.c.command_deadband else -1 if command.value < -self.c.command_deadband else 0
            if self.last_class is not None and cls!=self.last_class:self.transition=t;self.transitions+=1
            self.last_class=cls
        h=getattr(self.inner,'_interval_history',None);diag=h.last if h else None
        if self.label==B and old_adapt is not None and e.mode=='FUSED' and not e.command_stale:
            z=.5*(front.value+rear.value);tz=.5*(front.t+rear.t);delta=tz-old_adapt.t
            if .05<=delta<=self.c.max_age_s:
                ma=(z-old_adapt.value)/delta
                if abs(ma)<=self.c.max_accel_mps2 and abs(z)>.5:
                    gpost=self.inner.drive_a-self.inner.resistance(self.inner.v)
                    diag=dict(start=old_adapt.t,end=tz,measured_a=ma,current_pre_g=self.inner.drive_a-self.inner.resistance(old_v),current_post_g=gpost,original_target=ma-gpost,reason='')
        if e.mode!='WAITING_FOR_INITIALIZATION':self.phase_rows.append((t,e.v,t-self.transition<=1.))
        if h:self.max_segments=max(self.max_segments,len(h.segments))
        if diag is not None and not diag['reason'] and t-self.transition<=1.:self.transition_updates+=1
        if e.mode!='WAITING_FOR_INITIALIZATION' and (FULL_TRACE or (len(self.rows)<1200 and self.n%20==0)):
            self.rows.append(dict(t=t,v=e.v,s=e.s,d=e.disturbance,mode=e.mode,transition=t-self.transition<=1.,**(diag or {})))
        return e
    def report(self):
        h=getattr(self.inner,'_interval_history',None)
        return dict(counts=h.counts if h else {},transition_updates=self.transition_updates,transitions=self.transitions,
                    max_segments=self.max_segments,estimate_sha256=self.fingerprint.hexdigest(),ticks=self.n)

def factory(config):
    label=FACTORY[id(config)]
    if label==B: obs=impl.OriginalReadout.GuardedReadoutObserver(impl.OriginalCore.Config(**asdict(config)))
    else:obs=IntervalReadoutObserver(config,enabled=label!=OFF,endpoint_control=label==CTRL)
    if COLLECT:obs=Probe(obs,label);PROBES[label]=obs
    return obs

def evaluate(events,refs,role,fault=None):
    global FACTORY,PROBES,FULL_TRACE,COLLECT
    COLLECT=True;FULL_TRACE=fault is not None;PROBES={}
    names=[B,C,OFF]+([CTRL] if role=='development' else [])
    models={n:Config(**PROFILE['config']) for n in names};FACTORY={id(c):n for n,c in models.items()}
    old=ev.Observer;ev.Observer=factory
    try: result=ev.score(events,refs,models,OPS,fault)
    finally:ev.Observer=old
    reports={n:p.report() for n,p in PROBES.items()}
    if reports[B]['estimate_sha256']!=reports[OFF]['estimate_sha256'] or result['runtime'][B]!=result['runtime'][OFF]:
        raise AssertionError('Canonical v7 != disabled H13')
    result['mechanism']=reports
    result['phase_metrics']={}
    for name in names:
        a=np.array(PROBES[name].phase_rows).reshape(-1,3)
        result['phase_metrics'][name]={}
        for receiver,values in refs.items():
            target=ev.ex.match(values,a[:,0]);valid=np.isfinite(target)
            result['phase_metrics'][name][receiver]={label:ev.ex.metrics(a[:,0],a[:,1],target,valid&(a[:,2]==flag)) for label,flag in [('transition_1s',1),('other',0)]}
    traces={}
    for name in [B,C]+([CTRL] if role=='development' else []):
        rows=PROBES[name].rows
        stamps=np.array([r['t'] for r in rows])
        for receiver,values in refs.items():
            target=ev.ex.match(values,stamps)
            for row,value in zip(rows,target):row['v_error_'+receiver]=row['v']-float(value) if np.isfinite(value) else None
        traces[LABELS[name]]=rows
    return result,traces

def extra_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid;v=(f+r)/2
    phase=np.where(u>.04,1,np.where(u<-.04,-1,0))
    changes=np.r_[False,phase[1:]!=phase[:-1]]
    for label,mask,kind,duration in [('low_speed_lock',valid&(v>1)&(v<2),'lock',3.),('transition_dropout',valid&changes&(v>2),'dropout',5.)]:
        indices=np.flatnonzero(mask&(t>25)&(t<t[-1]-25))
        if len(indices):
            anchor=float(t[indices[0]]);fault=dict(kind=kind,start=anchor,end=anchor+duration)
            yield label,fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]

def worker(args):
    bag,role,out=args;out=Path(out);store=RoleStore(out/'access'/(bag+'.json'))
    events,refs=store.load(bag,role);meta=dict(bag=bag,group=store.records[bag]['group'])
    clean,tr=evaluate(events,refs,role);clean=dict(**meta,**clean)
    SAVE(out/'traces'/(bag+'-clean.json'),tr)
    stress=[];extra=[]
    if role!='train':
        for i,(fault,window) in enumerate(guarded.fault_windows(events)):
            scores,tr=evaluate(window,refs,role,fault);stress.append(dict(**meta,fault=fault,**scores))
            SAVE(out/'traces'/(bag+'-fault'+str(i)+'.json'),tr)
        if role=='development':
            for label,fault,window in extra_windows(events):
                scores,tr=evaluate(window,refs,role,fault);extra.append(dict(**meta,suite=label,fault=fault,**scores))
                SAVE(out/'traces'/(bag+'-'+label+'.json'),tr)
    result=dict(clean=clean,stress=stress,diagnostic_suites=extra,access=store.access)
    SAVE(out/'bags'/(bag+'.json'),result);print('CHECKPOINT',role,bag,clean['mechanism'][C]['counts'],flush=True)
    return result

def contract(clean,stress,candidate=C):
    sums={n:v6.summary(clean,stress,n) for n in (B,candidate)}
    a,b=sums[candidate],sums[B];reasons=[];safety=[]
    def frac(x,y):return (x/y-1) if y else None
    changes={k:frac(a[k],b[k]) if a[k] is not None and b[k] is not None else None for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse')}
    gain=any(changes[k] is not None and changes[k]<=-limit for k,limit in [('clean_rmse',.02),('fault_rmse',.05)])
    if not gain:reasons.append('insufficient_gain')
    for key,limit in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        if a[key] is None or b[key] is None:reasons.append('missing_aggregate:'+key)
        elif a[key]>b[key]*(1+limit)+(1e-12 if b[key]==0 else 0):reasons.append('aggregate_regression:'+key)
    for row in clean+stress:
        tag=row['bag']+('/'+str(row.get('fault')) if 'fault' in row else '')
        rt=row['runtime'][candidate]
        if rt['causal_errors'] or rt['resets']:safety.append('causal_or_reset:'+tag)
        for receiver,scores in row['receivers'].items():
            x,y=scores[candidate],scores[B];key=tag+'/'+receiver
            if x['n']!=y['n'] or x['coverage']!=y['coverage']:safety.append('coverage:'+key)
            if x.get('false_stop_samples',0)>y.get('false_stop_samples',0):safety.append('false_stops:'+key)
            if 'fault' in row and y.get('recovery_s') is not None and x.get('recovery_s') is None:safety.append('new_unrecovered:'+key)
            if 'fault' not in row and y['rmse'] is not None and (x['rmse'] is None or x['rmse']>y['rmse']+max(.005,.05*y['rmse'])):
                reasons.append('clean_bag_regression:'+key)
    for n in sums:
        sums[n].update(clean_mae=v6.macro(clean,n,'mae'),clean_signed_bias=v6.macro(clean,n,'bias'),fault_mae=v6.macro(stress,n,'mae'),fault_signed_bias=v6.macro(stress,n,'bias'),recovery_macro_s=v6.macro(stress,n,'recovery_s'))
    return dict(summary=sums,relative_change=changes,accuracy_passed=not(reasons+safety),reasons=sorted(set(reasons+safety)),safety_reasons=sorted(set(safety)))

def coverage(clean):
    groups=defaultdict(Counter);total=Counter();transitions=0
    for row in clean:
        m=row['mechanism'][C];total.update(m['counts']);groups[row['group']].update(m['counts']);transitions+=m['transition_updates']
    reasons=[]
    if total['applied']<100:reasons.append('too_few_updates')
    if sum(c['applied']>0 for c in groups.values())<3:reasons.append('too_few_groups')
    if transitions<20:reasons.append('too_few_transition_updates')
    if total['changed']<20:reasons.append('target_not_changed')
    if total['skipped']>.1*total['eligible']:reasons.append('too_many_skips')
    for group,c in groups.items():
        if c['eligible']>=100 and c['skipped']>.25*c['eligible']:reasons.append('group_skips:'+group)
    return dict(passed=not reasons,reasons=reasons,counts=dict(total),groups={g:dict(v) for g,v in groups.items()},transition_updates=transitions)

def csv_results(out,clean,stress,extra):
    rows=[]
    for suite,items in [('clean',clean),('original_fault',stress),('diagnostic',extra)]:
        for row in items:
            for receiver,models in row['receivers'].items():
                for name in (B,C,CTRL):
                    if name not in models:continue
                    m=models[name];rows.append(dict(suite=row.get('suite',suite),bag=row['bag'],group=row['group'],receiver=receiver,model=LABELS[name],fault=json.dumps(row.get('fault')),**{k:m.get(k) for k in ('rmse','mae','bias','p95','n','coverage','event_rmse','false_stop_samples','recovery_s')},distance=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')))
    with (out/'per_bag.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def benchmark(out):
    global COLLECT,FACTORY
    store=RoleStore(out/'cost_access.json');bag=sorted(store.plan['splits']['development'])[0];events,_=store.load(bag,'development')
    models={B:Config(**PROFILE['config']),C:Config(**PROFILE['config'])};FACTORY={id(c):n for n,c in models.items()};COLLECT=False
    records=[];old=ev.Observer;ev.Observer=factory
    try:
        for name in (B,C):ev.replay(events,models[name],OPS) # discarded warmup
        for repeat in range(4):
            for name in ((B,C) if repeat%2==0 else (C,B)):
                w=time.perf_counter();cpu=time.process_time();a,info=ev.replay(events,models[name],OPS)
                records.append(dict(repeat=repeat,order='AB' if repeat%2==0 else 'BA',model=LABELS[name],wall_s=time.perf_counter()-w,cpu_s=time.process_time()-cpu,outputs=len(a),runtime=info))
    finally:ev.Observer=old;COLLECT=True
    # Step-only synthetic timing is separately labelled; no dataset/ROS latency claim.
    micro=[];data=list(impl.stream(3000))
    for name in (B,C):
        obs=factory(models[name]);obs=obs.inner if isinstance(obs,Probe) else obs
        cpu=time.process_time()
        for args in data:obs.step(*args)
        micro.append(dict(model=LABELS[name],cpu_s=time.process_time()-cpu,steps=len(data)))
    result=dict(bag=bag,replay=records,synthetic_step_cpu=micro,threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')},rss_and_ros_latency_measured=False)
    SAVE(out/'cost.json',result)

def run(role,out,workers,freeze=None):
    out.mkdir(parents=True,exist_ok=False);source=hashes()
    if role=='validation':
        frozen=json.loads(freeze.read_text());commit=os.environ.get('H13_FREEZE_COMMIT')
        if not commit or source!=frozen['hashes'] or not frozen['development_eligible']:raise ValueError('Freeze mismatch/barrier')
        subprocess.run(['git','cat-file','-e',commit+'^{commit}'],cwd=ROOT,check=True)
    SAVE(out/'started.json',dict(at_utc=now(),role=role,hashes=source,source_commit=os.environ.get('H13_SOURCE_COMMIT',head()),freeze_commit=os.environ.get('H13_FREEZE_COMMIT'),baseline=BASE,profile=PROFILE,operational=OPS,test_evaluated=False,python=platform.python_version(),numpy=np.__version__))
    store=ev.ex.Store();tasks=[(b,role,str(out)) for b in store.plan['splits'][role]]
    with ProcessPoolExecutor(max_workers=workers) as pool: results=list(pool.map(worker,tasks))
    clean=[r['clean'] for r in results];stress=[x for r in results for x in r['stress']];extra=[x for r in results for x in r['diagnostic_suites']]
    cov=coverage(clean);decision=contract(clean,stress) if role!='train' else None
    result=dict(role=role,clean=clean,stress=stress,diagnostic_suites=extra,coverage=cov,decision=decision,access=[x for r in results for x in r['access']],test_evaluated=False)
    if role=='development':
        result['skip_control']=contract(clean,stress,CTRL)
        result['diagnostic_decision']=contract(clean,extra) if extra else None
        safety=(decision['safety_reasons']+([] if not extra else result['diagnostic_decision']['safety_reasons']))
        result['development_eligible']=cov['passed'] and not safety
        result['prevalidation_verdict']='READY' if result['development_eligible'] else 'REJECTED' if safety else 'INCONCLUSIVE'
        benchmark(out)
    SAVE(out/'results.json',result);csv_results(out,clean,stress,extra)
    SAVE(out/'decision.json',dict(verdict=('CONFIRMED_ACCURACY_ONLY' if decision['accuracy_passed'] else 'REJECTED') if role=='validation' else result.get('prevalidation_verdict','TRAIN_ONLY'),coverage=cov,decision=decision,development_eligible=result.get('development_eligible'),merge_ready=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ('clean','stress','diagnostic_suites','access')},ensure_ascii=False,indent=2),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['train','development','freeze','validation']);p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2);p.add_argument('--development',type=Path);p.add_argument('--freeze',type=Path)
    args=p.parse_args()
    if not 1<=args.workers<=4:raise ValueError('workers 1..4')
    if args.stage=='freeze':
        if args.output.exists():raise FileExistsError('Preserve freeze')
        dev=json.loads((args.development/'results.json').read_text())
        if not dev['development_eligible']:raise PermissionError('Development coverage/safety did not pass')
        store=ev.ex.Store()
        SAVE(args.output,dict(at_utc=now(),source_commit=os.environ.get('H13_SOURCE_COMMIT',head()),baseline=BASE,hashes=hashes(),development_eligible=True,development_sha256=ev.sha(args.development/'results.json'),data={r['bag']:r['sha256'] for r in store.records.values() if r['split']!='test'},model=PROFILE,candidate='H13_interval_linear_v1',test_evaluated=False))
    else:run(args.stage,args.output,args.workers,args.freeze)
if __name__=='__main__':main()

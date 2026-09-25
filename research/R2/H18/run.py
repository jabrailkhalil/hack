"""Preregistered covariance-only H18; canonical v7, original evaluator unchanged.

Training is wheel-only. Development is a real separately checked data role.
Validation requires a separately committed freeze and successful development.
No code path authorizes test/final measurement payloads.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict
import datetime
from functools import partial
import gzip
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
sys.path.insert(0, str(ROOT / 'tools/finalization'))
import evaluate as ev
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.outage_uncertainty import OutageUncertaintyObserver
from reserve_odometry.timeline import Timeline
np, ex = ev.np, ev.ex
BASE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'
HERE = ROOT/'research/R2/H18'
OPS = dict(rate_hz=20., alignment_delay_s=0.)
NAMES = ('baseline', 'control', 'candidate')
ALIASES = dict(baseline_v2='baseline', balanced_physics='control', H18='candidate')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


v6 = module('h18_v6_helpers', 'tools/research_v6/compare.py')
guarded = module('h18_guarded_helpers', 'tools/research_guarded/compare.py')
PROFILE = json.loads((ROOT/'src/reserve_odometry/config/guarded_readout_v7.json').read_text())
CFG = PROFILE['config']
READOUT = ReadoutConfig(**PROFILE['readout'])
ORIGINAL_REPLAY = ev.replay


def save(path, obj):
    ev.save(path, obj)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    paths = [p for p in HERE.glob('*') if p.is_file()]
    paths += [ROOT/'src/reserve_odometry/reserve_odometry/outage_uncertainty.py']
    paths += [ROOT/p for p in json.loads((HERE/'BASELINE_FILES.json').read_text())]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}


def verify_sources():
    for p, digest in json.loads((HERE/'BASELINE_FILES.json').read_text()).items():
        if sha(ROOT/p) != digest:
            raise ValueError('Immutable baseline/evaluator differs: '+p)
    if PROFILE['readout'] != dict(gain=1., holdoff_s=.5):
        raise ValueError('Wrong readout baseline')
    if CFG['adaptation_tau_s'] != .5 or CFG['wheel_time_compensation'] != 0.:
        raise ValueError('Wrong inner baseline')
    yaml = (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text()
    values = {}
    for line in yaml.splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and (key.startswith('model.') or key in ('rate_hz','alignment_delay_s','readout.gain','readout.holdoff_s')):
            values[key] = float(value)
    assert {k[6:]:v for k,v in values.items() if k.startswith('model.')} == CFG
    assert values['rate_hz'] == 20. and values['alignment_delay_s'] == 0.
    assert 'guarded_odometry_node' in (ROOT/'src/reserve_odometry/launch/odometry.launch.py').read_text()
    return source_hashes()


def metadata():
    return dict(round='R2-v7-fixed', hypothesis='H18', baseline_commit=BASE,
                source_commit=os.environ.get('GITHUB_SHA','local-working-copy'),
                source_sha256=verify_sources(), python=platform.python_version(),
                numpy=np.__version__, created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                run_id=os.environ.get('GITHUB_RUN_ID','local'), run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
                test_evaluated=False, operational=OPS, profile=PROFILE)


class RoleStore(ex.Store):
    """Adds true development access only; does not relabel train/validation."""
    def __init__(self, role, root=ROOT/'dataset/data'):
        if role not in ('train','development','validation'):
            raise PermissionError('Forbidden role: '+role)
        super().__init__(root)
        self.role = role

    def load(self, bag, purpose=None):
        purpose = purpose or self.role
        row = self.records[bag]
        if purpose != self.role or row['split'] != self.role:
            raise PermissionError('Role violation before DB IO: '+bag)
        if self.role != 'development':
            return super().load(bag, self.role)
        path = self.root/bag/(bag+'_0.db3')
        if sha(path) != row['sha256']:
            raise ValueError('Development DB checksum: '+bag)
        allowed = list(ex.CHANNELS)+list(ex.REFS)
        events, refs = [], dict(master=[], rover=[])
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                     'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic, typ, raw in con.execute(query, allowed):
                stamp, values = ex.decode(raw, typ)
                t = (stamp-row['sensor_start_ns'])/1e9
                if topic in ex.CHANNELS:
                    ch = ex.CHANNELS[topic]
                    events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed = math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):
                        refs[ex.REFS[topic]].append((t,speed))
        self.access.append(dict(bag=bag,purpose='development',topics=allowed,sha256=row['sha256']))
        return np.asarray(events,float), refs


@contextmanager
def factory(observer):
    original = ev.Observer
    ev.Observer = observer
    try:
        yield
    finally:
        ev.Observer = original


def predictor(events, candidate=False, pdd=0., fault=None, enabled=True):
    cls = partial(OutageUncertaintyObserver, readout=READOUT, pdd=pdd, enabled=enabled) if candidate else partial(GuardedReadoutObserver, readout=READOUT)
    with factory(cls):
        return ORIGINAL_REPLAY(events, Config(**CFG), OPS, fault)


class CalibrationProbe(GuardedReadoutObserver):
    """Offline-only observer instrumentation; no reference or future inputs."""
    def __init__(self, *args, **kwargs):
        self.blocks = []
        self.block = []
        self.residual_count = 0
        self.clipped_blocks = 0
        super().__init__(*args, **kwargs)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.block = []

    def step(self, t, command=None, front=None, rear=None):
        old, old_d = self.adapt_previous, self.disturbance
        result = super().step(t, command, front, rear)
        if result.mode == 'FUSED' and not result.command_stale and old is not None:
            tz = .5*(front.t+rear.t)
            z = .5*(front.value+rear.value)
            dt = tz-old.t
            if .05 <= dt <= self.c.max_age_s:
                a = (z-old.value)/dt
                if abs(a) <= self.c.max_accel_mps2 and abs(z) > .5:
                    residual = a-self.drive_a+self.resistance(self.v)-old_d
                    self.residual_count += 1
                    if self.block and tz-self.block[-1][0] > self.c.max_age_s:
                        self.block = []
                    self.block.append((tz,residual))
                    if tz-self.block[0][0] >= .5 and len(self.block) >= 3:
                        value = sum(x[1] for x in self.block)/len(self.block)
                        limit = 2*self.c.disturbance_limit_mps2
                        clipped = max(-limit,min(limit,value))
                        self.clipped_blocks += int(clipped != value)
                        self.blocks.append(dict(start=self.block[0][0],end=tz,n=len(self.block),residual=clipped))
                        self.block = []
        return result


def training(output):
    store = RoleStore('train')
    rows = []
    group_squares = defaultdict(list)
    save(output/'started.json', metadata())
    for bag in store.plan['splits']['train']:
        events, refs = store.load(bag)
        assert refs == dict(master=[],rover=[])
        instances = []
        def build(c):
            o = CalibrationProbe(c, readout=READOUT); instances.append(o); return o
        with factory(build):
            _, counters = ORIGINAL_REPLAY(events,Config(**CFG),OPS)
        o = instances[0]; group = store.records[bag]['group']
        group_squares[group].extend(b['residual']**2 for b in o.blocks)
        row = dict(bag=bag,group=group,blocks=len(o.blocks),trusted_residuals=o.residual_count,
                   clipped_blocks=o.clipped_blocks,sum_squares=sum(b['residual']**2 for b in o.blocks),runtime=counters)
        rows.append(row)
        save(output/'bags'/(bag+'.json'),dict(summary=row,blocks=o.blocks))
        save(output/'access.json',dict(test_evaluated=False,access=store.access))
        print('TRAIN',bag,row['blocks'],flush=True)
    groups = {g:dict(blocks=len(v),mean_square=float(np.mean(v))) for g,v in group_squares.items() if v}
    count = sum(x['blocks'] for x in rows)
    sufficient = count >= 100 and len(groups) >= 5
    raw = float(np.mean([g['mean_square'] for g in groups.values()])) if groups else None
    pdd = min(CFG['disturbance_limit_mps2']**2,max(1e-6,raw)) if raw is not None else None
    result = dict(**metadata(),name='fixed_consider',pdd=pdd,pdd_raw=raw,sufficient=sufficient,
                  training_bags=len(rows),blocks=count,groups=groups,per_bag=rows,
                  meaning='group-balanced second moment of causal wheel pseudo-residual block means, not independent truth')
    save(output/'calibration.json',result)
    print('TRAIN_CALIBRATION',pdd,'blocks',count,'groups',len(groups),'sufficient',sufficient,flush=True)


class TraceMixin:
    """OFFLINE-only trace collection; not imported by runtime module."""
    def __init__(self,*args,detail=False,corruption=(),**kwargs):
        self.trace=[]; self.detail=detail; self.corruption=corruption
        self.stats=dict(active_ticks=0,episodes=0,false_accepted=0,false_reacquired=0,accepted_updates=0)
        super().__init__(*args,**kwargs)

    def step(self,t,command=None,front=None,rear=None):
        old_t,old_pv=self.t,self.pv
        was_active=getattr(self,'_h18_active',False)
        e=super().step(t,command,front,rear)
        dt=0. if old_t is None else t-old_t
        prior=getattr(self,'_h18_prior',old_pv+self.c.process_noise_v*dt*(4 if e.command_stale else 1))
        statuses=(e.front_status,e.rear_status)
        accepted='ACCEPTED' in statuses and e.mode!='INITIALIZED'
        gain=max(0.,min(1.,1-self.pv/prior)) if accepted and prior>0 else 0.
        extra=getattr(self,'_h18_injection',0.)
        self.stats['active_ticks']+=int(extra>0.)
        self.stats['episodes']+=int(extra>0. and not was_active)
        self.stats['accepted_updates']+=int(accepted)
        for ch,s,status in zip((1,2),(front,rear),statuses):
            bad=s is not None and any(start<=s.t<end and ch in channels for start,end,channels in self.corruption)
            if bad:
                self.stats['false_accepted']+=int(status=='ACCEPTED')
                self.stats['false_reacquired']+=int(status=='REACQUIRE_ACCEPTED')
        if self.detail and e.mode!='WAITING_FOR_INITIALIZATION':
            self.trace.append([t,e.v,e.s,self.v,self.disturbance,self.pv,getattr(self,'_h18_pvd',0.),
                               getattr(self,'_h18_pdd',0.),gain,extra,e.front_status,e.rear_status,e.mode,prior])
        return e


class TracedBase(TraceMixin,GuardedReadoutObserver): pass
class TracedCandidate(TraceMixin,OutageUncertaintyObserver): pass


def paired(events,refs,pdd,fault=None,corruption=(),detail=False,check=False):
    """Pass-through capture: every score and replay formula executes unchanged."""
    models={key:Config(**CFG) for key in ALIASES}
    ids={id(c):ALIASES[key] for key,c in models.items()}
    objects,arrays,counters={},{},{}
    def build(c):
        name=ids[id(c)]
        cls=TracedCandidate if name=='candidate' else TracedBase
        kw=dict(pdd=pdd) if name=='candidate' else {}
        o=cls(c,readout=READOUT,detail=detail,corruption=corruption,**kw)
        objects[name]=o
        return o
    def capture(events,c,ops,fault=None):
        arr,info=ORIGINAL_REPLAY(events,c,ops,fault)
        name=ids[id(c)];arrays[name]=arr;counters[name]=info
        return arr,info
    saved=ev.replay
    try:
        ev.replay=capture
        with factory(build):
            result=ev.score(events,refs,models,OPS,fault)
    finally:
        ev.replay=saved
    for name in ('control','candidate'):
        assert np.array_equal(arrays[name][:,0],arrays['baseline'][:,0]),'Changed timestamps'
    assert np.array_equal(arrays['control'],arrays['baseline'],equal_nan=True)
    assert counters['baseline']==counters['control']
    reproduced=None
    if check:
        direct,info=guarded.predict(events,(partial(GuardedReadoutObserver,readout=READOUT),Config(**CFG)),fault)
        off,off_info=predictor(events,True,pdd,fault,False)
        assert np.array_equal(direct,arrays['baseline'],equal_nan=True),'Wrong canonical baseline driver'
        assert info==counters['baseline'],'Wrong baseline counters'
        assert np.array_equal(direct,off,equal_nan=True) and info==off_info,'Feature-off mismatch'
        reproduced=dict(direct_canonical_exact=True,feature_off_exact=True,
                        outputs=len(direct),outputs_sha256=hashlib.sha256(direct.tobytes()).hexdigest())
    for internal,public in ALIASES.items():
        result['runtime'][public]=result['runtime'].pop(internal)
        for scores in result['receivers'].values():
            scores[public]=scores.pop(internal)
    details=dict(stats={n:objects[n].stats for n in ('baseline','candidate')},
                 trace={n:objects[n].trace for n in ('baseline','candidate')})
    if detail:
        b,c=details['trace']['baseline'],details['trace']['candidate']
        assert len(b)==len(c)
        changed=sum(('ACCEPTED' in (y[10],y[11])) and (abs(x[8]-y[8])>1e-9 or abs(x[1]-y[1])>1e-9) for x,y in zip(b,c))
        details['changed_accepted_updates']=changed
        details['variance_vs_error']={}
        for n in ('baseline','candidate'):
            pred=arrays[n]; dt=details['trace'][n]
            vv=np.array([x[5] for x in dt])
            for receiver,values in refs.items():
                target=ex.match(values,pred[:,0]);mask=np.isfinite(target)
                if fault: mask &= (pred[:,0]>=fault['start']) & (pred[:,0]<fault['end']+10)
                err=(pred[:,1]-target)**2
                details['variance_vs_error'][n+'/'+receiver]=dict(n=int(mask.sum()),
                    mse=float(np.mean(err[mask])) if mask.any() else None,
                    mean_inner_variance=float(np.mean(vv[mask])) if mask.any() else None,
                    mean_squared_error_over_inner_variance=float(np.mean(err[mask]/np.maximum(vv[mask],1e-8))) if mask.any() else None,
                    calibrated_confidence_interval=False)
    return result,details,reproduced


def pct(a,b):
    return 100*(a/b-1) if b not in (None,0) and a is not None else None


def gates(clean,stress,require_gain):
    summary={n:v6.summary(clean,stress,n) for n in ('baseline','candidate')}
    for n in summary:
        summary[n].update(clean_mae=v6.macro(clean,n,'mae'),clean_signed_bias=v6.macro(clean,n,'bias'),
                          fault_mae=v6.macro(stress,n,'mae'),fault_signed_bias=v6.macro(stress,n,'bias'),
                          mean_confirmed_recovery_s=v6.macro(stress,n,'recovery_s'))
    b,c=summary['baseline'],summary['candidate']; reasons=[]
    for key,limit in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        x,y=b[key],c[key]
        if x is None or y is None: reasons.append('missing_aggregate:'+key)
        elif y>x*(1+limit)+ (1e-12 if x==0 else 0): reasons.append('aggregate_regression:'+key)
    if require_gain and not any(b[k] is not None and b[k]>0 and c[k] is not None and c[k]<=b[k]*(1-g) for k,g in [('clean_rmse',.02),('fault_rmse',.05)]):
        reasons.append('insufficient_gain')
    for row in clean+stress:
        key=row['bag']+'/'+str(row.get('fault','clean'))
        for n in ('baseline','candidate'):
            if row['runtime'][n]['causal_errors'] or row['runtime'][n]['resets']:
                reasons.append('causality_or_reset:'+key+'/'+n)
        for receiver,s in row['receivers'].items():
            x,y=s['baseline'],s['candidate']; tag=key+'/'+receiver
            if x['n']!=y['n'] or x['coverage']!=y['coverage']:reasons.append('coverage:'+tag)
            if y.get('false_stop_samples',0)>x.get('false_stop_samples',0):reasons.append('false_stops:'+tag)
            if 'fault' not in row and x['rmse'] is not None and (y['rmse'] is None or y['rmse']>x['rmse']+max(.005,.05*x['rmse'])):
                reasons.append('clean_bag_regression:'+tag)
            if 'fault' in row and x.get('recovery_s') is not None and y.get('event_rmse') is not None and y.get('recovery_s') is None:
                reasons.append('new_unrecovered:'+tag)
    return dict(summary=summary,rejections=sorted(set(reasons)),passed=not reasons,
                changes_percent={k:pct(c[k],b[k]) for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse')})


def diagnostic_cases(events, anchor):
    for kind,duration in [('common_5_0.7',.7),('common_5_1.2',1.2),('drop5_then_common2',6.)]:
        end=anchor+duration
        arr=events[(events[:,0]>=anchor-20)&(events[:,0]<=end+10.1)].copy()
        wheels=np.isin(arr[:,1],[1,2])
        if kind.startswith('common_5'):
            arr[wheels&(arr[:,0]>=anchor)&(arr[:,0]<end),2]+=5.
            corruption=[(anchor,end,(1,2))]
        else:
            arr=arr[~(wheels&(arr[:,0]>=anchor)&(arr[:,0]<anchor+5))]
            wheels=np.isin(arr[:,1],[1,2])
            arr[wheels&(arr[:,0]>=anchor+5)&(arr[:,0]<end),2]+=2.
            corruption=[(anchor+5,end,(1,2))]
        yield kind,arr,dict(kind='external_diagnostic',start=anchor,end=end),corruption


def write_csv(path,clean,stress,diagnostics):
    import csv
    fields=['suite','bag','group','receiver','fault','start','end','metric','baseline','candidate','delta','change_percent']
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for suite,rows in [('clean',clean),('original_fault',stress),('diagnostic',diagnostics)]:
            for row in rows:
                fault=row.get('fault',{})
                for receiver,scores in row['receivers'].items():
                    for metric in ('rmse','event_rmse','mae','bias','p95','recovery_s','n','coverage','false_stop_samples','distance'):
                        a=v6.metric_value(scores['baseline'],metric);b=v6.metric_value(scores['candidate'],metric)
                        w.writerow(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,
                            fault=row.get('diagnostic',fault.get('kind','')),start=fault.get('start'),end=fault.get('end'),metric=metric,
                            baseline=a,candidate=b,delta=b-a if a is not None and b is not None else None,change_percent=pct(b,a)))


def costs(events,pdd,output):
    records=[]
    for name in ('baseline','candidate'):
        predictor(events,name=='candidate',pdd)
    for pair in [('baseline','candidate'),('candidate','baseline'),('baseline','candidate'),('candidate','baseline')]:
        for name in pair:
            wall,cpu=time.perf_counter(),time.process_time()
            arr,_=predictor(events,name=='candidate',pdd)
            records.append(dict(scope='replay_with_output_collection',name=name,outputs=len(arr),
                cpu_s=time.process_time()-cpu,wall_s=time.perf_counter()-wall))
    timeline=Timeline(GuardedReadoutObserver(Config(**CFG),readout=READOUT),20,0)
    schedule=[]
    for t,ch,v in events:
        timeline.ingest(int(ch),Sample(float(t),float(v)))
        for estimate,held in timeline.advance():schedule.append((estimate.t,tuple(held)))
    def step_run(name):
        cls=OutageUncertaintyObserver if name=='candidate' else GuardedReadoutObserver
        kw=dict(pdd=pdd) if name=='candidate' else {}
        o=cls(Config(**CFG),readout=READOUT,**kw)
        # Schedule copied from the same causal Timeline. Forward gaps in this
        # first bag are checked below, not fabricated or silently integrated.
        outputs=[]
        for t,held in schedule:outputs.append(o.step(t,*held))
        return outputs
    # The first development stream has to permit direct step timing unchanged.
    if any(b[0]-a[0]>CFG['max_step_s']+1e-9 or b[0]<=a[0] for a,b in zip(schedule,schedule[1:])):
        direct_status='not_measured: timeline resets/gaps in fixed stream'
    else:
        direct_status='measured'
        for name in ('baseline','candidate'):step_run(name)
        for pair in [('baseline','candidate'),('candidate','baseline'),('baseline','candidate'),('candidate','baseline')]:
            for name in pair:
                wall,cpu=time.perf_counter(),time.process_time();out=step_run(name)
                records.append(dict(scope='step_with_output_collection',name=name,outputs=len(out),cpu_s=time.process_time()-cpu,wall_s=time.perf_counter()-wall))
    save(output/'cost.json',dict(records=records,ab_ba_pairs=4,warmups_per_algorithm_per_scope=1,
        first_development_bag=ex.Store().plan['splits']['development'][0],threads=dict(OPENBLAS_NUM_THREADS=os.getenv('OPENBLAS_NUM_THREADS'),OMP_NUM_THREADS=os.getenv('OMP_NUM_THREADS')),
        direct_status=direct_status,process_cumulative_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        rss_scope='whole offline research process, NOT isolated runtime/candidate RSS',
        installed_ros_latency_measured=False,interpretation='CPU and wall per offline scope; no ROS latency claim'))


def comparison(stage,training_path,output,freeze=None):
    training=json.loads(training_path.read_text());pdd=training['pdd']
    if not training['sufficient']:raise ValueError('Insufficient train calibration')
    verify_sources()
    if stage=='validation':
        if freeze is None:raise PermissionError('Separate prevalidation freeze required')
        frozen=json.loads(freeze.read_text())
        if frozen['source_sha256']!=source_hashes() or frozen['pdd']!=pdd or not frozen['development_passed']:
            raise PermissionError('Invalid frozen source/calibration/development')
        # A freeze must exist in committed HEAD, not merely an uncommitted file.
        rel=str(freeze.resolve().relative_to(ROOT))
        committed=subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)
        if committed!=freeze.read_bytes():raise PermissionError('Freeze not committed before validation')
    store=RoleStore(stage);clean=[];stress=[];diagnostics=[];details=[];checks=[]
    save(output/'started.json',metadata())
    first_events=None
    for bag in store.plan['splits'][stage]:
        events,refs=store.load(bag);group=store.records[bag]['group']
        if first_events is None:first_events=events.copy()
        row,_,reproduction=paired(events,refs,pdd,check=True)
        clean.append(dict(bag=bag,group=group,**row));checks.append(dict(bag=bag,**reproduction))
        windows=list(guarded.fault_windows(events))
        for fault,window in windows:
            corrupted=[(fault['start'],fault['end'],(1,) if fault['kind']=='bias' else (1,2))] if fault['kind'] in ('bias','lock') else []
            row,detail,_=paired(window,refs,pdd,fault,corrupted,detail=True)
            item=dict(bag=bag,group=group,fault=fault,**row);stress.append(item)
            details.append(dict(bag=bag,group=group,suite='original',fault=fault,**detail))
        if windows:
            for name,arr,fault,corruption in diagnostic_cases(events,windows[0][0]['start']):
                row,detail,_=paired(arr,refs,pdd,fault,corruption,detail=True)
                diagnostics.append(dict(bag=bag,group=group,fault=fault,diagnostic=name,**row))
                details.append(dict(bag=bag,group=group,suite=name,fault=fault,**detail))
        save(output/'bags'/(bag+'.json'),dict(clean=clean[-1],stress=[r for r in stress if r['bag']==bag],diagnostics=[r for r in diagnostics if r['bag']==bag]))
        save(output/'access.json',dict(test_evaluated=False,access=store.access))
        print(stage.upper(),bag,'original',len(windows),'baseline reproduced',reproduction['outputs'],flush=True)
    decision=gates(clean,stress,require_gain=stage=='validation')
    diagnostic_gate=gates(clean,diagnostics,require_gain=False)
    # Extra diagnostic accuracy does not replace original admission. Only its
    # safety outcomes (false stops/recovery/causality/coverage) block this stage.
    safety=[s for s in diagnostic_gate['rejections'] if not s.startswith(('aggregate_regression','missing_aggregate','clean_bag_regression'))]
    for d in details:
        b,c=d['stats']['baseline'],d['stats']['candidate']
        if c['false_accepted']+c['false_reacquired']>b['false_accepted']+b['false_reacquired']:
            safety.append('false_acceptance:'+d['bag']+'/'+d['suite']+'/'+str(d['fault']))
    coverage=dict(outages=sum(d['stats']['candidate']['episodes'] for d in details),
                  groups=len({d['group'] for d in details if d['stats']['candidate']['active_ticks']}),
                  active_ticks=sum(d['stats']['candidate']['active_ticks'] for d in details),
                  changed_accepted_updates=sum(d['changed_accepted_updates'] for d in details))
    sufficient=(coverage['outages']>=10 and coverage['groups']>=3 and coverage['active_ticks']>=200 and coverage['changed_accepted_updates']>=10)
    decision.update(stage=stage,safety_rejections=sorted(set(safety)),coverage=coverage,coverage_sufficient=sufficient,
        candidate='fixed_consider',pdd=pdd,baseline_reproduction=checks,test_evaluated=False,ready_to_merge=False)
    if decision['rejections'] or safety:verdict='REJECTED'
    elif not sufficient:verdict='INCONCLUSIVE'
    elif stage=='development':verdict='READY_FOR_FROZEN_VALIDATION'
    else:verdict='NUMERICALLY_ELIGIBLE_REQUIRES_INSTALLED_ROS'
    decision['verdict']=verdict
    decision['mechanism']='ACTIVE' if sufficient else 'INSUFFICIENT_COVERAGE'
    save(output/'results.json',dict(**metadata(),stage=stage,pdd=pdd,clean=clean,stress=stress,diagnostics=diagnostics,decision=decision))
    save(output/'decision.json',decision)
    write_csv(output/'per_bag.csv',clean,stress,diagnostics)
    with gzip.open(output/'traces.json.gz','wt') as f:json.dump(dict(columns=['t','published_v','published_s','inner_v','d','Pvv','Pvd','Pdd','gain','injection','front','rear','mode','prior'],cases=details),f,allow_nan=False)
    save(output/'diagnostics.json',dict(cases=[{k:v for k,v in d.items() if k!='trace'} for d in details],gate=diagnostic_gate))
    if stage=='development':costs(first_events,pdd,output)
    print('DECISION',json.dumps(decision,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['train','development','validation'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--training',type=Path)
    p.add_argument('--freeze',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    if a.stage=='train':training(a.output)
    else:
        training_path=a.training
        if a.stage=='validation':
            if a.freeze is None:raise PermissionError('Freeze required before validation')
            frozen=json.loads(a.freeze.read_text());training_path=ROOT/frozen['training_path']
        if training_path is None:raise ValueError('--training required')
        comparison(a.stage,training_path,a.output,a.freeze)


if __name__=='__main__':main()

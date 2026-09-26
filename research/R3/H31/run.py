"""R3-H31 role-safe, unchanged-scorer driver. No validation entry point.

The measured algorithm is an opt-in composition, not a changed canonical launch.
Original raw SQLite or verified lossless train/development transport is accepted.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import csv
from dataclasses import asdict
import datetime
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'src/reserve_odometry'),str(ROOT/'tools/finalization')]
from probe import profile,load,BASE
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config,Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver
from reserve_odometry.prequential_outage import PrequentialOutageObserver,EnsembleConfig
from reserve_odometry.timeline import Timeline


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

v6=module('h31_v6',ROOT/'tools/research_v6/compare.py')
guarded=module('h31_guarded_scoring',ROOT/'tools/research_guarded/compare.py')
h11=module('h31_h11',ROOT/'tools/research_h11/compare.py')
OPS=dict(rate_hz=20.,alignment_delay_s=0.)
NAMES={'baseline_v2':'v8','balanced_physics':'H31','equal_weight':'equal_weight'}


def save(path,data):ev.save(path,data)
def canon(data):return json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest_data(data):return hashlib.sha256(canon(data)).hexdigest()
def dump_gz(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wt',encoding='utf-8') as f:json.dump(data,f,separators=(',',':'),allow_nan=False)
def read_gz(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)


def identity():
    pins=json.loads((Path(__file__).parent/'BASELINE_PINS.json').read_text())
    for p,h in pins['files'].items():
        if ev.sha(ROOT/p)!=h:raise AssertionError('Baseline source changed: '+p)
    paths=list(pins['files'])+[str(p.relative_to(ROOT)) for p in (ROOT/'research/R3/H31').rglob('*')
                             if p.is_file() and p.suffix in ('.py','.json','.md','.wl')]
    paths+=['src/reserve_odometry/reserve_odometry/prequential_outage.py']
    sources={p:ev.sha(ROOT/p) for p in sorted(set(paths))}
    measured=os.environ.get('H31_SOURCE_SHA')
    if not measured:raise ValueError('Set H31_SOURCE_SHA to published source commit before measurement')
    return dict(baseline_sha=BASE,source_sha=measured,source_sha256=sources,
                profile={**asdict(profile()[0]),'readout':asdict(profile()[1])},
                python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),
                utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                run_id=os.environ.get('GITHUB_RUN_ID','local'),run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1'),
                validation_opened=False,test_opened=False)


class Data:
    def __init__(self,streams=None,data_root=None):
        self.store=ev.ex.Store(data_root or ROOT/'dataset/data');self.streams=Path(streams) if streams else None
        self.access=[];self.records=self.store.records;self.plan=self.store.plan
        if self.streams:
            m=json.loads((self.streams/'stream_manifest.json').read_text())
            assert m['baseline']==BASE and m['split_sha256']==ev.sha(ROOT/'research/split_v3.json')
            self.transport={r['bag']:r for r in m['records']}
    def get(self,bag,role):
        record=self.records[bag]
        if role not in ('train','development') or record['split']!=role:
            raise PermissionError('Only exact train/development membership allowed')
        if not self.streams:
            events,refs=load(self.store,bag,role);self.access=list(self.store.access)
            return events,refs
        m=self.transport[bag];path=self.streams/'streams'/role/(bag+'.npz')
        assert m['role']==role and m['group']==record['group'] and m['bag_sha256']==record['sha256']
        assert ev.sha(path)==m['stream_sha256']
        with np.load(path,allow_pickle=False) as f:
            events=f['events'];refs={k:f[k].tolist() for k in ('master','rover')}
        if role=='train' and any(refs.values()):raise AssertionError('Train reference prohibited')
        assert events.ndim==2 and events.shape[1]==3 and np.all(np.isin(events[:,1],[0,1,2]))
        self.access.append(dict(bag=bag,purpose=role,group=record['group'],
             bag_sha256=record['sha256'],transport_sha256=m['stream_sha256'],
             topics=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if role=='development' else [])))
        return events,refs


class Audited:
    """External diagnostics/equivalence only. Not used in CPU benchmarks."""
    def __init__(self,c,readout,*,candidate=False,equal=False):
        self.o=PrequentialOutageObserver(c,readout=readout,ensemble=EnsembleConfig(True,equal)) if candidate else GuardedReadoutObserver(c,readout=readout)
        self.check=GuardedReadoutObserver(deepcopy(c),readout=deepcopy(readout))
        self.off=PrequentialOutageObserver(deepcopy(c),readout=deepcopy(readout),ensemble=EnsembleConfig(False))
        self.candidate=candidate;self.steps=0;self.completions=0;self.effective=0
        self.selected=[];self.trace=[];self.eq_hash=hashlib.sha256();self.last_trace=-math.inf
        self.total_stats=Counter();self.max_records=0;self.limit_failures=0
    @property
    def c(self):return self.o.c
    @property
    def t(self):return self.o.t
    def reset(self,**kwargs):
        if self.candidate:self.total_stats.update(self.o.stats)
        self.o.reset(**kwargs);self.check.reset(**kwargs);self.off.reset(**kwargs)
    def step(self,*args,**kw):
        e=self.o.step(*args,**kw);truth=self.check.step(*args,**kw);disabled=self.off.step(*args,**kw)
        if disabled!=truth or vars(self.off.base)!=vars(self.check):raise AssertionError('Feature-off mismatch')
        inner=self.o.base if self.candidate else self.o
        if vars(inner)!=vars(self.check):raise AssertionError('Canonical inner-state mismatch')
        if not self.candidate and e!=truth:raise AssertionError('Canonical mismatch')
        self.steps+=1;self.eq_hash.update(canon(asdict(truth)))
        if self.candidate:
            d=self.o.last_diag;self.max_records=max(self.max_records,len(self.o.scores))
            if d:
                self.completions+=int(d['completed']);self.effective+=abs(d['delta_v'])>1e-6
                if d['triggered'] and d['selected']:
                    if not d['score_stamp']<d['trigger']:raise AssertionError('Score leakage at trigger')
                    self.selected.append(dict(t=d['trigger'],score_stamp=d['score_stamp'],count=self.o.outage.score_count,weights=list(self.o.outage.weights)))
                if d['triggered'] or d['completed'] or d['missing'] or abs(d['delta_v'])>0 or e.t-self.last_trace>=1:
                    # Compressed offline artifact only; no observer logging.
                    self.trace.append(dict(**d,base_v=truth.v,v=e.v,s=e.s,base_s=truth.s,
                         mode=e.mode,front_status=e.front_status,rear_status=e.rear_status,
                         completed_losses=list(self.o.scores[-1].losses) if d['completed'] else None))
                    self.last_trace=e.t
        return e
    def summary(self):
        stats=dict(self.total_stats)
        if self.candidate:
            count=Counter(stats);count.update(self.o.stats);stats=dict(count)
        return dict(steps=self.steps,completed=self.completions,effective_ticks=self.effective,
                    selected_outages=self.selected,stats=stats,max_records=self.max_records,
                    canonical_output_sha256=self.eq_hash.hexdigest(),inner_checks_passed=True,off_checks_passed=True)


@contextmanager
def factory(audit=True,baseline_only=False,equal=True):
    refs={};models={};instances={}
    for k in ('baseline_v2','balanced_physics')+(() if baseline_only or not equal else ('equal_weight',)):
        c,r=profile();models[k]=c;refs[id(c)]=(k,r)
    original=ev.Observer
    def new(c):
        k,r=refs[id(c)];candidate=k!='baseline_v2' and not baseline_only
        if audit:o=Audited(c,r,candidate=candidate,equal=k=='equal_weight')
        elif candidate:o=PrequentialOutageObserver(c,readout=r,ensemble=EnsembleConfig(True,k=='equal_weight'))
        else:o=GuardedReadoutObserver(c,readout=r)
        instances[k]=o;return o
    ev.Observer=new
    try:yield models,instances
    finally:ev.Observer=original


def score_case(events,refs,meta,output,baseline_only=False):
    fault=meta.get('fault');common=fault is not None and fault['kind']=='common_bias'
    if common:events=h11.inject_common(events,fault)
    with factory(baseline_only=baseline_only) as (models,instances):
        scores=ev.score(events,refs,models,OPS,fault)
        audits={NAMES[k]:(obj.summary() if isinstance(obj,Audited) else {}) for k,obj in instances.items()}
        hashes={a['canonical_output_sha256'] for a in audits.values()}
        if len(hashes)!=1:raise AssertionError('Baseline trajectory differs across models')
        for k,obj in instances.items():
            if isinstance(obj,Audited) and obj.trace:
                dump_gz(output/'traces'/(meta['case_id']+'-'+NAMES[k]+'.json.gz'),obj.trace)
    for row in scores['receivers'].values():
        for old,new in NAMES.items():
            if old in row:row[new]=row.pop(old)
    for old,new in NAMES.items():
        if old in scores['runtime']:scores['runtime'][new]=scores['runtime'].pop(old)
    result=dict(**meta,**scores,audit=audits)
    if baseline_only:
        for r in result['receivers'].values():
            # score adds common_front/mean keys to the second legacy alias only.
            a={k:v for k,v in r['v8'].items() if not k.startswith('common_')}
            b={k:v for k,v in r['H31'].items() if not k.startswith('common_')}
            if a!=b:raise AssertionError('Independent baseline reproduction mismatch')
        if result['runtime']['v8']!=result['runtime']['H31']:raise AssertionError('Baseline counters mismatch')
    return result


def low_windows(events):
    # Exact source 6190e82 tools/research_lock/low_speed.py, role adapter only.
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=np.flatnonzero(valid&(abs(f-r)<.15)&((f+r)/2>1)&((f+r)/2<2)&(u>=0)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25.))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            yield dict(kind='lock',start=anchor,end=anchor+duration),events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


def transition_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid;reg=np.where(u>.04,1,np.where(u<-.04,-1,0))
    for before,after in ((1,0),(0,-1)):
        idx=np.flatnonzero(valid[1:]&valid[:-1]&(reg[:-1]==before)&(reg[1:]==after)&(t[1:]>25)&(t[1:]<t[-1]-25))+1
        if len(idx):
            anchor=float(t[idx[0]]);fault=dict(kind='dropout',start=anchor,end=anchor+5.,transition=f'{before}_to_{after}')
            yield fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+15.1)]


def worker(args):
    bag,role,streams,data_root,output,baseline_only=args;output=Path(output)
    data=Data(streams,data_root);events,refs=data.get(bag,role);group=data.records[bag]['group'];rows=[]
    meta=dict(bag=bag,group=group,role=role,suite='clean',case_id=bag+'-clean')
    if role=='train':
        with factory(equal=False) as (models,instances):
            for name,c in models.items():
                pred,rt=ev.replay(events,c,OPS)
                obj=instances[name];a=obj.summary()
                rows.append(dict(model=NAMES[name],outputs=len(pred),runtime=rt,audit=a))
            if rows[0]['audit']['canonical_output_sha256']!=rows[1]['audit']['canonical_output_sha256']:
                raise AssertionError('Train inner mismatch')
        result=dict(bag=bag,group=group,role=role,models=rows,reference_used=False,access=data.access)
    else:
        rows.append(score_case(events,refs,meta,output,baseline_only))
        suites=(('original',guarded.fault_windows),('low_speed',low_windows),('common',h11.common_fault_windows),('transition',transition_windows))
        for suite,fn in suites:
            for number,(fault,window) in enumerate(fn(events)):
                meta=dict(bag=bag,group=group,role=role,suite=suite,fault=fault,case_id=f'{bag}-{suite}-{number}')
                rows.append(score_case(window,refs,meta,output,baseline_only))
        result=dict(bag=bag,group=group,role=role,cases=rows,access=data.access)
    dump_gz(output/'bags'/(bag+'.json.gz'),result)
    print('CHECKPOINT',role,bag,flush=True)
    return result


def summary(rows,name):
    clean=[r for r in rows if r['suite']=='clean'];stress=[r for r in rows if r['suite']=='original']
    s=v6.summary(clean,stress,name)
    s.update(clean_mae=v6.macro(clean,name,'mae'),clean_bias=v6.macro(clean,name,'bias'),
             clean_p95=v6.macro(clean,name,'p95'),fault_mae=v6.macro(stress,name,'mae'),
             fault_bias=v6.macro(stress,name,'bias'),recovery_s=v6.macro(stress,name,'recovery_s'))
    s['extra']={}
    for suite in ('low_speed','common','transition'):
        cases=[r for r in rows if r['suite']==suite]
        s['extra'][suite]=dict(event_macro_rmse=v6.macro(cases,name,'event_rmse'),
              full_macro_rmse=v6.macro(cases,name,'rmse'),mae=v6.macro(cases,name,'mae'),
              bias=v6.macro(cases,name,'bias'),recovery_s=v6.macro(cases,name,'recovery_s'),
              false_stops=v6.total(cases,name,'false_stop_samples'),unrecovered=v6.unrecovered(cases,name))
    return s


def evaluate_gate(rows,sums,risk):
    b=sums['v8'];c=sums['H31'];reasons=[];safety=[]
    missing=any(b[k] is None or c[k] is None for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse'))
    gains={k:(1-c[k]/b[k] if b[k] else None) for k in ('clean_rmse','fault_rmse')}
    if missing:reasons.append('missing_reference')
    elif not ((gains['clean_rmse'] is not None and gains['clean_rmse']>=.02) or (gains['fault_rmse'] is not None and gains['fault_rmse']>=.05)):
        reasons.append('insufficient_gain')
    for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse'):
        if c[k] is not None and b[k] is not None and c[k]>b[k]*(1.01 if k=='distance_rmse' else 1.005)+1e-12:
            reasons.append('aggregate_regression:'+k)
    for suite in ('low_speed','common','transition'):
        bb=b['extra'][suite]['event_macro_rmse'];cc=c['extra'][suite]['event_macro_rmse']
        if bb is None or cc is None:safety.append('missing_extra_reference:'+suite)
        elif cc>bb*1.005+1e-12:safety.append('extra_event_regression:'+suite)
    for row in rows:
        key=row['case_id'];rt=row['runtime']['H31']
        if rt['causal_errors'] or rt['resets']:safety.append('causality_or_reset:'+key)
        if row['audit']['H31']['stats'].get('limit_failures',0):safety.append('empty_limiter_intersection:'+key)
        for recv,m in row['receivers'].items():
            bb=m['v8'];cc=m['H31'];pair=key+'/'+recv
            if bb['n']!=cc['n'] or bb['coverage']!=cc['coverage']:safety.append('coverage:'+pair)
            if cc.get('false_stop_samples',0)>bb.get('false_stop_samples',0):safety.append('false_stop:'+pair)
            if bb.get('event_rmse') is not None and bb.get('recovery_s') is not None and cc.get('recovery_s') is None:
                safety.append('new_individual_unrecovered:'+pair)
            if row['suite']=='clean' and bb['rmse'] is not None and (cc['rmse'] is None or cc['rmse']>bb['rmse']+max(.005,.05*bb['rmse'])):
                reasons.append('per_bag_clean:'+pair)
    if not risk['passed']:safety.append('synthetic_counterexample')
    clean=[r for r in rows if r['suite']=='clean'];original=[r for r in rows if r['suite']=='original']
    completed=sum(r['audit']['H31']['completed'] for r in clean)
    completed_groups=sorted({r['group'] for r in clean if r['audit']['H31']['completed']})
    eligible={(r['bag'],r['fault']['start']) for r in original if r['audit']['H31']['selected_outages']}
    eligible_groups=sorted({r['group'] for r in original if r['audit']['H31']['selected_outages']})
    effective=sum(r['audit']['H31']['effective_ticks'] for r in original)
    reference_groups=sorted({r['group'] for r in original if r['audit']['H31']['effective_ticks'] and any(m['H31']['event_rmse'] is not None for m in r['receivers'].values())})
    coverage=dict(completed_forecasts=completed,completed_groups=completed_groups,
        eligible_original_contexts=len(eligible),eligible_original_groups=eligible_groups,
        effective_original_ticks=effective,altered_original_reference_groups=reference_groups)
    covered=(completed>=100 and len(completed_groups)>=3 and len(eligible)>=5 and len(eligible_groups)>=3
             and effective>=100 and len(reference_groups)>=2)
    coverage['passed']=covered
    reasons=sorted(set(reasons+safety))
    verdict='INCONCLUSIVE' if not covered else ('REJECTED' if reasons else 'DEVELOPMENT_PASSED_PENDING_VALIDATION')
    return dict(mechanism_status='ACTIVE' if effective else 'NOT_EFFECTIVE_ON_ORIGINAL_SUITE',
        coverage_status='SUFFICIENT' if covered else 'INSUFFICIENT',scientific_verdict=verdict,
        coverage=coverage,gains=gains,reasons=reasons,safety_reasons=sorted(set(safety)),
        development_contract_passed=covered and not reasons,accuracy_contract_passed=False,
        runtime_verified=False,ready_to_merge=False,validation_authorized=covered and not reasons,
        validation_opened=False,test_opened=False,
        runtime_stage='NOT_RUN_AFTER_REJECTION' if verdict=='REJECTED' else 'NOT_RUN_AFTER_INCONCLUSIVE' if not covered else 'PENDING')


def write_tables(output,rows,sums):
    fields=['suite','bag','group','receiver','kind','start','end','model','rmse','event_rmse','mae','bias','p95','n','coverage','false_stop_samples','recovery_s','distance_rmse','effective_ticks','completed','selected_outages']
    with (output/'per_bag.csv').open('w',newline='') as out:
        w=csv.DictWriter(out,fields);w.writeheader()
        for row in rows:
            f=row.get('fault',{})
            for rec,models in row['receivers'].items():
                for name in sums:
                    m=models[name];a=row['audit'][name]
                    line={k:row[k] for k in ('suite','bag','group')};line.update(receiver=rec,model=name,**{k:f.get(k) for k in ('kind','start','end')})
                    line.update({k:m.get(k) for k in ('rmse','event_rmse','mae','bias','p95','n','coverage','false_stop_samples','recovery_s')})
                    line.update(distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m'),effective_ticks=a['effective_ticks'],completed=a['completed'],selected_outages=len(a['selected_outages']))
                    w.writerow(line)
    groups={}
    for g in sorted({r['group'] for r in rows}):
        groups[g]={name:summary([r for r in rows if r['group']==g],name) for name in sums}
    save(output/'per_group.json',groups)
    with (output/'aggregate.csv').open('w',newline='') as out:
        w=csv.writer(out);w.writerow(['model','metric','value'])
        for name,s in sums.items():
            for k,v in s.items():
                if k!='extra':w.writerow([name,k,v])
                else:
                    for suite,mm in v.items():
                        for mk,mv in mm.items():w.writerow([name,suite+'.'+mk,mv])


def run_stage(args):
    provenance=identity();output=args.output;output.mkdir(parents=True,exist_ok=False)
    save(output/'started.json',provenance)
    role='train' if args.stage=='train' else 'development';data=Data(args.streams,args.data_root)
    jobs=[(bag,role,str(args.streams) if args.streams else None,str(args.data_root) if args.data_root else None,str(output),args.stage=='baseline') for bag in data.plan['splits'][role]]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:results=list(pool.map(worker,jobs))
    access=[a for r in results for a in r['access']];save(output/'access.json',dict(access=access,validation_opened=False,test_opened=False))
    if role=='train':
        total={name:dict(outputs=0,completed=0,effective_ticks=0) for name in ('v8','H31')}
        for r in results:
            for m in r['models']:
                s=total[m['model']];s['outputs']+=m['outputs'];s['completed']+=m['audit']['completed'];s['effective_ticks']+=m['audit']['effective_ticks']
        save(output/'SUMMARY.json',dict(bags=len(results),groups=len({r['group'] for r in results}),models=total,reference_used=False,equivalence_passed=True))
        return
    rows=[c for r in results for c in r['cases']]
    if args.stage=='baseline':
        names=('v8','H31');sums={n:summary(rows,n) for n in names}
        save(output/'SUMMARY.json',dict(independent_execution_reproduced=True,baseline=sums['v8'],bags=len(results),groups=len({r['group'] for r in results})))
        return
    if args.baseline is None:raise ValueError('Development requires --baseline completed stage')
    comparisons=0
    for result in results:
        old=read_gz(args.baseline/'bags'/(result['bag']+'.json.gz'))
        for before,after in zip(old['cases'],result['cases']):
            assert before['case_id']==after['case_id']
            assert before['runtime']['v8']==after['runtime']['v8']
            assert before['audit']['v8']['canonical_output_sha256']==after['audit']['v8']['canonical_output_sha256']
            for rec,mm in before['receivers'].items():
                assert mm['v8']==after['receivers'][rec]['v8'];comparisons+=1
    sums={name:summary(rows,name) for name in ('v8','H31','equal_weight')}
    testmod=module('h31_tests_for_risk',ROOT/'research/R3/H31/tests.py');risk=testmod.risk_probes()
    save(output/'synthetic_risk.json',risk)
    decision=evaluate_gate(rows,sums,risk);save(output/'decision.json',decision)
    case_counts=Counter(r['suite'] for r in rows)
    rc={suite:sum(m['v8']['rmse'] is not None for r in rows if r['suite']==suite for m in r['receivers'].values()) for suite in case_counts}
    save(output/'SUMMARY.json',dict(**decision,summary=sums,bags=len(results),groups=len({r['group'] for r in results}),
         cases=dict(case_counts),reference_cases=rc,baseline_reproduced=True,compared_case_receiver_metrics=comparisons,
         actual_published_estimate=True,equal_weight_is_diagnostic_only=True))
    write_tables(output,rows,sums)
    print(json.dumps(dict(decision=decision,summary=sums),indent=2),flush=True)


def tape(events,fault=None):
    c,r=profile();tl=Timeline(GuardedReadoutObserver(c,readout=r),rate_hz=20,delay_s=0);result=[]
    for t,ch,v in events:
        ch=int(ch)
        if fault and fault['start']<=t<fault['end']:
            if fault['kind']=='dropout' and ch in (1,2):continue
            if fault['kind']=='lock' and ch in (1,2):v=0
            if fault['kind']=='bias' and ch==1:v+=5
        tl.ingest(ch,Sample(float(t),float(v)))
        for e,held in tl.advance():result.append((e.t,*held))
    return result


def cost(args):
    provenance=identity();args.output.mkdir(parents=True,exist_ok=False);save(args.output/'started.json',provenance)
    data=Data(args.streams,args.data_root);bag=data.plan['splits']['development'][0];events,_=data.get(bag,'development')
    clean=events[events[:,0]<=events[0,0]+120.]
    original=[(f,w) for f,w in guarded.fault_windows(events) if f['kind']=='dropout'];f,w=original[0]
    trials=[]
    for label,flow,fault in (('healthy_learning',clean,None),('original_dropout',w,f)):
        held=tape(flow,fault);cut=held[0][0]+10
        for mode in ('step','replay'):
            for rep in range(6):
                for name in (('v8','H31') if rep%2==0 else ('H31','v8')):
                    c,r=profile();o=GuardedReadoutObserver(c,readout=r) if name=='v8' else PrequentialOutageObserver(c,readout=r)
                    collector=[]
                    if mode=='step':
                        cpu=wall=0.;measured=0
                        for tick in held:
                            if tick[0]<cut:o.step(*tick);continue
                            ts=time.perf_counter_ns();cs=time.process_time_ns();e=o.step(*tick)
                            cpu+=time.process_time_ns()-cs;wall+=time.perf_counter_ns()-ts;measured+=1
                            collector.append((e.t,e.v,e.s))
                    else:
                        # Whole official replay, after one explicit 10s observer warmup
                        # in a separate object; every measured replay starts identically.
                        for tick in held:
                            if tick[0]>=cut:break
                            o.step(*tick)
                        original_factory=ev.Observer
                        ev.Observer=(lambda cc:GuardedReadoutObserver(cc,readout=r)) if name=='v8' else (lambda cc:PrequentialOutageObserver(cc,readout=r))
                        ts=time.perf_counter_ns();cs=time.process_time_ns()
                        try:a,info=ev.replay(flow,c,OPS,fault)
                        finally:ev.Observer=original_factory
                        cpu=time.process_time_ns()-cs;wall=time.perf_counter_ns()-ts;measured=len(a);collector=a[:,:3].tolist()
                    trials.append(dict(dataset=label,bag=bag,mode=mode,repeat=rep,warmup=rep==0,model=name,
                         outputs=measured,cpu_us_per_output=cpu/1000/measured,wall_us_per_output=wall/1000/measured,
                         output_sha256=digest_data(collector),effective_ticks=o.stats['effective_ticks'] if name=='H31' and mode=='step' else None))
    summaries={}
    for label in ('healthy_learning','original_dropout'):
        summaries[label]={}
        for mode in ('step','replay'):
            summaries[label][mode]={}
            for name in ('v8','H31'):
                items=[x for x in trials if not x['warmup'] and x['dataset']==label and x['mode']==mode and x['model']==name]
                assert len({x['output_sha256'] for x in items})==1
                summaries[label][mode][name]={k:statistics.median(x[k] for x in items) for k in ('cpu_us_per_output','wall_us_per_output')}
    save(args.output/'trials.json',dict(trials=trials,scope='Python step/replay ONLY; not ROS latency/RSS',warmup='10s explicit + first AB pair discarded; replay includes full flow',summary=summaries))
    save(args.output/'access.json',dict(access=data.access,validation_opened=False,test_opened=False))
    print(json.dumps(summaries,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['baseline','train','development','cost'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path)
    p.add_argument('--streams',type=Path);p.add_argument('--data-root',type=Path);p.add_argument('--workers',type=int,default=2)
    args=p.parse_args()
    if not 1<=args.workers<=4:p.error('workers must be1..4')
    if args.stage=='cost':cost(args)
    else:run_stage(args)

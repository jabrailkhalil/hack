"""One fixed R2-H21 experiment. No test loader; unchanged score/masks/aggregation."""
import argparse
from collections import Counter
from dataclasses import asdict
import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
import subprocess
import sys
import time

from factory import ROOT, BASE, PKG, factories, canonical_bytes, normalize, assert_off, patch_text
sys.path.insert(0,str(ROOT/'tools/finalization'))
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config, Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

GR=module('h21_unchanged_faults','tools/research_guarded/compare.py')
V6=module('h21_unchanged_aggregation','tools/research_v6/compare.py')
B,C='r2_baseline','h21_envelope'
OPS=dict(rate_hz=20.,alignment_delay_s=0.)
MAKE,MOD,TMP,RUNTIME_DIR=factories()


def save(path,data):
    ev.save(path,data)


def source_manifest():
    unchanged=['tools/finalization/evaluate.py','tools/research_v3/experiment.py','tools/research_v3/manifest.py',
      'tools/export_bags.py','tools/research_guarded/compare.py','tools/research_v6/compare.py',
      'research/split_v3.json','research/plan_v3.json','src/reserve_odometry/config/guarded_readout_v7.json',
      'src/reserve_odometry/config/guarded_readout_v7.yaml','src/reserve_odometry/launch/odometry.launch.py',
      PKG+'/core.py',PKG+'/guarded_readout.py',PKG+'/timeline.py',PKG+'/node.py',PKG+'/guarded_node.py']
    for p in unchanged:
        if (ROOT/p).read_bytes()!=canonical_bytes(p):raise AssertionError('Protected R2 file changed: '+p)
    extras=list((ROOT/'research/R2/H21').glob('*'))+[ROOT/PKG/'reachable_interval.py']
    files=[ROOT/p for p in unchanged]+[p for p in extras if p.is_file()]
    return dict(baseline=BASE,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
       utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=platform.python_version(),numpy=np.__version__,
       source_sha256={str(p.relative_to(ROOT)):ev.sha(p) for p in files},
       applied_core_sha256=ev.sha(RUNTIME_DIR/'h21candidate/core.py'),
       applied_patch_sha256=hashlib.sha256(patch_text().encode()).hexdigest(),
       effective_model=asdict(MAKE('baseline').c),readout=asdict(MAKE('baseline').readout),operational=OPS,
       run_id=__import__('os').environ.get('GITHUB_RUN_ID','local'),test_evaluated=False)


class RoleStore(ev.ex.Store):
    """Keep true development role; GNSS is external evaluator input only."""
    def __init__(self,journal):
        super().__init__();self.journal=journal
    def load(self,bag,purpose):
        if purpose not in ('train','development','validation') or self.records[bag]['split']!=purpose:
            raise PermissionError('Measurement role denied before IO')
        if bag not in self.plan['splits'][purpose]:raise PermissionError('Split mismatch')
        rec=self.records[bag];p=self.root/bag/(bag+'_0.db3')
        if ev.sha(p)!=rec['sha256']:raise ValueError('DB checksum mismatch')
        allowed=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose!='train' else [])
        entry=dict(bag=bag,purpose=purpose,sha256=rec['sha256'],topics=allowed)
        self.access.append(entry);save(self.journal,dict(test_evaluated=False,access=self.access))
        events=[];refs={'master':[],'rover':[]};origin=rec['sensor_start_ns']
        with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as con:
            q=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name IN ('+
               ','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(q,allowed):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs


def checked_baseline():
    """Canonical package, separately reconstructed package, and off all agree."""
    o=MAKE('baseline');live=GuardedReadoutObserver(Config(**asdict(o.c)),readout=ReadoutConfig(**asdict(o.readout)))
    off=MAKE('off');step=o.step;reset=o.reset
    def checked(*args,**kwargs):
        out=step(*args,**kwargs);other=live.step(*args,**kwargs);disabled=off.step(*args,**kwargs)
        if normalize(out)!=normalize(other) or normalize(out)!=normalize(disabled):
            raise AssertionError('Canonical/disabled returned Estimate differs')
        # Exclude offline wrapper methods, which are not algorithm state.
        for key,value in vars(live).items():
            if normalize(value)!=normalize(getattr(o,key)) or normalize(value)!=normalize(getattr(off,key)):
                raise AssertionError('Canonical/disabled inner state differs: '+key)
        return out
    def reset_all(**kwargs):reset(**kwargs);live.reset(**kwargs);off.reset(**kwargs)
    o.step=checked;o.reset=reset_all
    return o


def record_step(o,tape):
    step=o.step
    def recorded(t,command=None,front=None,rear=None):
        out=step(t,command,front,rear)
        if out.mode!='WAITING_FOR_INITIALIZATION':
            bound=o.h21_last_bounds
            tape.append((t,out.v,out.s,out.mode,out.front_status,out.rear_status,
              o.h21_active,bound[0] if bound else None,bound[1] if bound else None,
              o.h21_rejections,front,rear,o.disturbance,o.drive_a))
        return out
    o.step=recorded


def diagnostics(tape,refs):
    t=np.array([x[0] for x in tape]);targets={k:ev.ex.match(v,t) for k,v in refs.items()}
    coverage={};labels=Counter();trace=[]
    for receiver,target in targets.items():
        eligible=np.array([bool(x[6]) and x[7] is not None for x in tape],dtype=bool) & np.isfinite(target)
        inside=np.array([x[7] is not None and x[7]<=v<=x[8] for x,v in zip(tape,target)],dtype=bool)
        coverage[receiver]=dict(n=int(eligible.sum()),inside=int((eligible&inside).sum()),
                               fraction=float(inside[eligible].mean()) if eligible.any() else None)
    # Batch matching at measurement stamps avoids repeatedly sorting a long bag.
    rejections=[(idx,reject) for idx,x in enumerate(tape) for reject in x[9]]
    rt=np.array([r[1][1] for r in rejections]);matched={k:ev.ex.match(v,rt) for k,v in refs.items()}
    for j,(idx,rej) in enumerate(rejections):
        values=[x[j] for x in matched.values() if math.isfinite(x[j])]
        _,stamp,z,lo,hi=rej
        if not values:label='unlabelled'
        elif all(abs(v-z)<=.25 and not lo<=v<=hi for v in values):label='false_rejection'
        elif all(abs(v-z)>.5 for v in values):label='fault_consistent_rejection'
        else:label='ambiguous_rejection'
        labels[label]+=1
    for idx,x in enumerate(tape):
        values=[a[idx] for a in targets.values() if math.isfinite(a[idx])]
        if values:
            for sample,status in zip(x[10:12],x[4:6]):
                if sample is not None and status=='ACCEPTED' and all(abs(sample.value-v)>.5 for v in values):
                    labels['accepted_far_from_reference']+=1
                    if x[6]:labels['active_missed_rejection_proxy']+=1
        if idx%20==0 or x[9]:
            trace.append(dict(t=x[0],v=x[1],s=x[2],mode=x[3],front_status=x[4],rear_status=x[5],
               active=x[6],lo=x[7],hi=x[8],width=x[8]-x[7] if x[7] is not None else None,
               veto=[list(r) for r in x[9]],disturbance=x[12],drive_a=x[13],
               reference={k:float(a[idx]) if math.isfinite(a[idx]) else None for k,a in targets.items()}))
    return dict(interval_reference_coverage=coverage,labels=dict(labels),
                active_ticks=sum(x[6] for x in tape),veto_ticks=sum(bool(x[9]) for x in tape),trace=trace)


def paired(events,refs,fault=None,with_diagnostics=True):
    bc,cc=Config(**asdict(MAKE('baseline').c)),Config(**asdict(MAKE('baseline').c))
    tape=[];objects={}
    previous=ev.Observer
    def factory(config):
        kind=B if config is bc else C
        o=checked_baseline() if kind==B else MAKE('candidate')
        objects[kind]=o
        if kind==C and with_diagnostics:record_step(o,tape)
        return o
    try:
        ev.Observer=factory
        result=ev.score(events,refs,{'baseline_v2':bc,'balanced_physics':cc},OPS,fault)
    finally:ev.Observer=previous
    for src,dst in [('baseline_v2',B),('balanced_physics',C)]:
        result['runtime'][dst]=result['runtime'].pop(src)
        for scores in result['receivers'].values():scores[dst]=scores.pop(src)
    result['canonical_and_disabled_per_tick_checked']=True
    result['h21_counts']=objects[C].h21_counts
    if with_diagnostics:result['diagnostics']=diagnostics(tape,refs)
    return result


def contract(clean,stress):
    summary={name:V6.summary(clean,stress,name) for name in (B,C)}
    base,cand=summary[B],summary[C];reasons=[];missing=False
    for key,limit in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        bv,cv=base[key],cand[key]
        if bv is None or cv is None:missing=True;reasons.append('missing:'+key);continue
        if cv>bv*(1+limit)+1e-12:reasons.append('aggregate_regression:'+key)
    gains={key:(1-cand[key]/base[key] if base[key] and cand[key] is not None else None) for key in ('clean_rmse','fault_rmse')}
    if not ((gains['clean_rmse'] is not None and gains['clean_rmse']>=.02) or
            (gains['fault_rmse'] is not None and gains['fault_rmse']>=.05)):reasons.append('insufficient_gain')
    for row in clean+stress:
        for name in (B,C):
            if row['runtime'][name]['causal_errors'] or row['runtime'][name]['resets']:reasons.append('causality_or_reset')
        for receiver,scores in row['receivers'].items():
            b,a=scores[B],scores[C];tag=row['bag']+'/'+receiver+('/'+str(row.get('fault')) if 'fault' in row else '')
            if b['n']!=a['n'] or b['coverage']!=a['coverage']:reasons.append('coverage:'+tag)
            if a.get('false_stop_samples',0)>b.get('false_stop_samples',0):reasons.append('false_stops:'+tag)
            if 'fault' not in row and b['rmse'] is not None and (a['rmse'] is None or a['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                reasons.append('per_bag:'+tag)
            if 'fault' in row and b.get('event_rmse') is not None and b.get('recovery_s') is not None and a.get('recovery_s') is None:
                reasons.append('new_unrecovered:'+tag)
    return dict(summary=summary,gains=gains,reasons=sorted(set(reasons)),passed=not reasons,missing=missing)


def csv_results(output,clean,stress,extra):
    import csv
    rows=[]
    for suite,items in [('clean',clean),('original_fault',stress),('diagnostic_fault',extra)]:
        for row in items:
            for receiver,models in row['receivers'].items():
                for name in (B,C):
                    m=models[name]
                    rows.append(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,model=name,
                        fault_kind=row.get('fault',{}).get('kind',''),duration=row.get('fault',{}).get('end',0)-row.get('fault',{}).get('start',0),
                        **{k:m.get(k) for k in ('rmse','mae','bias','p95','n','coverage','false_stop_samples','event_rmse','recovery_s')},
                        distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')))
    if rows:
        with (output/'per_bag.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def benchmark(events,output):
    window=events[events[:,0]<=events[:,0].min()+60.];trials=[]
    prev=ev.Observer
    try:
        # Identical collector; no equivalence checker or diagnostic wrappers timed.
        for rep in range(6):
            for name in ((B,C) if rep%2==0 else (C,B)):
                ev.Observer=lambda cfg:MAKE('baseline' if name==B else 'candidate')
                wall=time.perf_counter();cpu=time.process_time()
                a,_=ev.replay(window,MAKE('baseline').c,OPS)
                cpu=time.process_time()-cpu;wall=time.perf_counter()-wall
                trials.append(dict(kind='replay',repeat=rep,warmup=rep==0,model=name,cpu_s=cpu,wall_s=wall,
                                   outputs=len(a),cpu_us_per_output=cpu*1e6/len(a),wall_us_per_output=wall*1e6/len(a)))
        timeline=ev.Timeline(MAKE('baseline'),rate_hz=20,delay_s=0);ticks=[]
        for t,ch,v in window:
            timeline.ingest(int(ch),Sample(float(t),float(v)))
            for estimate,held in timeline.advance():ticks.append((estimate.t,held))
        for rep in range(6):
            for name in ((B,C) if rep%2==0 else (C,B)):
                o=MAKE('baseline' if name==B else 'candidate');collected=[]
                wall=time.perf_counter();cpu=time.process_time()
                for t,held in ticks:collected.append(o.step(t,*held))
                cpu=time.process_time()-cpu;wall=time.perf_counter()-wall
                trials.append(dict(kind='step',repeat=rep,warmup=rep==0,model=name,cpu_s=cpu,wall_s=wall,
                    outputs=len(collected),cpu_us_per_output=cpu*1e6/len(collected),wall_us_per_output=wall*1e6/len(collected)))
    finally:ev.Observer=prev
    medians={kind:{name:{k:statistics.median(x[k] for x in trials if x['kind']==kind and x['model']==name and not x['warmup'])
        for k in ('cpu_us_per_output','wall_us_per_output')} for name in (B,C)} for kind in ('step','replay')}
    result=dict(trials=trials,medians=medians,threads=1,scope='Python only; NOT installed ROS latency/RSS',
        evaluator_process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    save(output/'benchmark.json',result)


def run(args):
    if args.output.exists():raise FileExistsError('Use a new output directory')
    if args.stage=='freeze':
        result=json.loads((args.development/'decision.json').read_text())
        if not result['validation_authorized']:raise PermissionError('Prevalidation gate failed')
        args.output.mkdir(parents=True)
        save(args.output/'FROZEN.json',dict(**source_manifest(),development_decision_sha256=ev.sha(args.development/'decision.json')))
        return
    if args.stage=='validation':
        if args.freeze is None:raise PermissionError('Published freeze required')
        frozen=json.loads((args.freeze/'FROZEN.json').read_text());current=source_manifest()
        if frozen['source_sha256']!=current['source_sha256']:raise ValueError('Source changed after freeze')
        tracked=str((args.freeze/'FROZEN.json').resolve().relative_to(ROOT))
        subprocess.check_call(['git','ls-files','--error-unmatch',tracked],cwd=ROOT,stdout=subprocess.DEVNULL)
    args.output.mkdir(parents=True);store=RoleStore(args.output/'access.json');started=time.perf_counter()
    prov=source_manifest();save(args.output/'started.json',prov)
    clean=[];stress=[];extra=[];train=[];benchmark_done=False
    for bag in store.plan['splits'][args.stage]:
        events,refs=store.load(bag,args.stage);group=store.records[bag]['group']
        metadata=dict(bag=bag,group=group,role=args.stage)
        if args.stage=='train':
            row=paired(events,refs,with_diagnostics=False);train.append(dict(**metadata,outputs=row['outputs'],runtime=row['runtime'],h21_counts=row['h21_counts']))
            save(args.output/'bags'/(bag+'.json'),train[-1]);print('TRAIN',bag,row['outputs'],flush=True);continue
        row=dict(**metadata,**paired(events,refs));clean.append(row)
        faults=[];diags=[];windows=list(GR.fault_windows(events))
        for fault,window in windows:
            f=dict(**metadata,fault=fault,**paired(window,refs,fault));faults.append(f);stress.append(f)
        if windows:
            anchor=windows[0][0]['start']
            for kind,duration in [('dropout',30.),('ramp_positive',4.),('ramp_negative',4.)]:
                fault=dict(kind=kind,start=anchor,end=anchor+duration)
                window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)].copy()
                if kind.startswith('ramp'):
                    sel=(window[:,1]>0)&(window[:,0]>=anchor)&(window[:,0]<anchor+duration)
                    window[sel,2]+=(1 if kind=='ramp_positive' else -1)*np.minimum(3.,1.5*(window[sel,0]-anchor))
                f=dict(**metadata,fault=fault,**paired(window,refs,fault));extra.append(f);diags.append(f)
        if args.stage=='development' and not benchmark_done:
            benchmark(events,args.output);benchmark_done=True
        save(args.output/'bags'/(bag+'.json'),dict(clean=row,original_faults=faults,diagnostic_faults=diags))
        print(args.stage.upper(),bag,'active',row['h21_counts']['active'],'veto',row['h21_counts']['veto'],flush=True)
    if args.stage=='train':
        save(args.output/'results.json',dict(**prov,train=train,outputs={n:sum(r['outputs'] for r in train) for n in (B,C)},
            reference_used=False,parameters_fitted=False,elapsed_s=time.perf_counter()-started));return
    admission=contract(clean,stress);allrows=clean+stress+extra
    active=sum(r['h21_counts']['active'] for r in allrows);veto=sum(r['h21_counts']['veto_ticks'] for r in allrows)
    veto_groups=sorted({r['group'] for r in allrows if r['h21_counts']['veto_ticks']})
    labels=Counter()
    for r in allrows:labels.update(r['diagnostics']['labels'])
    covered=active>=200 and veto>=20 and len(veto_groups)>=2
    diagnostic_contract=contract(clean,extra)
    unsafe=[x for x in admission['reasons']+diagnostic_contract['reasons']
            if x.startswith(('false_stops:','new_unrecovered:','causality','coverage:'))]
    if labels['false_rejection']:unsafe.append('reference_confirmed_false_rejection')
    reasons=list(admission['reasons'])+unsafe
    verdict='INCONCLUSIVE' if not covered or admission['missing'] else ('REJECTED' if reasons else 'DEVELOPMENT_PASS')
    if unsafe:verdict='REJECTED'
    if args.stage=='validation' and not reasons:verdict='CONFIRMED_ACCURACY_PENDING_ROS'
    decision=dict(stage=args.stage,verdict=verdict,validation_authorized=covered and not reasons,
       mechanism_covered=covered,active_ticks=active,veto_ticks=veto,veto_groups=veto_groups,
       reference_classification=dict(labels),admission=admission,unsafe_reasons=sorted(set(unsafe)),
       diagnostic_suite_separate=True,test_evaluated=False,ready_to_merge=False,
       ros_benchmark='not run; required only if accuracy passes')
    result=dict(**prov,clean=clean,stress=stress,diagnostic_faults=extra,elapsed_s=time.perf_counter()-started)
    save(args.output/'results.json',result);save(args.output/'decision.json',decision)
    csv_results(args.output,clean,stress,extra)
    print(json.dumps(decision,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['train','development','freeze','validation'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--development',type=Path);p.add_argument('--freeze',type=Path)
    run(p.parse_args())

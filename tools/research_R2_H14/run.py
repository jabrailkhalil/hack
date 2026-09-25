"""R2-H14: one preregistered candidate; unchanged scoring, original fault suite."""
import argparse
from collections import Counter
from dataclasses import asdict
from functools import partial
import csv
import datetime
import gzip
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
from concurrent.futures import ProcessPoolExecutor
from common import (ROOT,BASE,ev,Config,GuardedReadoutObserver,ReadoutConfig,
                    AsyncAdaptationObserver,Pristine,profile,manifest,save,sha)
import numpy as np
sys.path.insert(0,str(ROOT/'tools/research_v6'))
import compare as v6
sys.path.insert(0,str(ROOT/'tools/research_guarded'))
import importlib.util
_spec=importlib.util.spec_from_file_location('h14_original_guarded',ROOT/'tools/research_guarded/compare.py')
gd=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(gd)
from reserve_odometry.core import Sample
from reserve_odometry.timeline import Timeline

NAMES={'baseline_v2':'v7_baseline','balanced_physics':'H14_async_pairs',
       'off':'H14_off','canonical':'v7_hook'}


class RoleStore(ev.ex.Store):
    """Read-only development extension; the original train/validation lock stays."""
    def __init__(self,journal):
        super().__init__();self.journal=Path(journal)
    def load(self,bag,purpose):
        # No sqlite connection, target query or final loader before this check.
        if purpose not in ('train','development','validation'):
            raise PermissionError('Final/test measurement payloads remain locked')
        row=self.records[bag]
        if row['split']!=purpose or bag not in self.plan['splits'][purpose]:
            raise PermissionError('Role mismatch before IO')
        topics=list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose!='train' else [])
        self.access.append(dict(bag=bag,purpose=purpose,topics=topics,sha256=row['sha256']))
        save(self.journal,dict(test_evaluated=False,access=self.access))
        if purpose!='development':
            n=len(self.access); result=super().load(bag,purpose)
            self.access=self.access[:n];return result
        path=self.root/bag/(bag+'_0.db3')
        if ev.ex.digest(path)!=row['sha256']:raise ValueError('DB checksum mismatch')
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                   'WHERE t.name IN ('+','.join('?' for _ in topics)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,topics):
                stamp,values=ev.decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ev.ex.CHANNELS:
                    ch=ev.ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ev.ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs


def make_models():
    c,r,ops=profile();cfg=asdict(c)
    models={k:Config(**cfg) for k in NAMES}
    classes={'baseline_v2':partial(Pristine,readout=r),
             'balanced_physics':partial(AsyncAdaptationObserver,readout=r),
             'off':partial(AsyncAdaptationObserver,readout=r,enabled=False),
             'canonical':partial(GuardedReadoutObserver,readout=r)}
    return models,classes,ops


def score(events,refs,fault=None,trace_path=None):
    """Factory and telemetry wrapper only; original ev.score/replay code runs."""
    models,classes,ops=make_models();by_id={id(v):k for k,v in models.items()}
    captures={};diag={};recorders={};step_pairs={}
    original_factory,original_replay=ev.Observer,ev.replay
    def factory(c):
        key=by_id[id(c)];o=classes[key](c);real_step=o.step
        stats=dict(healthy_s=0.,healthy_without_fused_s=0.,pair_rows=0,
                   async_pair_rows=0,updates=0,async_updates=0,output_ticks=0)
        diag[key]=stats;recorders[key]=o;step_pairs[key]=[]
        last_pair=None
        def step(t,command=None,front=None,rear=None):
            nonlocal last_pair
            old_t=o.t;d_before=o.disturbance
            result=real_step(t,command,front,rear);dt=0. if old_t is None else t-old_t
            statuses=(result.front_status,result.rear_status)
            healthy=(not result.command_stale and result.mode not in
                     ('INITIALIZED','WAITING_FOR_INITIALIZATION','REACQUIRING','STOPPED')
                     and all(s in ('ACCEPTED','DUPLICATE_OR_OLD') for s in statuses)
                     and all(o._valid(s,t,c.max_age_s) for s in (front,rear))
                     and abs(front.t-rear.t)<=c.pair_skew_s
                     and abs(front.value-rear.value)<=c.disagreement_mps)
            stats['output_ticks']+=1
            if healthy:
                stats['healthy_s']+=dt
                if result.mode!='FUSED':stats['healthy_without_fused_s']+=dt
            pair=getattr(o,'_h14_last_pair',None)
            if pair is not None and pair!=last_pair:
                stats['pair_rows']+=1;stats['async_pair_rows']+=bool(pair[4])
                stats['updates']+=bool(o._h14_updated)
                stats['async_updates']+=bool(o._h14_updated and pair[4]);last_pair=pair
            if trace_path is not None and key in ('baseline_v2','balanced_physics'):
                # Bounded diagnostic excerpt; full clean scores still use all data.
                in_window = ((fault is not None and fault['start']-1<=t<=fault['end']+2)
                             or (fault is None and healthy and result.mode!='FUSED'
                                 and len(step_pairs[key])<1000))
                if in_window:
                    step_pairs[key].append([t,result.v,result.s,o.v,o.pv,d_before,
                        o.disturbance,result.mode,*statuses,
                        None if front is None else front.t,None if rear is None else rear.t,
                        pair,bool(getattr(o,'_h14_updated',False))])
            return result
        o.step=step
        return o
    def replay(*args,**kwargs):
        a,info=original_replay(*args,**kwargs);key=by_id[id(args[1])]
        captures[key]=(a,info)
        return a,info
    try:
        ev.Observer=factory;ev.replay=replay
        row=ev.score(events,refs,models,ops,fault)
    finally:
        ev.Observer=original_factory;ev.replay=original_replay
    b,bi=captures['baseline_v2']
    for alias in ('off','canonical'):
        a,ai=captures[alias]
        if not np.array_equal(a,b,equal_nan=True) or ai!=bi:
            raise AssertionError('R2 baseline reproduction failed: '+alias)
    for k,v in recorders.items():
        diag[k]['mechanism_counts']=getattr(v,'_h14_counts',None)
        diag[k]['healthy_without_fused_fraction']=(diag[k]['healthy_without_fused_s']/diag[k]['healthy_s']
                                                   if diag[k]['healthy_s'] else None)
    for internal,public in NAMES.items():
        row['runtime'][public]=row['runtime'].pop(internal)
        for scores in row['receivers'].values():scores[public]=scores.pop(internal)
    if trace_path is not None:
        with gzip.open(trace_path,'wt',encoding='utf8') as f:
            json.dump(dict(columns=['t','output_v','output_s','inner_v','inner_pv','d_before','d_after','mode',
                                   'front_status','rear_status','front_stamp','rear_stamp','h14_pair','h14_update'],
                           traces={NAMES[k]:v for k,v in step_pairs.items() if v}),f,allow_nan=False)
    return row,{NAMES[k]:v for k,v in diag.items()}


def worker(task):
    bag,role,out=task;out=Path(out);store=RoleStore(out/'access'/f'{bag}.json')
    events,refs=store.load(bag,role);meta=dict(bag=bag,group=store.records[bag]['group'],role=role)
    clean,activation=score(events,refs,trace_path=out/'traces'/f'{bag}-clean.json.gz')
    clean=dict(**meta,**clean);stress=[];fault_diag=[]
    for i,(fault,window) in enumerate(gd.fault_windows(events)):
        s,d=score(window,refs,fault,trace_path=out/'traces'/f'{bag}-fault{i}.json.gz')
        stress.append(dict(**meta,fault=fault,**s));fault_diag.append(dict(fault=fault,models=d))
    result=dict(clean=clean,stress=stress,activation=activation,fault_activation=fault_diag,access=store.access)
    save(out/'bags'/f'{bag}.json',result)
    print('CHECKPOINT',role,bag,'async updates',activation['H14_async_pairs']['async_updates'],flush=True)
    return result


def r2_decision(clean,stress):
    sums={n:v6.summary(clean,stress,n) for n in NAMES.values()}
    b,c=sums['v7_baseline'],sums['H14_async_pairs'];reasons=[];safety=[];changes={}
    for key,cap in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        x,y=b[key],c[key]
        if x is None or y is None:
            reasons.append('missing_'+key);changes[key]=None;continue
        changes[key]=dict(baseline=x,candidate=y,absolute=y-x,relative=(y/x-1) if x>0 else None)
        if y > x*(1+cap)+ (1e-12 if x==0 else 0):reasons.append('aggregate_regression:'+key)
    def gain(key):
        return (1-c[key]/b[key]) if b[key] is not None and b[key]>0 and c[key] is not None else None
    cg,fg=gain('clean_rmse'),gain('fault_rmse')
    if not ((cg is not None and cg>=.02) or (fg is not None and fg>=.05)):
        reasons.append('insufficient_gain')
    for rows,is_clean in [(clean,True),(stress,False)]:
        for row in rows:
            tag=row['bag']+('/'+str(row.get('fault')) if not is_clean else '')
            r=row['runtime']['H14_async_pairs']
            if r['causal_errors'] or r['resets']:safety.append('causality_or_reset:'+tag)
            for recv,ms in row['receivers'].items():
                a,z=ms['v7_baseline'],ms['H14_async_pairs'];label=tag+'/'+recv
                if (a['n'],a['coverage'])!=(z['n'],z['coverage']):safety.append('coverage:'+label)
                if z.get('false_stop_samples',0)>a.get('false_stop_samples',0):safety.append('false_stops:'+label)
                if not is_clean and a.get('event_rmse') is not None and a.get('recovery_s') is not None and z.get('recovery_s') is None:
                    safety.append('new_unrecovered:'+label)
                if is_clean and a['rmse'] is not None and (z['rmse'] is None or z['rmse']>a['rmse']+max(.005,.05*a['rmse'])):
                    reasons.append('per_bag_regression:'+label)
    reasons=sorted(set(reasons+safety));safety=sorted(set(safety))
    return dict(eligible=not reasons,rejection_reasons=reasons,safety_failures=safety,
                summary=sums,changes=changes,clean_gain=cg,fault_gain=fg)


def write_csv(out,clean,stress,sums):
    fields=['suite','bag','group','receiver','model','fault','start','end','n','coverage','rmse',
            'mae','bias','p95','event_rmse','recovery_s','false_stop_samples','distance_rmse']
    with (out/'per_bag.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fields);w.writeheader()
        for suite,rows in [('clean',clean),('original_fault',stress)]:
            for row in rows:
                fault=row.get('fault',{})
                for recv,ms in row['receivers'].items():
                    for name in NAMES.values():
                        m=ms[name]
                        entry=dict(suite=suite,bag=row['bag'],group=row['group'],receiver=recv,model=name,
                                   fault=fault.get('kind'),start=fault.get('start'),end=fault.get('end'))
                        entry.update({k:m.get(k) for k in fields if k in m})
                        entry['distance_rmse']=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                        w.writerow(entry)
    with (out/'aggregate.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,['model']+list(next(iter(sums.values()))));w.writeheader()
        for name,metrics in sums.items():w.writerow(dict(model=name,**metrics))


def availability_diagnostics(out,store):
    """Separate artificial availability schedule. Source stamps never changed."""
    records=[];c,r,ops=profile()
    for bag in store.plan['splits']['development']:
        events,_=store.load(bag,'development')
        # Virtual baseline availability envelope >= every source stamp in input
        # order. NOT a reconstruction of original ROS wall-clock arrivals.
        avail=np.maximum.accumulate(events[:,0])+np.where(events[:,1]==2,.05,0.)
        order=np.argsort(avail,kind='stable');entry=dict(bag=bag,models={})
        for name,cls in [('v7_baseline',Pristine),('H14_async_pairs',AsyncAdaptationObserver)]:
            o=cls(c,readout=r);tl=Timeline(o,rate_hz=20,delay_s=0.);n=causal=0;times=[]
            for i in order:
                ts,ch,v=events[i];arrival=float(avail[i]);tl.ingest(int(ch),Sample(float(ts),float(v)))
                for e,held in tl.advance(now=arrival):
                    n+=1;times.append(e.t)
                    causal+=sum(s is not None and s.t>e.t+1e-9 for s in held)
            entry['models'][name]=dict(outputs=n,causal_errors=causal,resets=tl.resets,
                counts=getattr(o,'_h14_counts',None),schedule_sha256=__import__('hashlib').sha256(np.asarray(times).tobytes()).hexdigest())
        a,b=entry['models'].values();assert a['schedule_sha256']==b['schedule_sha256']
        assert a['causal_errors']==b['causal_errors']==0
        records.append(entry)
    save(out/'availability_diagnostic.json',dict(definition='separate artificial availability envelope + rear 0.05s; original source timestamps; not natural accuracy',records=records))


def cost_child(events,name,connection):
    c,r,ops=profile();cls=Pristine if name=='baseline' else AsyncAdaptationObserver
    warm=float(events[:,0].min())+10.;old=ev.Observer;info={'step_cpu_s':0.,'measured_ticks':0};start=[None,None]
    def factory(c):
        o=cls(c,readout=r);orig=o.step
        def step(t,*args):
            active=t>=warm
            if active and start[0] is None:start[:]=[time.perf_counter(),time.process_time()]
            began=time.process_time()
            e=orig(t,*args)
            if active:info['step_cpu_s']+=time.process_time()-began;info['measured_ticks']+=1
            return e
        o.step=step;return o
    try:
        ev.Observer=factory;a,rt=ev.replay(events,c,ops)
        info.update(model=name,replay_wall_s=time.perf_counter()-start[0],
                    replay_cpu_s=time.process_time()-start[1],outputs=len(a),
                    peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                    runtime=rt)
        connection.send(info)
    finally:ev.Observer=old;connection.close()


def benchmark(out,store):
    import multiprocessing as mp
    bag=sorted(store.plan['splits']['development'])[0];events,_=store.load(bag,'development')
    events=events[events[:,0]<=events[:,0].min()+190.];records=[];ctx=mp.get_context('fork')
    for pair,order in enumerate([('baseline','candidate'),('candidate','baseline')]*3):
        for name in order:
            receive,send=ctx.Pipe(False);p=ctx.Process(target=cost_child,args=(events,name,send));p.start();send.close()
            item=receive.recv();p.join();assert p.exitcode==0;item['pair']=pair;item['order']=list(order);records.append(item)
    save(out/'cost.json',dict(bag=bag,warmup_s=10.,measurement_limit_s=180.,
        scope='offline replay incl Timeline/collection; wrapped step CPU separately; child process peak RSS; NOT installed ROS latency',records=records))


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['development','validation'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--freeze',type=Path);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    out=a.output
    for sub in ('access','bags','traces'):(out/sub).mkdir()
    fingerprints=manifest();cfg,r,ops=profile()
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    provenance=dict(round='R2-v7-fixed',hypothesis='H14',baseline_sha=BASE,source_sha=source,
        source_sha256=fingerprints,config=asdict(cfg),readout=asdict(r),ops=ops,role=a.stage,
        python=platform.python_version(),numpy=np.__version__,test_evaluated=False,
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(out/'started.json',provenance)
    store=RoleStore(out/'access/supplementary.json')
    if a.stage=='validation':
        if a.freeze is None:raise PermissionError('Separate committed freeze required')
        freeze=json.loads(a.freeze.read_text())
        if freeze['source_sha256']!=fingerprints or not freeze['development_admitted']:
            raise PermissionError('Frozen candidate changed or development failed')
        rel=str(a.freeze.resolve().relative_to(ROOT))
        subprocess.run(['git','ls-files','--error-unmatch',rel],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        if subprocess.check_output(['git','diff','HEAD','--',rel],cwd=ROOT):raise PermissionError('Uncommitted freeze')
    else:
        train=sorted(store.plan['splits']['train'])[0];events,refs=store.load(train,'train')
        events=events[events[:,0]<=180.]
        row,diag=score(events,refs)
        save(out/'train.json',dict(bag=train,limit_s=180.,events=len(events),reference_used=False,
                                 purpose='execution only; no parameter fitting',result=row,diagnostics=diag))
    begin=time.perf_counter()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        result=list(pool.map(worker,[(b,a.stage,str(out)) for b in store.plan['splits'][a.stage]]))
    clean=[x['clean'] for x in result];stress=[s for x in result for s in x['stress']]
    decision=r2_decision(clean,stress)
    activations=[dict(bag=x['clean']['bag'],group=x['clean']['group'],**x['activation']['H14_async_pairs']) for x in result]
    groups=sorted({x['group'] for x in activations if x['async_updates']>0})
    coverage=dict(async_pairs=sum(x['async_pair_rows'] for x in activations),
        async_updates=sum(x['async_updates'] for x in activations),groups_with_updates=groups,
        healthy_without_fused_s=sum(x['healthy_without_fused_s'] for x in activations),
        healthy_s=sum(x['healthy_s'] for x in activations),per_bag=activations)
    coverage['adequate']=(coverage['async_pairs']>=100 and coverage['async_updates']>=50 and
                         len(groups)>=2 and coverage['healthy_without_fused_s']>=5)
    decision['coverage']=coverage
    if decision['safety_failures']:
        verdict='REJECTED'
    elif not coverage['adequate']:
        verdict='INCONCLUSIVE'
    else:verdict='CONFIRMED' if decision['eligible'] and a.stage=='validation' else 'AWAITING_FREEZE' if decision['eligible'] else 'REJECTED'
    decision.update(verdict=verdict,validation_evaluated=a.stage=='validation',test_evaluated=False,
                    merge_ready=False,stage=a.stage)
    save(out/'results.json',dict(provenance=provenance,clean=clean,stress=stress,
        activation=activations,baseline_reproduction=dict(pristine_vs_hook_and_off='exact all outputs and runtime',bags=len(clean),faults=len(stress)),
        elapsed_s=time.perf_counter()-begin))
    save(out/'decision.json',decision);write_csv(out,clean,stress,decision['summary'])
    save(out/'access.json',dict(test_evaluated=False,access=store.access+[e for x in result for e in x['access']]))
    if a.stage=='development':
        benchmark(out,store);availability_diagnostics(out,store)
        save(out/'access.json',dict(test_evaluated=False,access=store.access+[e for x in result for e in x['access']]))
    print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()

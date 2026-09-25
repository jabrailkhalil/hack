"""H19 fixed-budget research. Metrics/evaluator stay byte-identical to fixed v7.

No final/test stage. Validation requires a separately published passing freeze.
All output directories are append-only (new directories, never overwritten).
"""
import argparse
from collections import defaultdict
from dataclasses import asdict
import csv
import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
from factory import (ROOT,BASE,PLAN_COMMIT,NOTE_COMMIT,Factory,Config,Recorded,ev,
                     COLUMNS,MODES,STATUSES,digest)
from data import Store
np,ex = ev.np,ev.ex
spec = importlib.util.spec_from_file_location('h19_original_summary',ROOT/'tools/research_v6/compare.py')
v6 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v6)
OPS = dict(rate_hz=20.,alignment_delay_s=0.)
NAMES = ('baseline_v7','h03','h06')
ALIASES = {'baseline_v2':'baseline_v7','balanced_physics':'h03','h06':'h06'}

def save(path,data): ev.save(path,data)
def array_hash(a): return digest(np.ascontiguousarray(a,dtype='<f8').tobytes())

def prediction(factory, events, name, *, check=False, record=True, fault=None):
    cfg = Config(**factory.params['config']); captured=[]; old=ev.Observer
    def construct(config):
        item=Recorded(factory.make('baseline' if name=='baseline_v7' else name,config),
                      factory,check=check,record=record)
        captured.append(item); return item
    ev.Observer=construct
    try: a,info=ev.replay(events,cfg,OPS,fault)
    finally: ev.Observer=old
    return a,info,captured[0]

def measured(factory, events, refs, fault=None, *, check=True):
    configs = {k:Config(**factory.params['config']) for k in ALIASES}
    configs_by_id = {id(v):ALIASES[k] for k,v in configs.items()}; captured={}; old=ev.Observer
    def construct(config):
        name=configs_by_id[id(config)]
        item=Recorded(factory.make('baseline' if name=='baseline_v7' else name,config),
                      factory,check=check and name=='baseline_v7')
        captured[name]=item; return item
    ev.Observer=construct
    try: row=ev.score(events,refs,configs,OPS,fault)
    finally: ev.Observer=old
    for oldname,newname in ALIASES.items():
        if oldname != newname:
            row['runtime'][newname]=row['runtime'].pop(oldname)
            for receiver in row['receivers'].values(): receiver[newname]=receiver.pop(oldname)
    traces={n:np.asarray(captured[n].rows,float).reshape(-1,len(COLUMNS)) for n in NAMES}
    # Stronger exact grid test in addition to score's legacy atol check.
    t=traces['baseline_v7'][:,0]
    for name,a in traces.items():
        if not np.array_equal(t,a[:,0]): raise AssertionError('Exact output timestamps differ')
        if not np.all(np.isfinite(a)): raise AssertionError('Nonfinite runtime trace')
        target_masks={}
        for receiver,reference in refs.items():
            target=ex.match(reference,t); mask=np.isfinite(target)
            if fault: mask &= (t>=fault['start'])&(t<fault['end']+10)
            m=row['receivers'][receiver][name]
            m['slow_stop_samples']=int(np.sum(mask&(target>=.07)&(target<=.5)&(a[:,6]==MODES.index('STOPPED'))))
            target_masks[receiver]=digest(mask.tobytes()+np.nan_to_num(target).tobytes())
        row.setdefault('reference_mask_sha256',{})[name]=target_masks
    row['input_sha256']=array_hash(events)
    row['trace_sha256']={k:array_hash(v) for k,v in traces.items()}
    row['baseline_off_pristine_checked_ticks']=captured['baseline_v7'].checked_ticks
    row['detector']={n:diagnose(a,fault) for n,a in traces.items()}
    return row,traces

def diagnose(a,fault=None):
    if not len(a): return dict(outputs=0,weighted_updates=0,weighted_ticks=0,alarm_onsets=0)
    applied=a[:,7:9]==STATUSES.index('SEQUENTIAL_DOWNWEIGHTED')
    active=np.any(applied,axis=1); latched=np.any(a[:,13:15]>0,axis=1)
    info=dict(outputs=len(a),duration_s=float(a[-1,0]-a[0,0]),
              weighted_updates=int(applied.sum()),weighted_ticks=int(active.sum()),
              alarm_onsets=int(np.sum(latched & np.r_[True,~latched[:-1]])),
              max_cusum_s=float(a[:,9:13].max()),max_speed_delta_from_inner=float(np.max(abs(a[:,1]-a[:,23]))))
    if fault:
        event=(a[:,0]>=fault['start'])&(a[:,0]<fault['end'])
        before=a[:,0]<fault['start']; after=a[:,0]>=fault['end']
        info['phase_weighted_ticks']={k:int(np.sum(active&m)) for k,m in [('before',before),('event',event),('after',after)]}
        for phase,mask in [('before',before),('event',event),('after',after)]:
            info.setdefault('phase_disturbance_mean',{})[phase]=float(np.mean(a[mask,3])) if np.any(mask) else None
        if 'channel' in fault:
            i=fault['channel']-1
            hit=np.flatnonzero(event&applied[:,i])
            info.update(detection_delay_s=float(a[hit[0],0]-fault['start']) if len(hit) else None,
                        wrong_channel_updates=int(np.sum(applied[event,1-i])),
                        correct_channel_updates=int(np.sum(applied[event,i])))
    return info

def cases(events):
    g=ex.grid_channels(events)
    if g is None:return []
    t,u,f,r,valid=g
    indices=np.flatnonzero(valid&((f+r)/2>2.)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25.))
    if not len(indices):return []
    anchor=float(t[indices[0]])
    return [dict(kind=k,start=anchor,end=anchor+d) for k,d in [('bias',5.),('dropout',5.),('dropout',10.),('lock',3.)]]

def special_cases(original):
    if not original:return []
    anchor=original[0]['start']
    return [dict(kind=kind,start=anchor,end=anchor+8.,channel=channel,sign=sign,
                 amplitude=.4 if kind=='h19_drift' else .2)
            for kind in ('h19_drift','h19_intermittent') for channel in (1,2) for sign in (-1,1)]

def inject(events,fault):
    a=events.copy(); t=a[:,0]; elapsed=t-fault['start']
    mask=(a[:,1]==fault['channel'])&(t>=fault['start'])&(t<fault['end'])
    if fault['kind']=='h19_drift':offset=fault['amplitude']*np.clip(elapsed/4.,0.,1.)
    else:offset=fault['amplitude']*(np.remainder(elapsed,.5)<.25)
    a[mask,2]+=fault['sign']*offset[mask]
    return a

def window(events,fault):
    return events[(events[:,0]>=fault['start']-20)&(events[:,0]<=fault['end']+10.1)]

def change(a,b):
    if a is None or b is None:return None
    if b==0:return None
    return a/b-1

def exceeds(a,b,limit):
    if b is None:return a is not None  # preserve missingness
    if a is None:return True
    return a>b*(1+limit) if b else a>0

def decisions(clean,original,diagnostic):
    summaries={n:v6.summary(clean,original,n) for n in NAMES}
    base=summaries['baseline_v7']; verdicts={}
    for n in NAMES[1:]:
        s=summaries[n]; reasons=[]; safety=[]
        gain_clean=1-s['clean_rmse']/base['clean_rmse'] if base['clean_rmse'] else 0.
        gain_fault=1-s['fault_rmse']/base['fault_rmse'] if base['fault_rmse'] else 0.
        if gain_clean<.02 and gain_fault<.05:reasons.append('insufficient_original_gain')
        for metric in ('clean_rmse','fault_rmse','pooled_rmse'):
            if exceeds(s[metric],base[metric],.005):reasons.append('aggregate_regression:'+metric)
        if exceeds(s['distance_rmse'],base['distance_rmse'],.01):reasons.append('distance_regression')
        for row in clean:
            for receiver,scores in row['receivers'].items():
                a,b=scores[n],scores['baseline_v7']
                if b['rmse'] is not None and (a['rmse'] is None or a['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                    reasons.append('clean_per_bag:'+row['bag']+'/'+receiver)
        for row in clean+original+diagnostic:
            runtime=row['runtime'][n]
            if runtime['causal_errors'] or runtime['resets']:safety.append('causality_or_resets:'+row['id'])
            for receiver,scores in row['receivers'].items():
                a,b=scores[n],scores['baseline_v7']
                if a['n']!=b['n'] or a['coverage']!=b['coverage']:safety.append('coverage:'+row['id']+'/'+receiver)
                for key in ('false_stop_samples','slow_stop_samples'):
                    if a.get(key,0)>b.get(key,0):safety.append(key+':'+row['id']+'/'+receiver)
                if b.get('event_rmse') is not None and b.get('recovery_s') is not None and a.get('recovery_s') is None:
                    safety.append('new_unrecovered:'+row['id']+'/'+receiver)
        group_duty=defaultdict(lambda:[0,0]); weighted=0; alarm=0; seconds=0
        for row in clean:
            d=row['detector'][n]; weighted+=d['weighted_ticks']; alarm+=d['alarm_onsets']; seconds+=d['duration_s']
            g=group_duty[row['group']]; g[0]+=d['weighted_ticks']; g[1]+=d['outputs']
        duty=weighted/max(1,sum(x[1] for x in group_duty.values())); rate=alarm/max(seconds/60,1e-9)
        if duty>.005:safety.append('clean_alarm_duty_global')
        if rate>2:safety.append('clean_alarm_onsets_global')
        for g,(a,b) in group_duty.items():
            if a/max(1,b)>.01:safety.append('clean_alarm_duty_group:'+g)
        detections=0; wrong=0
        for row in diagnostic:
            d=row['detector'][n]; detections+=d['detection_delay_s'] is not None; wrong+=d['wrong_channel_updates']
            if d['wrong_channel_updates']:safety.append('wrong_channel:'+row['id'])
        activated=[r for r in clean+original+diagnostic if r['detector'][n]['weighted_updates']>0]
        updates=sum(r['detector'][n]['weighted_updates'] for r in activated)
        groups=len({r['group'] for r in activated})
        coverage=updates>=100 and groups>=3 and detections>=10
        passed=not reasons and not safety and coverage
        verdicts[n]=dict(summary=s,clean_gain=gain_clean,fault_gain=gain_fault,
            changes={k:dict(absolute=s[k]-base[k],relative=change(s[k],base[k])) for k in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse')},
            rejection_reasons=sorted(set(reasons)),safety_reasons=sorted(set(safety)),coverage_passed=coverage,
            activation=dict(weighted_updates=updates,groups=groups,diagnostic_detections=detections,wrong_channel_updates=wrong),
            clean_alarm_proxy=dict(duty=duty,onsets_per_min=rate,group_duty={g:a/max(1,b) for g,(a,b) in group_duty.items()}),
            development_passed=passed,verdict='ELIGIBLE_FOR_FREEZE' if passed else ('REJECTED' if updates and (reasons or safety) else 'INCONCLUSIVE'))
    eligible=[n for n,v in verdicts.items() if v['development_passed']]
    selected=min(eligible,key=lambda n:(summaries[n]['fault_rmse'],summaries[n]['clean_rmse'],-(.6 if n=='h06' else .3))) if eligible else None
    return dict(baseline=base,candidates=verdicts,selected=selected,validation_opened=False,test_opened=False,
                diagnostic_summary={n:v6.summary([],diagnostic,n) for n in NAMES},
                verdict='DEVELOPMENT_ONLY' if selected else ('REJECTED' if any(v['verdict']=='REJECTED' for v in verdicts.values()) else 'INCONCLUSIVE'))

def export_csv(out,rows):
    fields=['bag','group','suite','case','receiver','algorithm','n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples','slow_stop_samples','distance_rmse']
    with (out/'per_bag_receiver_case.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for row in rows:
            for receiver,scores in row['receivers'].items():
                for n in NAMES:
                    m=scores[n]; r=dict(bag=row['bag'],group=row['group'],suite=row['suite'],case=row['id'],receiver=receiver,algorithm=n)
                    r.update({k:m.get(k) for k in fields if k in m});r['distance_rmse']=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m');w.writerow(r)


def development(args,factory,store):
    out=args.output; clean=[]; original=[]; diagnostic=[]; tick_count=0
    (out/'traces').mkdir(); (out/'bags').mkdir()
    for bag in store.plan['splits']['development']:
        events,refs=store.load(bag,'development'); group=store.records[bag]['group']; rows=[]
        def run_case(source,fault,suite,index,check=False):
            nonlocal tick_count
            row,traces=measured(factory,source,refs,fault,check=check)
            ident=f'{bag}-{suite}-{index}'
            row.update(bag=bag,group=group,suite=suite,id=ident,fault=fault)
            tick_count+=row['baseline_off_pristine_checked_ticks']
            np.savez_compressed(out/'traces'/(ident+'.npz'),**traces)
            rows.append(row)
            return row,traces
        row,_=run_case(events,None,'clean',0,True); clean.append(row)
        faults=cases(events)
        for i,fault in enumerate(faults):
            row,_=run_case(window(events,fault),fault,'original',i,True);original.append(row)
        specials=special_cases(faults)
        if specials:
            source=window(events,specials[0])
            twin,traces_twin=run_case(source,None,'diagnostic_clean_twin',0)
            for i,fault in enumerate(specials):
                row,traces=run_case(inject(source,fault),fault,'diagnostic',i)
                for n,a in traces.items():
                    b=traces_twin[n]
                    if not np.array_equal(a[:,0],b[:,0]):raise AssertionError('Clean twin grid')
                    event=(a[:,0]>=fault['start'])&(a[:,0]<fault['end'])
                    delta=a[event,3]-b[event,3]
                    row['detector'][n]['disturbance_clean_twin_rmse']=float(np.sqrt(np.mean(delta*delta))) if len(delta) else None
                    row['detector'][n]['disturbance_clean_twin_bias']=float(np.mean(delta)) if len(delta) else None
                diagnostic.append(row)
        save(out/'bags'/(bag+'.json'),rows)
        print(json.dumps(dict(bag=bag,clean_rmse={n:v6.summary([clean[-1]],[],n)['clean_rmse'] for n in NAMES},
                              original_cases=len(faults),special_cases=len(specials)),ensure_ascii=False),flush=True)
    data=dict(clean=clean,original=original,diagnostic=diagnostic,baseline_off_pristine_checked_ticks=tick_count)
    save(out/'results.json',data);export_csv(out,clean+original+diagnostic)
    decision=decisions(clean,original,diagnostic);decision.update(bags=len(clean),groups=len({r['group'] for r in clean}),
       original_cases=len(original),diagnostic_cases=len(diagnostic),source_stage='development',results_sha256=digest((out/'results.json').read_bytes()))
    save(out/'decision.json',decision); print(json.dumps(decision,ensure_ascii=False),flush=True)


def train(args,factory,store):
    rows=[]
    for bag in store.plan['splits']['train']:
        events,refs=store.load(bag,'train')
        assert all(not r for r in refs.values()),'Train GNSS must be empty'
        events=events[events[:,0]<=events[:,0].min()+180.]
        info={}
        for name in NAMES:
            a,r,record=prediction(factory,events,name,check=name=='baseline_v7',record=False)
            info[name]=dict(runtime=r,outputs=len(a),output_sha256=array_hash(a),checked_ticks=record.checked_ticks)
        rows.append(dict(bag=bag,group=store.records[bag]['group'],events=len(events),info=info));print('TRAIN',bag,flush=True)
    save(args.output/'train.json',dict(bags=rows,train_gnss_opened=False,test_opened=False))


def benchmark(args,factory,store):
    bag=store.plan['splits']['development'][0];events,_=store.load(bag,'development')
    events=events[events[:,0]<=events[:,0].min()+180.]
    warm=events[events[:,0]<=events[:,0].min()+10.]
    rows=[]
    for candidate in ('h03','h06'):
        for n in ('baseline_v7',candidate):prediction(factory,warm,n,record=False)
        for pair in range(3):
            for order in (['baseline_v7',candidate],[candidate,'baseline_v7']):
                for n in order:
                    cpu=time.process_time(); wall=time.perf_counter()
                    a,r,_=prediction(factory,events,n,record=False)
                    rows.append(dict(algorithm=n,paired_candidate=candidate,pair=pair,order='/'.join(order),
                                replay_cpu_s=time.process_time()-cpu,replay_wall_s=time.perf_counter()-wall,
                                outputs=len(a),output_sha256=array_hash(a)))
    # Time step-only CPU on the SAME causal held input sequence, with identical collection.
    from reserve_odometry.timeline import Timeline
    from reserve_odometry.core import Sample
    seq=[]; tl=Timeline(factory.make('baseline'),rate_hz=20,delay_s=0)
    for t,ch,v in events:
        tl.ingest(int(ch),Sample(float(t),float(v)))
        for e,held in tl.advance():seq.append((e.t,*held))
    steps=[]
    for candidate in ('h03','h06'):
        for pair in range(3):
            for order in (['baseline_v7',candidate],[candidate,'baseline_v7']):
                for n in order:
                    obs=factory.make('baseline' if n=='baseline_v7' else n)
                    cutoff=seq[0][0]+10
                    j=0
                    while j<len(seq) and seq[j][0]<cutoff:obs.step(*seq[j]);j+=1
                    cpu=time.process_time(); outputs=[obs.step(*sample) for sample in seq[j:]];elapsed=time.process_time()-cpu
                    steps.append(dict(algorithm=n,paired_candidate=candidate,pair=pair,order='/'.join(order),step_cpu_s=elapsed,outputs=len(outputs)))
    save(args.output/'benchmark.json',dict(bag=bag,source_seconds=180,warmup_s=10,replay=rows,step=steps,
        rss_process_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        platform=platform.platform(),threads=dict(OPENBLAS=os.environ.get('OPENBLAS_NUM_THREADS'),OMP=os.environ.get('OMP_NUM_THREADS')),
        installed_ros_latency_measured=False,warning='Whole benchmark process RSS, not ROS node RSS; CPU/wall are not transport latency.'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('train','development','benchmark','validation'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--export',type=Path)
    parser.add_argument('--freeze',type=Path)
    args=parser.parse_args()
    if args.stage=='validation':
        # No candidate is authorized without a separate implementation/freeze commit.
        # Prevent speculative validation or falling back to an old freeze.
        raise PermissionError('H19 validation is locked: no approved candidate/freeze implementation in this development revision')
    args.output.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter();factory=Factory()
    save(args.output/'started.json',dict(baseline=BASE,plan_commit=PLAN_COMMIT,implementation_note_commit=NOTE_COMMIT,
         source_commit=os.environ.get('GITHUB_SHA',subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),
         stage=args.stage,command=sys.argv,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
         python=platform.python_version(),numpy=np.__version__,profile=factory.params,source_sha256=factory.hashes,
         candidate_core_sha256=digest(factory.patched_core),trace_columns=COLUMNS,modes=MODES,statuses=STATUSES,
         aliases=ALIASES,validation_opened=False,test_opened=False))
    (args.output/'candidate_core.py').write_bytes(factory.patched_core)
    store=Store(args.export,journal=args.output/'access.json')
    {'train':train,'development':development,'benchmark':benchmark}[args.stage](args,factory,store)
    save(args.output/'finished.json',dict(elapsed_wall_s=time.perf_counter()-started,
         access_count=len(store.access),validation_opened=False,test_opened=False,completed=True))

if __name__=='__main__':main()

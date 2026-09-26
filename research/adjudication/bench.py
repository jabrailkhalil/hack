"""Frozen estimator comparison, no parameter search and no final-test access.

All five colleague estimators are executed without tuning, using their published OurObserver port. Source is checked by Git blob ID. The primary
experiment deliberately gives all methods identical causal alignment/ticks;
it is not a benchmark of the peer's native receipt-clock ROS adapter.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, platform, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OURS = Path(os.environ.get('TRAM_OURS', str(ROOT/'ours')))
PEER_PORT = Path(os.environ.get('TRAM_PEER_PORT', str(ROOT/'peer/tools/tram_port')))
DATA = Path(os.environ.get('TRAM_DATA', str(OURS/'dataset/data')))
sys.path[:0] = [str(PEER_PORT), str(PEER_PORT/'vendor/ours'), str(OURS/'tools/finalization'), str(OURS/'src/reserve_odometry')]
import numpy as np
import evaluate as ev
from reserve_odometry.core import Config, Sample
from reserve_odometry.timeline import Timeline
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from ports import OurObserver

OUR_COMMIT = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
PEER_COMMITS = {'A':'98accff0d97b2ff69a2307e30841d2dec788c1d3','B':'46a81edf2a02ea170af5bde818746aea808e728a','C':'84342ac394f0de4e3f79e42e1b3a6526ebb6608a','D':'13c86f38e18d23ae964b23b0ee2ef63cca4a799a','H1_10':'b33d8b42262a5aabe0fdc22ac7b65b54d507798e','H2_050':'f76e4d729801a479b036a18a1bbe69cf47877e84'}
NAMES = ('ours_v8','A','B','C','H1_10','H2_050','mean','front','rear')
PROFILE = json.loads((OURS/'src/reserve_odometry/config/champion_v8.json').read_text())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def verify_sources():
    for path, expected in json.loads((ROOT/'source_hashes.json').read_text()).items():
        if hashlib.sha256((OURS/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Pinned runtime/evaluator changed: '+path)
    for path, expected in json.loads((ROOT/'peer_source_hashes.json').read_text()).items():
        raw=(PEER_PORT/path).read_bytes()
        got=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if got!=expected:raise ValueError('Imported peer code/model changed: '+path)


def raw_fault(events, fault):
    if fault is None: return events
    a=events.copy(); inside=(a[:,0]>=fault['start'])&(a[:,0]<fault['end'])
    wheels=(a[:,1]==1)|(a[:,1]==2)
    if fault['kind']=='dropout': return a[~(inside&wheels)]
    if fault['kind']=='lock': a[inside&wheels,2]=0.
    elif fault['kind']=='bias': a[inside&(a[:,1]==1),2]+=5.
    elif fault['kind']=='common_bias': a[inside&wheels,2]+=fault['offset']
    elif fault['kind']=='slow_common':
        m=inside&wheels
        a[m,2]+=fault['height']*np.clip((a[m,0]-fault['start'])/(fault['ramp_end']-fault['start']),0,1)
    return a


def replay_all(events, fault=None):
    inputs=raw_fault(events,fault)
    timeline=Timeline(GuardedReadoutObserver(Config(**PROFILE['config']),readout=ReadoutConfig(**PROFILE['readout'])),rate_hz=20.,delay_s=0.)
    peers={name:OurObserver(name,Config(**PROFILE['config'])) for name in NAMES if name!='ours_v8'}
    outputs={n:[] for n in NAMES};counts={n:Counter() for n in NAMES}
    all_ticks=0;early={n:0 for n in NAMES};violation=0;errors={};valid={n:0 for n in NAMES}
    for t,ch,value in inputs:
        timeline.ingest(int(ch),Sample(float(t),float(value)))
        for e,held in timeline.advance():
            all_ticks+=1
            violation+=sum(x is not None and x.t>e.t+1e-9 for x in held)
            other={}
            for name,peer in peers.items():
                if name in errors:continue
                try:
                    p=peer.step(e.t,*held)
                    if p.mode!='WAITING_FOR_INITIALIZATION' and not all(math.isfinite(x) for x in (p.v,p.s)):
                        raise ValueError('Nonfinite prediction')
                    other[name]=p
                except Exception as exc:
                    errors[name]=dict(kind=type(exc).__name__,message=str(exc),t=e.t)
            valid['ours_v8']+=e.mode!='WAITING_FOR_INITIALIZATION'
            for name,p in other.items():valid[name]+=p.mode!='WAITING_FOR_INITIALIZATION'
            if e.mode=='WAITING_FOR_INITIALIZATION':
                for name,p in other.items():early[name]+=p.mode!='WAITING_FOR_INITIALIZATION'
                continue
            outputs['ours_v8'].append((e.t,e.v,e.s,int(e.mode=='STOPPED')))
            counts['ours_v8'][e.mode]+=1
            for name in peers:
                p=other.get(name);available=p is not None and p.mode!='WAITING_FOR_INITIALIZATION'
                outputs[name].append((e.t,p.v if available else np.nan,p.s if available else np.nan,int(available and p.mode=='STOPPED')))
                counts[name][p.mode if p else 'EXCEPTION']+=1
    arrays={name:np.asarray(a,float).reshape(-1,4) for name,a in outputs.items()}
    return arrays,dict(grid_ticks=all_ticks,scored_grid_ticks=len(arrays['ours_v8']),
         available_ticks=valid,peer_available_before_our_initialization=early,
         causal_errors=int(violation),dropped=timeline.dropped,resets=timeline.resets,
         exceptions=errors,states={n:dict(v) for n,v in counts.items()},
         prediction_hashes={n:hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest() for n,a in arrays.items()})


def score(events, refs, fault=None):
    arrays, info=replay_all(events,fault)
    t=arrays['ours_v8'][:,0];common=np.isfinite(arrays['ours_v8'][:,1])
    result={}
    for receiver,ref in refs.items():
        target=ev.ex.match(ref,t); mask=common & np.isfinite(target)
        if fault: mask &= (t>=fault['start']) & (t<fault['end']+10.)
        scores={}
        for name,a in arrays.items():
            m=ev.ex.metrics(t,a[:,1],target,mask)
            m['false_STOPPED_samples']=int(np.sum(mask & (target>1.) & (a[:,3]>0)))
            m['available_on_v8_grid']=int(np.sum(mask & np.isfinite(a[:,1])))
            m['false_zero_samples']=int(np.sum(mask & (target>1.) & (np.abs(a[:,1])<=.07)))
            if fault:
                em=ev.ex.metrics(t,a[:,1],target,mask & (t<fault['end']))
                m['event_rmse']=em['rmse'];m['event_n']=em['n']
                good=mask & (t>=fault['end']) & (np.abs(a[:,1]-target)<.25)
                runs=np.convolve(good.astype(int),np.ones(20,int),mode='valid') if len(t)>=20 else np.array([])
                hits=np.flatnonzero(runs==20)
                m['recovery_s']=float(t[hits[0]]-fault['end']) if len(hits) and em['n'] else None
            else:
                reference=np.where(mask,target,np.nan)
                m['distance']=ev.distance_surrogate(a,reference)
            scores[name]=m
        result[receiver]=scores
    return dict(outputs=len(t),receivers=result,runtime=info)


def worker(args):
    bag, out=args
    store=ev.ex.Store(DATA)
    events,refs=store.load(bag,'validation')
    metadata=dict(bag=bag,group=store.records[bag]['group'],role='validation')
    clean=dict(**metadata,**score(events,refs))
    # Frozen vehicle-only anchors; do not search for favorable failure times.
    prior=json.loads((ROOT/'scenarios.json').read_text())[bag]
    cases=[]
    for suite in ('stress','abrupt','slow'):
        for f in prior[suite]:
            window=events[(events[:,0]>=f['start']-20.)&(events[:,0]<=f['end']+10.1)]
            label=(f['kind']+'_'+str(round(f['end']-f['start'],3)))
            cases.append(dict(**metadata,suite=suite,label=label,fault=f,**score(window,refs,f)))
    result=dict(clean=clean,cases=cases,access=store.access)
    save(out/'bags'/(bag+'.json'),result)
    print(bag,'clean',clean['outputs'],'faults',len(cases),flush=True)
    return result


def summary(rows,event=False):
    result={}
    for name in NAMES:
        groups=defaultdict(list);distances=defaultdict(list);se=0.;n=0;bias=0.;mae=0.;missing=[];zero=0;stops=0;unrecovered=0;recoveries=[]
        for row in rows:
            for receiver,models in row['receivers'].items():
                m=models[name];r=m.get('event_rmse') if event else m['rmse'];count=m.get('event_n',0) if event else m['n']
                if r is None:
                    missing.append(row['bag']+'/'+receiver); continue
                groups[row['group']].append(r);se+=r*r*count;n+=count
                if not event: bias+=m.get('bias',0.)*count;mae+=m.get('mae',0.)*count
                d=m.get('distance',{}).get('reanchored_span_rmse_m')
                if d is not None: distances[row['group']].append(d)
                zero+=m['false_zero_samples'];stops+=m['false_STOPPED_samples']
                if event:
                    if m.get('recovery_s') is None: unrecovered+=1
                    else: recoveries.append(m['recovery_s'])
        result[name]=dict(group_macro_rmse=float(np.mean([np.mean(v) for v in groups.values()])) if groups else None,
                          pooled_rmse=math.sqrt(se/n) if n else None,samples=n,groups=len(groups),
                          distance_macro_m=float(np.mean([np.mean(v) for v in distances.values()])) if distances else None,
                          pooled_bias=bias/n if n and not event else None,pooled_mae=mae/n if n and not event else None,
                          false_zero_samples=zero,false_STOPPED_samples=stops,unrecovered=unrecovered if event else None,
                          mean_recovery_s=float(np.mean(recoveries)) if recoveries else None,
                          missing_bag_receivers=sorted(set(missing)))
    return result


def decision(report,clean,cases):
    result={};base=report['clean']['ours_v8'];bf=report['fault_suites']['stress']['ours_v8']
    for name in NAMES[1:]:
        c=report['clean'][name];f=report['fault_suites']['stress'][name];reasons=[]
        if any(name in r['runtime']['exceptions'] for r in clean+cases):reasons.append('runtime exception')
        if any(r['runtime']['available_ticks'][name]<r['runtime']['available_ticks']['ours_v8'] for r in clean+cases):reasons.append('output coverage loss')
        for key,limit in (('group_macro_rmse',1.005),('pooled_rmse',1.005),('distance_macro_m',1.01)):
            if c[key] is None or c[key]>base[key]*limit:reasons.append(key+' regression')
        if f['group_macro_rmse'] is None or f['group_macro_rmse']>bf['group_macro_rmse']*1.005:reasons.append('original fault regression')
        if c['false_STOPPED_samples']>base['false_STOPPED_samples'] or f['false_STOPPED_samples']>bf['false_STOPPED_samples']:reasons.append('more false stops')
        if f['unrecovered']>bf['unrecovered']:reasons.append('more unrecovered original faults')
        if c['samples']<base['samples'] or f['samples']<bf['samples']:reasons.append('matched coverage loss')
        per_pair=[]
        for row in clean:
            for recv,ms in row['receivers'].items():
                br=ms['ours_v8']['rmse'];cr=ms[name]['rmse']
                if br is not None and (cr is None or cr-br>max(.005,.05*br)):
                    per_pair.append(row['bag']+'/'+recv)
        if per_pair:reasons.append('per-bag clean regression')
        cg=1-c['group_macro_rmse']/base['group_macro_rmse'] if c['group_macro_rmse'] is not None else None
        fg=1-f['group_macro_rmse']/bf['group_macro_rmse'] if f['group_macro_rmse'] is not None else None
        if not((cg is not None and cg>=.02) or (fg is not None and fg>=.05)):reasons.append('insufficient primary gain')
        result[name]=dict(eligible=not reasons,reasons=reasons,clean_gain=cg,original_fault_gain=fg,per_bag_regressions=per_pair)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    args=p.parse_args();verify_sources();args.output.mkdir(parents=True,exist_ok=False)
    store=ev.ex.Store(DATA); started=time.perf_counter()
    plan=dict(our_commit=OUR_COMMIT,peer_commits=PEER_COMMITS,peer_source_hashes=json.loads((ROOT/'peer_source_hashes.json').read_text()),
              protocol='identical source-time alignment and inputs; estimator comparison only, NOT native ROS timing',
              configs=dict(ours=PROFILE,peer=json.loads((PEER_PORT/'vendor/ours/research/model.json').read_text())),
              validation_bags=store.plan['splits']['validation'],final_test_opened=False,source_files_sha256=json.loads((ROOT/'source_hashes.json').read_text()),runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scenarios_sha256=hashlib.sha256((ROOT/'scenarios.json').read_bytes()).hexdigest(),
              python=platform.python_version(),numpy=np.__version__)
    save(args.output/'started.json',plan)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows=list(pool.map(worker,[(b,args.output) for b in plan['validation_bags']]))
    clean=[r['clean'] for r in rows];cases=[c for r in rows for c in r['cases']]
    report=dict(plan=plan,clean=summary(clean),fault_suites={s:summary([c for c in cases if c['suite']==s],True) for s in ('stress','abrupt','slow')},
                fault_types={s:summary([c for c in cases if c['label']==s],True) for s in sorted({c['label'] for c in cases})},
                clean_bags=len(clean),fault_cases=len(cases),elapsed_s=time.perf_counter()-started,
                causal_errors=sum(r['runtime']['causal_errors'] for r in clean+cases),
                peer_common_clean_finite_counts_identical=len({v['samples'] for v in summary(clean).values()})==1)
    actual=report['clean']['ours_v8']['group_macro_rmse']
    report['candidate_gates']=decision(report,clean,cases)
    report['baseline_reproduction']=dict(expected=0.1145498613174081,actual=actual,max_error=abs(actual-0.1145498613174081))
    if not math.isclose(actual,0.1145498613174081,abs_tol=1e-12,rel_tol=1e-12):
        raise AssertionError('Our baseline failed reproduction; do not claim comparison validity')
    # Store aggregate plus all independent per-bag files, without the private peer source.
    save(args.output/'summary.json',report);save(args.output/'access.json',[a for r in rows for a in r['access']])
    records=[]
    for r in clean+cases:
        for receiver,scores in r['receivers'].items():
            for name,m in scores.items():
                records.append(dict(bag=r['bag'],group=r['group'],suite=r.get('suite','clean'),scenario=r.get('label','clean'),receiver=receiver,model=name,
                                    n=m['n'],rmse=m['rmse'],event_rmse=m.get('event_rmse'),event_n=m.get('event_n'),mae=m.get('mae'),bias=m.get('bias'),p95=m.get('p95'),coverage=m['coverage'],
                                    false_zero=m['false_zero_samples'],false_STOPPED=m['false_STOPPED_samples'],recovery_s=m.get('recovery_s'),distance_rmse=m.get('distance',{}).get('reanchored_span_rmse_m')))
    with (args.output/'per_bag.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    print(json.dumps({k:v for k,v in report.items() if k not in ('plan','fault_types')},indent=2))

if __name__=='__main__': main()

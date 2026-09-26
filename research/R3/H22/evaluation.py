"""Fixed selected calibration on genuine development; scorer is untouched."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
from functools import partial
import numpy as np
import data as d

h11=d.module_at('h22_h11_suites','tools/research_h11/compare.py')
FACTORY=partial(d.GuardedReadoutObserver,readout=d.ReadoutConfig(1.,.5))
ALIASES={'baseline_v2':'main','balanced_physics':'candidate'}


def low_windows(events):
    """Exact PR13 low_speed.py construction, applied only to development."""
    grid=d.ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    ix=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2)
        & (u>=0) & (t>max(25.,.1*t[-1])) & (t<t[-1]-25.))
    if len(ix):
        anchor=float(t[ix[0]])
        for duration in (3.,5.):
            yield dict(kind='lock',start=anchor,end=anchor+duration),events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


def paired(events,refs,theta,fault=None):
    captured={};traces={};previous_factory=d.ev.Observer;original=d.ev.replay
    class Traced(d.GuardedReadoutObserver):
        def __init__(self,c):
            super().__init__(c,readout=d.ReadoutConfig(1.,.5));self._h22_trace=[]
        def step(self,t,*held):
            e=super().step(t,*held)
            # Offline collector only; no estimator decision uses fault metadata.
            if fault is not None:
                self._h22_trace.append([e.t,e.v,e.s,self.v,self.drive_a,self.disturbance,e.mode,e.front_status,e.rear_status])
            return e
    active=[]
    def factory(c):
        o=Traced(c);active.append(o);return o
    def replay(ev,cfg,ops,fault_arg=None):
        a,info=original(ev,cfg,ops,fault_arg)
        name='main' if not captured else 'candidate'
        captured[name]=a;traces[name]=active[-1]._h22_trace
        return a,info
    try:
        d.ev.Observer=factory;d.ev.replay=replay
        row=d.ev.score(events,refs,{'baseline_v2':d.base_config(),'balanced_physics':d.config_for(theta)},d.OPS,fault)
    finally:d.ev.Observer=previous_factory;d.ev.replay=original
    for mapping in [row['runtime']]+list(row['receivers'].values()):
        for old,new in ALIASES.items():mapping[new]=mapping.pop(old)
    a,b=captured['main'],captured['candidate']
    if a.shape!=b.shape or not np.array_equal(a[:,0],b[:,0]):raise AssertionError('Output schedule changed')
    row['identity']=dict(schedule_exact=True,
        timestamp_sha256=hashlib.sha256(a[:,0].tobytes()).hexdigest(),
        changed_outputs=int(np.sum(abs(a[:,1]-b[:,1])>1e-6)),outputs=len(a))
    return row,captured,traces


def assert_baseline(events,refs,row,fault=None,common=None):
    models={'main':(FACTORY,d.base_config())}
    expected=(h11.compare_common(events,refs,models,common) if common is not None
              else d.gc.compare(events,refs,models,fault))
    assert row['runtime']['main']==expected['runtime']['main']
    for receiver,scores in expected['receivers'].items():
        assert row['receivers'][receiver]['main']==scores['main'],('baseline_metric_mismatch',receiver)
    assert row['outputs']==expected['outputs']


def save_traces(path,traces,fault):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wt',newline='') as f:
        w=csv.writer(f);w.writerow(['model','stage','t','published_v','published_s','inner_v','drive_a','disturbance','mode','front_status','rear_status'])
        for name,rows in traces.items():
            for row in rows:
                t=row[0];stage='before' if t<fault['start'] else 'during' if t<fault['end'] else 'after'
                w.writerow([name,stage]+row)


def gains(summary):
    result={}
    for key in ['macro_rmse','fault_macro','pooled_rmse','distance_macro']:
        a,b=summary['main'][key],summary['candidate'][key]
        result[key]=dict(baseline=a,candidate=b,absolute=None if a is None or b is None else b-a,
            relative=None if a is None or b is None or a==0 else b/a-1.)
    return result


def gate(clean,stress,low,common,summary,selection):
    reasons=list(selection['check_veto']);missing=[]
    delta=gains(summary);gain_clean=None;gain_fault=None
    for key,limit in [('macro_rmse',.005),('fault_macro',.005),('pooled_rmse',.005),('distance_macro',.01)]:
        a,b=summary['main'][key],summary['candidate'][key]
        if a is None or b is None or not math.isfinite(a+b):missing.append(key);continue
        if b>a*(1+limit)+1e-12:reasons.append('aggregate_regression:'+key)
    if not missing:
        gain_clean=1-summary['candidate']['macro_rmse']/summary['main']['macro_rmse'] if summary['main']['macro_rmse']>0 else 0.
        gain_fault=1-summary['candidate']['fault_macro']/summary['main']['fault_macro'] if summary['main']['fault_macro']>0 else 0.
        if gain_clean<.02 and gain_fault<.05:reasons.append('insufficient_gain')
    for label,rows in [('clean',clean),('original',stress),('low_speed',low),('common_mode',common)]:
        for row in rows:
            context=label+':'+row['bag']+':'+str(row.get('fault'))
            if row['runtime']['candidate']['causal_errors'] or row['runtime']['candidate']['resets']:
                reasons.append('causal_or_reset:'+context)
            for receiver,scores in row['receivers'].items():
                a,b=scores['main'],scores['candidate'];tag=context+'/'+receiver
                if a['n']!=b['n'] or a['coverage']!=b['coverage']:reasons.append('coverage:'+tag)
                if b.get('false_stop_samples',0)>a.get('false_stop_samples',0):reasons.append('false_stops:'+tag)
                if label=='clean' and a['rmse'] is not None:
                    if b['rmse'] is None or b['rmse']>a['rmse']+max(.005,.05*a['rmse']):reasons.append('per_bag_clean:'+tag)
                if label!='clean' and a.get('event_rmse') is not None and a.get('recovery_s') is not None and b.get('recovery_s') is None:
                    reasons.append('new_individual_unrecovered:'+tag)
    suites={}
    for label,rows in [('low_speed',low),('common_mode',common)]:
        suites[label]=h11.common_summary(rows)
        a,b=suites[label]['main']['event_macro_rmse'],suites[label]['candidate']['event_macro_rmse']
        if a is None or b is None:missing.append(label+'_reference')
        elif b>a*1.005+1e-12:reasons.append('supplemental_regression:'+label)
    changed=sum(r['identity']['changed_outputs'] for r in clean)
    groups=sorted({r['group'] for r in clean if r['identity']['changed_outputs']})
    enough=changed>=1000 and len(groups)>=3
    verdict='INCONCLUSIVE' if missing or not enough else 'REJECTED' if reasons else 'ACCURACY_PASSED_DEVELOPMENT'
    return dict(scientific_verdict=verdict,mechanism_status='ACTIVE' if changed else 'INACTIVE',
        coverage_status='SUFFICIENT' if enough and not missing else 'INSUFFICIENT',
        accuracy_contract_passed=not reasons and enough and not missing,runtime_verified=False,ready_to_merge=False,
        changed_outputs=changed,changed_groups=groups,clean_gain=gain_clean,fault_gain=gain_fault,
        rejection_reasons=sorted(set(reasons)),missing_evidence=missing,delta=delta,supplemental=suites,
        validation_opened=False,validation_authorized=not reasons and enough and not missing,
        enabled_ros='NOT_RUN_AFTER_REJECTION' if verdict=='REJECTED' else 'NOT_RUN',test_evaluated=False)


def compact_tables(clean,stress,low,common,out):
    fields=['suite','bag','group','receiver','fault','start','duration','model','n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples','distance_rmse']
    with (out/'per_bag.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for label,rows in [('clean',clean),('original',stress),('low_speed',low),('common_mode',common)]:
            for row in rows:
                fault=row.get('fault',{});start=fault.get('start');end=fault.get('end')
                for receiver,scores in row['receivers'].items():
                    for name in ['main','candidate']:
                        m=scores[name]
                        record={k:m.get(k) for k in fields if k in m}
                        record.update(suite=label,bag=row['bag'],group=row['group'],receiver=receiver,
                            fault=fault.get('kind',''),start=start,duration=end-start if start is not None else None,model=name,
                            distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m'))
                        writer.writerow(record)
    groups=[]
    for label,rows in [('clean',clean),('original',stress),('low_speed',low),('common_mode',common)]:
        for group in sorted({r['group'] for r in rows}):
            subset=[r for r in rows if r['group']==group]
            for name in ['main','candidate']:
                keys=['rmse','mae','bias','p95','distance'] if label=='clean' else ['event_rmse','rmse','mae','bias','recovery_s']
                groups.append(dict(suite=label,group=group,model=name,**{k:d.v6.macro(subset,name,k) for k in keys}))
    d.save(out/'per_group.json',groups)


def run(output,training):
    out=d.new_dir(output);started=d.provenance('development');d.save(out/'started.json',started)
    selection=json.loads((training/'selection.json').read_text())
    for p,h in selection['source_sha256'].items():
        if d.sha(d.ROOT/p)!=h:raise ValueError('Source changed since train selection: '+p)
    chosen=selection['selected']
    if chosen is None:raise PermissionError('No finite selected fit')
    artifact=training/(chosen+'.json')
    assert d.sha(artifact)==selection['candidate_sha256']
    model=json.loads(artifact.read_text());theta=np.asarray(model['theta'])
    assert model['config']==d.asdict(d.config_for(theta))
    clean=[];stress=[];low=[];common=[];store=d.Store(out/'access.json');before=time.perf_counter()
    for bag in store.plan['splits']['development']:
        events,refs=store.load(bag,'development');meta=dict(bag=bag,group=store.records[bag]['group'])
        row,arrays,_=paired(events,refs,theta);assert_baseline(events,refs,row);clean.append(dict(**meta,**row))
        for label,source,target in [('original',d.gc.fault_windows(events),stress),('low_speed',low_windows(events),low),('common_mode',h11.common_fault_windows(events),common)]:
            for index,(fault,window) in enumerate(source):
                input_events=h11.inject_common(window,fault) if label=='common_mode' else window
                row,_,traces=paired(input_events,refs,theta,fault)
                if label=='common_mode':assert_baseline(window,refs,row,common=fault)
                target.append(dict(**meta,fault=fault,**row))
                save_traces(out/'traces'/f'{bag}-{label}-{index}.csv.gz',traces,fault)
        d.save(out/'progress.json',dict(completed_bags=len(clean),last_bag=bag,test_evaluated=False))
        print('DEVELOPMENT',bag,'changed',clean[-1]['identity']['changed_outputs'],flush=True)
    summary=d.gc.aggregate(clean,stress);decision=gate(clean,stress,low,common,summary,selection)
    compact_tables(clean,stress,low,common,out)
    d.save(out/'results.json',dict(started=started,selection=selection,summary=summary,decision=decision,
        clean=clean,stress=stress,low_speed=low,common_mode=common,elapsed_s=time.perf_counter()-before,test_evaluated=False))
    d.save(out/'SUMMARY.json',dict(baseline=d.BASE,candidate_source=started['source_ref'],selected=chosen,
        summary=summary,**decision))
    with (out/'aggregate.csv').open('w',newline='') as f:
        cols=['model','macro_rmse','pooled_rmse','distance_macro','fault_macro','n','false_stops','fault_false_stops','fault_missing_recovery','mean_recovery_s']
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for name,m in summary.items():w.writerow(dict(model=name,**{k:m[k] for k in cols if k!='model'}))
    print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--training',type=Path,required=True)
    a=p.parse_args();run(a.output,a.training)

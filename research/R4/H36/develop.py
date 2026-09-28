"""H36 frozen-configuration development; unchanged scorers, no validation CLI."""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import importlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import time

from model import *
from foundation import integrity

guarded = module('h36_guarded_metrics', ROOT/'tools/research_guarded/compare.py')
h11 = module('h36_h11_metrics', ROOT/'tools/research_h11/compare.py')
v6 = module('h36_v6_metrics', ROOT/'tools/research_v6/compare.py')
NAMES = ('main', 'candidate', 'control')
OPS = dict(rate_hz=20., alignment_delay_s=0.)
PHASES = {'traction': 1, 'coast': 0, 'braking': -1, 'stale': 2}
MODES = {s:i for i,s in enumerate(('WAITING_FOR_INITIALIZATION','INITIALIZED','MODEL_ONLY',
                                  'FUSED','SINGLE_WHEEL','REACQUIRING','STOPPED'))}
STATUS = {s:i for i,s in enumerate(('MISSING_OR_STALE','RANGE','DUPLICATE_OR_OLD',
          'RATE_ANOMALY','CANDIDATE','MODEL_DISAGREEMENT','AMBIGUOUS_PAIR','ACCEPTED',
          'REACQUIRE_ACCEPTED','ZERO_LOCK_SUSPECT','COMMON_MODE_QUARANTINE'))}


class DevelopmentStore(ev.ex.Store):
    def load(self, bag, purpose):
        if purpose != 'development' or self.records[bag]['split'] != 'development' or bag not in self.plan['splits']['development']:
            raise PermissionError('H36 permits only the original development role here')
        r=self.records[bag];path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=r['sha256']:raise ValueError('DB checksum mismatch: '+bag)
        allowed=list(ev.ex.CHANNELS)+list(ev.ex.REFS)
        self.access.append(dict(bag=bag,purpose=purpose,topics=allowed,sha256=r['sha256']))
        events=[];refs={'master':[],'rover':[]};origin=r['sensor_start_ns']
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


class Trace:
    """External, equal offline collector; not part of the runtime state."""
    def __init__(self, observer):self.o=observer;self.rows=[]
    def __getattr__(self, name):return getattr(self.o,name)
    def reset(self, **kw):self.o.reset(**kw)
    def step(self,t,command=None,front=None,rear=None):
        e=self.o.step(t,command,front,rear)
        if e.mode!='WAITING_FOR_INITIALIZATION':
            u=0. if e.command_stale else command.value
            phase=2 if e.command_stale else 1 if u>.04 else -1 if u<-.04 else 0
            self.rows.append((e.t,e.v,e.s,phase,self.o.v,self.o.drive_a,e.disturbance,
                              MODES[e.mode],STATUS[e.front_status],STATUS[e.rear_status],
                              e.variance_v,e.variance_s))
        return e
    def array(self):return np.asarray(self.rows,float).reshape(-1,12)


def model_set(configs, traces):
    ms={};readout=profile()[1]
    for name in NAMES:
        def create(c, name=name):
            tr=Trace(GuardedReadoutObserver(c,readout=readout));traces[name]=tr;return tr
        ms[name]=(create,Config(**configs[name]))
    return ms


def scored(events,refs,configs,fault=None,common=False,direct_check=False):
    traces={};ms=model_set(configs,traces)
    out=h11.compare_common(events,refs,ms,fault) if common else guarded.compare(events,refs,ms,fault)
    arrays={n:t.array() for n,t in traces.items()};base=arrays['main']
    for n,a in arrays.items():
        assert a.shape==base.shape and np.array_equal(a[:,0],base[:,0]),('schedule',n)
    if direct_check:
        original=ev.Observer
        try:
            ev.Observer=lambda c:GuardedReadoutObserver(c,readout=profile()[1])
            direct,counters=ev.replay(events,Config(**configs['main']),OPS,fault)
        finally:ev.Observer=original
        assert np.array_equal(direct[:,:3],base[:,:3]) and counters==out['runtime']['main']
        # Separate exact profile / feature-off factory, not merely an array alias.
        try:
            ev.Observer=lambda c:factory(configs['candidate'].get('unused'),enabled=False)
            off,offc=ev.replay(events,Config(**configs['main']),OPS,fault)
        finally:ev.Observer=original
        assert np.array_equal(off,direct,equal_nan=True) and offc==counters
        out['direct_baseline_and_feature_off_equal']=True
    return out,arrays


def low_speed_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    indices=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2)
        & (u>=0) & (t>max(25.,.1*t[-1])) & (t<t[-1]-25.))
    if len(indices):
        anchor=float(t[indices[0]])
        for duration in (3.,5.):
            fault=dict(kind='lock',start=anchor,end=anchor+duration)
            yield fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


def phase_metrics(arrays,refs,meta):
    rows=[];t=arrays['main'][:,0]
    for phase in ('traction','coast','braking'):
        receivers={}
        for receiver,values in refs.items():
            target=ev.ex.match(values,t);mask=np.isfinite(target)&(arrays['main'][:,3]==PHASES[phase])
            receivers[receiver]={n:ev.ex.metrics(t,a[:,1],target,mask) for n,a in arrays.items()}
        rows.append(dict(**meta,phase=phase,receivers=receivers))
    return rows


def full_distance(events,refs,configs,fault):
    traces={};ms=model_set(configs,traces);runtime={}
    for name,m in ms.items():
        _,runtime[name]=guarded.predict(events,m,fault)
    arrays={n:tr.array() for n,tr in traces.items()};t=arrays['main'][:,0]
    for n,a in arrays.items():assert np.array_equal(a[:,0],t),('full schedule',n)
    receivers={}
    for receiver,values in refs.items():
        target=ev.ex.match(values,t)
        receivers[receiver]={n:ev.distance_surrogate(a,target) for n,a in arrays.items()}
    delta={}
    for n in ('candidate','control'):
        d=arrays[n][:,2]-arrays['main'][:,2];after=t>=fault['end']+10
        delta[n]=dict(terminal_delta_s_m=float(d[-1]) if len(d) else None,
                      delta_s_at_end_plus_10_m=float(d[np.flatnonzero(after)[0]]) if after.any() else None,
                      max_abs_delta_s_after_end_plus_10_m=float(np.max(abs(d[after]))) if after.any() else None)
    return dict(receivers=receivers,runtime=runtime,delta_s=delta),arrays


def worker(args):
    bag,data_root,configs,output=args;store=DevelopmentStore(data_root)
    events,refs=store.load(bag,'development');meta=dict(bag=bag,group=store.records[bag]['group'],role='development')
    out,arrays=scored(events,refs,configs,direct_check=True)
    clean=dict(**meta,**out);phases=phase_metrics(arrays,refs,meta)
    activation={n:int(np.sum(abs(arrays[n][:,1]-arrays['main'][:,1])>1e-8)) for n in ('candidate','control')}
    if bag=='30618_0652866c':np.savez_compressed(output/'traces'/f'{bag}-clean.npz',**arrays)
    original=[];low=[];common=[];full=[]
    for i,(fault,window) in enumerate(guarded.fault_windows(events)):
        out,a=scored(window,refs,configs,fault);original.append(dict(**meta,fault=fault,**out))
        fd,fa=full_distance(events,refs,configs,fault);full.append(dict(**meta,fault=fault,**fd))
        if bag=='30618_0652866c' and i==2:
            np.savez_compressed(output/'traces'/f'{bag}-dropout10-cropped.npz',**a)
            np.savez_compressed(output/'traces'/f'{bag}-dropout10-full.npz',**fa)
    for fault,window in low_speed_windows(events):
        out,_=scored(window,refs,configs,fault);low.append(dict(**meta,fault=fault,**out))
    for fault,window in h11.common_fault_windows(events):
        out,_=scored(window,refs,configs,fault,common=True);common.append(dict(**meta,**out))
    result=dict(clean=clean,original=original,low=low,common=common,full=full,
                phases=phases,activation=activation,access=store.access)
    save(output/'bags'/(bag+'.json'),result)
    print('DEVELOPMENT_CHECKPOINT',bag,'original',len(original),'low',len(low),'common',len(common),flush=True)
    return result


def supplemental_summary(rows,name):
    recovery=[s[name]['recovery_s'] for r in rows for s in r['receivers'].values() if s[name].get('recovery_s') is not None]
    return dict(event_rmse=v6.macro(rows,name,'event_rmse'),mae=v6.macro(rows,name,'mae'),
        p95=v6.macro(rows,name,'p95'),signed_bias=v6.macro(rows,name,'bias'),
        false_stops=v6.total(rows,name,'false_stop_samples'),unrecovered=v6.unrecovered(rows,name),
        mean_recovery_s=float(np.mean(recovery)) if recovery else None,
        reacquiring_ticks=sum(r['runtime'][name]['mode_counts'].get('REACQUIRING',0) for r in rows),
        groups={g:v6.macro([r for r in rows if r['group']==g],name,'event_rmse') for g in sorted({r['group'] for r in rows})})


def decide(result,train):
    summaries=result['summary'];b=summaries['main'];decisions={}
    for name in ('candidate','control'):
        c=summaries[name];reasons=[]
        cg=1-c['clean_rmse']/b['clean_rmse'];fg=1-c['fault_rmse']/b['fault_rmse']
        if cg<.02 and fg<.05:reasons.append('insufficient_gain')
        for key,limit in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
            if c[key]>b[key]*(1+limit):reasons.append('aggregate_regression:'+key)
        for suite in ('clean','original','low','common'):
            for row in result[suite]:
                if row['runtime'][name]['causal_errors'] or row['runtime'][name]['resets']:reasons.append('causality_or_reset:'+suite)
                for receiver,scores in row['receivers'].items():
                    x,y=scores[name],scores['main'];case=suite+':'+row['bag']+'/'+receiver+':'+str(row.get('fault'))
                    if x['n']!=y['n'] or x['coverage']!=y['coverage']:reasons.append('coverage:'+case)
                    if x['false_stop_samples']>y['false_stop_samples']:reasons.append('false_stops:'+case)
                    if suite=='clean' and y['rmse'] is not None and (x['rmse'] is None or x['rmse']>y['rmse']+max(.005,.05*y['rmse'])):
                        reasons.append('per_bag_clean:'+case)
                    if suite!='clean' and y['event_rmse'] is not None and y['recovery_s'] is not None and x['recovery_s'] is None:
                        reasons.append('new_individual_unrecovered:'+case)
        for suite in ('low','common'):
            x,y=result['supplemental'][suite][name],result['supplemental'][suite]['main']
            if x['event_rmse'] is None or y['event_rmse'] is None:reasons.append('missing_reference:'+suite)
            elif x['event_rmse']>y['event_rmse']*1.005:reasons.append('supplemental_regression:'+suite)
            if suite=='common' and x['reacquiring_ticks']>y['reacquiring_ticks']:reasons.append('new_common_reacquisition')
        act=result['activation'][name]
        if act['changed_ticks']<100 or len(act['changed_groups'])<3:reasons.append('activation_insufficient')
        if name=='candidate':reasons+=train['prerequisite_failures']
        decisions[name]=dict(clean_gain=cg,original_fault_gain=fg,selectable=name=='candidate',
            eligible=not reasons and name=='candidate',rejection_reasons=sorted(set(reasons)))
    return decisions


def tables(output,result):
    import csv
    rows=[];regressions=[]
    for suite in ('clean','original','low','common'):
        for row in result[suite]:
            for receiver,scores in row['receivers'].items():
                for name,m in scores.items():
                    scalar={k:v for k,v in m.items() if not isinstance(v,(dict,list))}
                    distance=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')
                    rows.append(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,
                                     fault=json.dumps(row.get('fault')),model=name,distance_rmse_m=distance,**scalar))
                for name in ('candidate','control'):
                    for key in ('rmse','event_rmse','mae','p95','bias','recovery_s'):
                        a,b=scores[name].get(key),scores['main'].get(key)
                        if a is not None and b is not None and a>b:
                            regressions.append(dict(suite=suite,bag=row['bag'],group=row['group'],receiver=receiver,
                                fault=json.dumps(row.get('fault')),model=name,metric=key,baseline=b,candidate=a,absolute=a-b,
                                relative=a/b-1 if b!=0 else None))
    for filename,data in [('per_bag_receiver_fault.csv',rows),('positive_deltas.csv',regressions)]:
        fields=list(dict.fromkeys(k for r in data for k in r))
        with (output/filename).open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)


def run(data_root,train_path,output,workers):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);(output/'traces').mkdir()
    train=json.loads(Path(train_path).read_text());configs={'main':train['models']['baseline']['config'],
        'candidate':train['models']['profiled']['config'],'control':train['models']['control_no_nuisance']['config']}
    assert configs['main']==asdict(configuration())
    for name in ('candidate','control'):
        assert set(k for k in configs[name] if configs[name][k]!=configs['main'][k])<=set(FIELDS)
    save(output/'started.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        baseline=BASE,tree=TREE,plan_commit=PLAN_SHA,role='development',train_sha256=sha(train_path),
        configs=configs,readout=asdict(profile()[1]),operational=OPS,
        actual_class=GuardedReadoutObserver.__module__+'.'+GuardedReadoutObserver.__name__,
        actual_module_file=importlib.import_module(GuardedReadoutObserver.__module__).__file__,
        source_ref=os.environ.get('H36_SOURCE_SHA','local-uncommitted'),
        code_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
        integrity=integrity(),python=platform.python_version(),numpy=np.__version__,
        prerequisite_passed=train['prerequisite_passed'],diagnostic_only=not train['prerequisite_passed'],
        validation_opened=False,test_opened=False))
    start=time.perf_counter();store=DevelopmentStore(data_root)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        items=list(pool.map(worker,[(b,data_root,configs,output) for b in store.plan['splits']['development']]))
    result={k:[item['clean'] for item in items] if k=='clean' else [r for item in items for r in item[k]]
            for k in ('clean','original','low','common','full','phases')}
    result['summary']={n:v6.summary(result['clean'],result['original'],n) for n in NAMES}
    result['supplemental']={s:{n:supplemental_summary(result[s],n) for n in NAMES} for s in ('original','low','common')}
    for n in NAMES:
        result['summary'][n].update(clean_mae=v6.macro(result['clean'],n,'mae'),
            clean_p95=v6.macro(result['clean'],n,'p95'),clean_signed_bias=v6.macro(result['clean'],n,'bias'))
    expected=dict(clean_rmse=.09266814298282507,fault_rmse=.2375486120563008,
                  pooled_rmse=.1293056944774334,distance_rmse=5.310295004801444,samples=394221)
    deltas={k:result['summary']['main'][k]-v for k,v in expected.items()}
    if any(abs(x)>1e-10 for x in deltas.values()):
        save(output/'BASELINE_MISMATCH.json',deltas);raise AssertionError(('baseline fingerprint',deltas))
    result['baseline_reproduction']=dict(passed=True,fingerprint_deltas=deltas,
         independent_clean_replays=len(items),feature_off_replays=len(items))
    result['activation']={n:dict(changed_ticks=sum(i['activation'][n] for i in items),
        changed_groups=sorted({i['clean']['group'] for i in items if i['activation'][n]>0})) for n in ('candidate','control')}
    result['decisions']=decide(result,train);result['elapsed_s']=time.perf_counter()-start
    result['validation_opened']=False;result['test_opened']=False
    result['scientific_verdict']='CONFIRMED_DEVELOPMENT_ONLY' if result['decisions']['candidate']['eligible'] else 'REJECTED'
    save(output/'access.json',[a for i in items for a in i['access']]);save(output/'results.json',result)
    save(output/'decision.json',{k:result[k] for k in ('summary','supplemental','activation','decisions','scientific_verdict','baseline_reproduction')})
    save(output/'traces/schema.json',dict(columns=['t','published_v','published_s','phase','inner_v','drive_a','disturbance',
          'mode','front_status','rear_status','variance_v','variance_s'],mode=MODES,status=STATUS,phase=PHASES))
    tables(output,result)
    print(json.dumps(dict(summary=result['summary'],decisions=result['decisions']),indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--train',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=2);args=p.parse_args()
    if not 1<=args.workers<=8:raise ValueError('workers 1..8')
    run(args.data_root,args.train,args.output,args.workers)

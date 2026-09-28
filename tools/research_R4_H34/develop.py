"""H34 development only: immutable official scorers, fixed A/B attribution.

No fitting, validation or final-test entry point. Large per-tick traces are not
committed. A is a diagnostic refit control; only B can be selected.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import csv
import datetime
import gzip
import importlib.util
import json
import math
from pathlib import Path
import platform
import sqlite3
import sys
import time
from common import ROOT,D,BASE,ev,np,profile,integrity,save,sha,make,norm,Config


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

# Use only the existing functions, not their historical model constructors.
guarded=load('h34_original_guarded',ROOT/'tools/research_guarded/compare.py')
h11=load('h34_original_h11',ROOT/'tools/research_h11/compare.py')
v6=load('h34_original_macro',ROOT/'tools/research_v6/compare.py')
NAMES=('main','A','B','B0','off')


class DevelopmentStore(ev.ex.Store):
    def load(self,bag,purpose):
        if purpose!='development' or self.records[bag]['split']!='development' or bag not in self.plan['splits']['development']:
            raise PermissionError('H34 permits development only in this loader')
        row=self.records[bag];path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=row['sha256']:raise ValueError('Bag checksum mismatch: '+bag)
        allowed=list(ev.ex.CHANNELS)+list(ev.ex.REFS)
        self.access.append(dict(bag=bag,purpose=purpose,topics=allowed,sha256=row['sha256']))
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


class CheckedOff:
    """Offline comparison wrapper, not runtime state or cost accounting."""
    def __init__(self):self.o=make('A');self.reference=make('baseline')
    def __getattr__(self,k):return getattr(self.o,k)
    def reset(self,**kwargs):self.o.reset(**kwargs);self.reference.reset(**kwargs)
    def step(self,*args,**kwargs):
        a=self.o.step(*args,**kwargs);b=self.reference.step(*args,**kwargs)
        if norm(a)!=norm(b):raise AssertionError('off Estimate parity')
        for k,v in vars(self.reference).items():
            if norm(getattr(self.o,k))!=norm(v):raise AssertionError('off state parity: '+k)
        return a


def instance(name,fitted):
    if name=='main':return make('baseline')
    if name=='off':return CheckedOff()
    return make('B' if name=='B0' else name,None if name=='B0' else fitted[name]['theta'])


class Trace:
    """Same offline collector for every method; no reference reaches observer."""
    def __init__(self,o):self.o=o;self.rows=[]
    def __getattr__(self,k):return getattr(self.o,k)
    def reset(self,**kwargs):self.o.reset(**kwargs)
    def step(self,t,command=None,front=None,rear=None):
        e=self.o.step(t,command,front,rear)
        if e.mode!='WAITING_FOR_INITIALIZATION':
            u=0. if e.command_stale else max(-1.,min(1.,command.value))
            phase=0 if e.command_stale else (1 if u>.04 else -1 if u<-.04 else 2)
            self.rows.append((e.t,e.v,e.s,phase,self.o.v,self.o.drive_a,e.disturbance,
                              u,e.mode,e.front_status,e.rear_status))
        return e


def score(events,refs,fitted,fault=None,official_check=False,common=False):
    collectors={};configs={n:instance(n,fitted).c for n in NAMES}
    def factory(cfg):
        name=next(n for n in NAMES if configs[n] is cfg)
        tr=Trace(instance(name,fitted));collectors[name]=tr;return tr
    _,_,ops=profile();old=ev.Observer
    if common:
        model_set={n:(factory,configs[n]) for n in NAMES}
        out=h11.compare_common(events,refs,model_set,fault)
    else:
        models={('baseline_v2' if n=='main' else 'balanced_physics' if n=='off' else n):c for n,c in configs.items()}
        try:ev.Observer=factory;out=ev.score(events,refs,models,ops,fault)
        finally:ev.Observer=old
        for original,new in [('baseline_v2','main'),('balanced_physics','off')]:
            out['runtime'][new]=out['runtime'].pop(original)
            for m in out['receivers'].values():m[new]=m.pop(original)
    base=np.asarray([r[:3] for r in collectors['main'].rows],float).reshape(-1,3)
    for name,tr in collectors.items():
        a=np.asarray([r[:3] for r in tr.rows],float).reshape(-1,3)
        assert a.shape==base.shape and np.array_equal(a[:,0],base[:,0]),('schedule',name)
        if name=='off':assert np.array_equal(a,base),'off outputs'
    if official_check:
        try:
            ev.Observer=lambda cfg:make('baseline')
            check=ev.score(events,refs,{'baseline_v2':configs['main'],'balanced_physics':configs['main']},ops,fault)
        finally:ev.Observer=old
        assert check['runtime']['baseline_v2']==out['runtime']['main']
        for r,m in out['receivers'].items():assert m['main']==check['receivers'][r]['baseline_v2']
        out['direct_official_baseline_reproduced']=True
    return out,collectors


def low_speed_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2) & (u>=0) & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
            yield dict(kind='lock',start=anchor,end=anchor+duration),window


def phase_scores(coll,refs,meta):
    rows=[];tr=coll['main'].rows
    if not tr:return rows
    t=np.array([r[0] for r in tr]);phase=np.array([r[3] for r in tr])
    for ph,label in ((1,'traction'),(-1,'braking'),(2,'coast')):
        receivers={}
        for receiver,values in refs.items():
            target=ev.ex.match(values,t);mask=np.isfinite(target)&(phase==ph)
            receivers[receiver]={n:ev.ex.metrics(t,np.array([r[1] for r in c.rows]),target,mask) for n,c in coll.items()}
        rows.append(dict(**meta,phase=label,receivers=receivers))
    return rows


def full_fault(events,refs,fitted,fault,clean_arrays):
    """Original fault injection, whole bag; scalar metric formulas unchanged."""
    _,_,ops=profile();arrays={};runtime={};old=ev.Observer
    for name in ('main','A','B'):
        o=instance(name,fitted)
        try:ev.Observer=lambda c:o;arrays[name],runtime[name]=ev.replay(events,o.c,ops,fault)
        finally:ev.Observer=old
    t=arrays['main'][:,0];j=int(np.searchsorted(t,fault['end']+10.,side='right')-1)
    delta={}
    for name,a in arrays.items():
        assert np.array_equal(a[:,0],t) and np.array_equal(t,clean_arrays[name][:,0])
        delta[name]=dict(at_s=float(t[j]),fault_minus_clean_s_m=float(a[j,2]-clean_arrays[name][j,2]),
                        terminal_fault_minus_clean_s_m=float(a[-1,2]-clean_arrays[name][-1,2]))
    receivers={}
    for receiver,values in refs.items():
        target=ev.ex.match(values,t);mask=np.isfinite(target);m={}
        for name,a in arrays.items():
            s=ev.ex.metrics(t,a[:,1],target,mask);s['distance_surrogate']=ev.distance_surrogate(a,target)
            s['false_stop_samples']=int(np.sum(mask&(target>1.)&(a[:,5]>0)))
            # Identical original recovery definition, but from a full-bag state.
            window_mask=mask&(t>=fault['start'])&(t<fault['end']+10.)
            s['event_rmse']=ev.ex.metrics(t,a[:,1],target,window_mask&(t<fault['end']))['rmse']
            good=window_mask&(t>=fault['end'])&(np.abs(a[:,1]-target)<.25)
            runs=np.convolve(good.astype(int),np.ones(20,int),mode='valid') if len(t)>=20 else np.array([])
            hits=np.flatnonzero(runs==20);s['recovery_s']=float(t[hits[0]]-fault['end']) if len(hits) else None
            m[name]=s
        receivers[receiver]=m
    return dict(fault=fault,receivers=receivers,runtime=runtime,outputs=len(t),residual_delta_s=delta)


def compressed(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():raise FileExistsError(p)
    with gzip.open(p,'wt',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def worker(args):
    bag,fitted,output=args;store=DevelopmentStore();events,refs=store.load(bag,'development')
    meta=dict(bag=bag,group=store.records[bag]['group'])
    raw,coll=score(events,refs,fitted,official_check=True);clean=dict(**meta,**raw)
    phases=phase_scores(coll,refs,meta);base=np.array([r[1] for r in coll['main'].rows])
    reference=any(m['main']['n']>0 for m in clean['receivers'].values())
    activation={n:dict(output_changed=int(np.sum(np.abs(np.array([r[1] for r in coll[n].rows])-base)>1e-8)),reference=reference) for n in ('A','B','B0')}
    clean_arrays={n:np.array([r[:3] for r in coll[n].rows]) for n in ('main','A','B')}
    original=[];low=[];common=[];full=[]
    del coll
    for i,(fault,window) in enumerate(guarded.fault_windows(events)):
        raw,tr=score(window,refs,fitted,fault);original.append(dict(**meta,fault=fault,**raw))
        if bag=='30618_0652866c' and i==2:
            compressed(output/'traces'/f'{bag}-original-dropout10.json.gz',dict(columns=['t','published_v','published_s','phase','inner_v','drive_a','d','command','mode','front_status','rear_status'],models={n:x.rows for n,x in tr.items() if n!='off'}))
        del tr
        full.append(dict(**meta,**full_fault(events,refs,fitted,fault,clean_arrays)))
    for fault,window in low_speed_windows(events):
        raw,_=score(window,refs,fitted,fault);low.append(dict(**meta,fault=fault,**raw))
    for fault,window in h11.common_fault_windows(events):
        raw,_=score(window,refs,fitted,fault,common=True);common.append(dict(**meta,**raw))
    result=dict(clean=clean,original=original,low_speed=low,common_mode=common,full_faulted=full,
                phases=phases,activation=dict(**meta,models=activation),access=store.access)
    compressed(output/'bags'/(bag+'.json.gz'),result)
    print('CHECKPOINT',bag,activation,flush=True);return result


def row_veto(rows,name,reference,clean=False):
    reasons=[]
    for row in rows:
        loc=row['bag']+'/'+str(row.get('fault',{}))
        run=row.get('runtime',{}).get(name,{})
        if run.get('causal_errors',0) or run.get('resets',0):reasons.append('causality_or_reset:'+loc)
        for receiver,scores in row['receivers'].items():
            a,b=scores[name],scores[reference];where=loc+'/'+receiver
            if a['n']!=b['n'] or a['coverage']!=b['coverage']:reasons.append('coverage:'+where)
            if a.get('false_stop_samples',0)>b.get('false_stop_samples',0):reasons.append('false_stops:'+where)
            if b.get('event_rmse') is not None and b.get('recovery_s') is not None and a.get('recovery_s') is None:
                reasons.append('individual_unrecovered:'+where)
            if clean and b['rmse'] is not None and (a['rmse'] is None or a['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                reasons.append('clean_per_bag:'+where)
    return reasons


def increased(a,b,ratio):return a is None or b is None or a>b*(1+ratio)+1e-12

def gate(data,summary,reference):
    a,b=summary['B'],summary[reference];reasons=[];changes={}
    for key in ('clean_rmse','fault_rmse','pooled_rmse','distance_rmse'):
        av,bv=a[key],b[key];changes[key]=dict(baseline=bv,candidate=av,absolute=None if av is None or bv is None else av-bv,relative=None if av is None or bv in (0,None) else av/bv-1)
        if increased(av,bv,.01 if key=='distance_rmse' else .005):reasons.append('aggregate_regression:'+key)
    clean_gain=None if b['clean_rmse'] in (0,None) else 1-a['clean_rmse']/b['clean_rmse']
    fault_gain=None if b['fault_rmse'] in (0,None) else 1-a['fault_rmse']/b['fault_rmse']
    if clean_gain is None or fault_gain is None or (clean_gain<.02 and fault_gain<.05):reasons.append('insufficient_gain')
    reasons+=row_veto(data['clean'],'B',reference,True)+row_veto(data['original'],'B',reference)
    extras={}
    for suite in ('low_speed','common_mode','full_faulted'):
        key='distance' if suite=='full_faulted' else 'event_rmse'
        av,bv=v6.macro(data[suite],'B',key),v6.macro(data[suite],reference,key)
        extras[suite]=dict(baseline=bv,candidate=av,relative=None if bv in (0,None) else av/bv-1)
        if increased(av,bv,.01 if suite=='full_faulted' else .005):reasons.append('supplemental_regression:'+suite)
        reasons+=row_veto(data[suite],'B',reference)
    changed=sum(r['models']['B']['output_changed'] for r in data['activation'])
    groups={r['group'] for r in data['activation'] if r['models']['B']['reference'] and r['models']['B']['output_changed']>0}
    coverage=changed>=100 and len(groups)>=3
    if not coverage:reasons.append('activation_coverage')
    return dict(reference=reference,passed=not reasons,reasons=sorted(set(reasons)),delta=changes,
                clean_gain=clean_gain,fault_gain=fault_gain,extra_suites=extras,
                coverage=dict(passed=coverage,changed_outputs=changed,reference_groups=sorted(groups)))


def decision(data):
    summary={n:v6.summary(data['clean'],data['original'],n) for n in NAMES}
    expected={'clean_rmse':.09266814298282507,'fault_rmse':.2375486120563008,'pooled_rmse':.1293056944774334,'distance_rmse':5.310295004801444,'samples':394221}
    for k,v in expected.items():assert abs(summary['main'][k]-v)<=1e-10,('baseline_fingerprint',k,summary['main'][k],v)
    official=gate(data,summary,'main');attribution=gate(data,summary,'A')
    verdict='REJECTED' if not official['passed'] else ('CONFIRMED_DEVELOPMENT_ONLY' if attribution['passed'] else 'INCONCLUSIVE')
    return dict(summary=summary,baseline_gate=official,attribution_gate=attribution,
                scientific_verdict=verdict,accuracy_contract_evaluated=True,accuracy_contract_passed=official['passed'],
                validation_admitted=official['passed'] and attribution['passed'],selected='B' if official['passed'] and attribution['passed'] else None,
                validation_opened=False,test_opened=False,enabled_runtime_verified=False,ready_to_merge=False)


def write_csv(data,path):
    with path.open('x',newline='') as f:
        w=csv.writer(f);w.writerow(['suite','bag','group','receiver','model','fault_kind','fault_start','fault_duration','phase','n','coverage','rmse_mps','mae_mps','bias_mps','p95_mps','event_rmse_mps','recovery_s','false_stop_samples','distance_rmse_m'])
        for suite in ('clean','original','low_speed','common_mode','full_faulted','phases'):
            for row in data[suite]:
                ft=row.get('fault',{})
                for receiver,scores in row['receivers'].items():
                    for name in NAMES:
                        if name not in scores:continue
                        m=scores[name]
                        w.writerow([suite,row['bag'],row['group'],receiver,name,ft.get('kind'),ft.get('start'),None if not ft else ft['end']-ft['start'],row.get('phase')]+[m.get(k) for k in ('n','coverage','rmse','mae','bias','p95','event_rmse','recovery_s','false_stop_samples')]+[m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')])


def main():
    p=argparse.ArgumentParser();p.add_argument('--fit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);checks=integrity()
    fitted={n:json.loads((args.fit/(n+'.json')).read_text()) for n in ('A','B')}
    assert all(m['success'] for m in fitted.values());assert 1<=args.workers<=4
    started=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline_sha=BASE,
                 baseline_checks=checks,source_hashes={str(f.relative_to(ROOT)):sha(f) for f in [Path(__file__),ROOT/'src/reserve_odometry/reserve_odometry/core.py',ROOT/'src/reserve_odometry/reserve_odometry/guarded_readout.py',ROOT/'src/reserve_odometry/reserve_odometry/integration_h34.py',ROOT/'tools/research_R4_H34/common.py']},
                 fit_hashes={n:sha(args.fit/(n+'.json')) for n in fitted},python=platform.python_version(),numpy=np.__version__,
                 role='development',validation_opened=False,test_opened=False,
                 classes={n:dict(class_name=type(instance(n,fitted)).__name__,module_file=sys.modules[type(instance(n,fitted)).__module__].__file__,config=asdict(instance(n,fitted).c),readout=asdict(instance(n,fitted).readout)) for n in NAMES if n!='off'})
    save(args.output/'started.json',started);store=DevelopmentStore();start=time.perf_counter()
    data={k:[] for k in ('clean','original','low_speed','common_mode','full_faulted','phases','activation','access')}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(worker,[(b,fitted,args.output) for b in store.plan['splits']['development']]):
            for k in data:
                if k in ('clean','activation'):data[k].append(result[k])
                else:data[k].extend(result[k])
    result=decision(data);save(args.output/'decision.json',result);save(args.output/'access.json',data['access'])
    write_csv(data,args.output/'per_bag.csv');compressed(args.output/'results.json.gz',dict(started=started,elapsed_s=time.perf_counter()-start,**data))
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()

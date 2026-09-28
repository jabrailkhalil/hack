"""R3-H24 immutable-score development comparison. No validation/test CLI exists."""
import argparse
from collections import defaultdict, Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sqlite3
import time
from common import ROOT, BASE, ev, np, profile, integrity, save, sha, load_module
from common import GuardedReadoutObserver, Sample, Timeline
from reserve_odometry.core import Observer
from reserve_odometry.command_map import CommandMap, CommandMapObserver

# Import original scorers and anchors, never their historic model factories/loaders.
guarded=load_module('h24_official_guarded',ROOT/'tools/research_guarded/compare.py')
h11=load_module('h24_official_h11',ROOT/'tools/research_h11/compare.py')
v6=load_module('h24_official_macro',ROOT/'tools/research_v6/compare.py')
NAMES=('main','H24_L01','H24_L1','off')
CANDIDATES=('H24_L01','H24_L1')


class DevelopmentStore(ev.ex.Store):
    def load(self,bag,purpose):
        if purpose!='development' or self.records[bag]['split']!='development' or bag not in self.plan['splits']['development']:
            raise PermissionError('R3-H24 development only: '+bag+' / '+purpose)
        r=self.records[bag];path=self.root/bag/(bag+'_0.db3')
        if sha(path)!=r['sha256']:raise ValueError('Bag checksum mismatch')
        allowed=list(ev.ex.CHANNELS)+list(ev.ex.REFS);events=[];refs={'master':[],'rover':[]};origin=r['sensor_start_ns']
        self.access.append(dict(bag=bag,purpose=purpose,topics=allowed,sha256=r['sha256']))
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


def baseline(config):
    _,r,_=profile()
    return GuardedReadoutObserver(config,readout=r)


def make(config, model):
    if model is None:return baseline(config)
    _,r,_=profile()
    return CommandMapObserver(config,readout=r,command_map=CommandMap(**model))


class CheckedOff(CommandMapObserver):
    def __init__(self,config,model):
        self.reference=baseline(config);_,r,_=profile()
        super().__init__(config,readout=r,command_map=CommandMap(**(model|{'enabled':False})))

    def reset(self,**kwargs):
        super().reset(**kwargs)
        if hasattr(self,'reference'):self.reference.reset(**kwargs)

    def step(self,*args,**kwargs):
        a=super().step(*args,**kwargs);b=self.reference.step(*args,**kwargs)
        if a!=b:raise AssertionError('off Estimate differs from canonical v8')
        for k,v in vars(self.reference).items():
            if getattr(self,k)!=v:raise AssertionError('off state differs: '+k)
        return a


class Trace:
    """Offline equal collector; never shipped in runtime or counted as runtime state."""
    def __init__(self,o):self.o=o;self.rows=[]
    def __getattr__(self,k):return getattr(self.o,k)
    def reset(self,**kw):self.o.reset(**kw)
    def step(self,t,command=None,front=None,rear=None):
        oldv=self.o.v;e=self.o.step(t,command,front,rear)
        if e.mode=='WAITING_FOR_INITIALIZATION':return e
        u=0. if e.command_stale else max(-1.,min(1.,command.value))
        delta=self.o.drive_target(u,oldv)-Observer.drive_target(self.o,u,oldv)
        phase=0 if e.command_stale else (1 if u>.04 else -1 if u<-.04 else 2)
        self.rows.append((e.t,e.v,e.s,phase,delta,self.o.v,self.o.drive_a,e.disturbance,
                          u,e.mode,e.front_status,e.rear_status,e.variance_v,e.variance_s))
        return e


def models(fitted,collectors):
    c,r,ops=profile();cfgs={};by_id={}
    for name in NAMES:
        cfg=type(c)(**asdict(c));cfgs[name]=cfg;by_id[id(cfg)]=name
    def factory(cfg):
        name=by_id[id(cfg)]
        if name=='off':o=CheckedOff(cfg,fitted[CANDIDATES[0]]['command_map'])
        else:o=make(cfg,None if name=='main' else fitted[name]['command_map'])
        wrapped=Trace(o);collectors[name]=wrapped;return wrapped
    ms={('baseline_v2' if n=='main' else 'balanced_physics' if n=='off' else n):cfgs[n] for n in NAMES}
    return cfgs,ms,factory


def score(events,refs,fitted,fault=None,official_check=False):
    collectors={};cfgs,ms,factory=models(fitted,collectors);_,_,ops=profile()
    old=ev.Observer
    try:
        ev.Observer=factory
        out=ev.score(events,refs,ms,ops,fault)
    finally:ev.Observer=old
    for original,new in [('baseline_v2','main'),('balanced_physics','off')]:
        out['runtime'][new]=out['runtime'].pop(original)
        for scores in out['receivers'].values():scores[new]=scores.pop(original)
    if official_check:
        try:
            ev.Observer=baseline
            ref=ev.score(events,refs,{'baseline_v2':cfgs['main'],'balanced_physics':cfgs['main']},ops,fault)
        finally:ev.Observer=old
        assert out['runtime']['main']==ref['runtime']['baseline_v2']
        for receiver,scores in out['receivers'].items():
            assert scores['main']==ref['receivers'][receiver]['baseline_v2'],('baseline_reproduction',receiver)
        out['baseline_reproduced_with_direct_factory']=True
    check_schedules(collectors)
    return out,collectors


def check_schedules(collectors):
    b=np.array([r[:3] for r in collectors['main'].rows],float).reshape(-1,3)
    for name,tr in collectors.items():
        a=np.array([r[:3] for r in tr.rows],float).reshape(-1,3)
        if a.shape!=b.shape or not np.array_equal(a[:,0],b[:,0]):raise AssertionError('schedule '+name)
        if name=='off' and not np.array_equal(a,b):raise AssertionError('off published trajectory')


def common_score(events,refs,fitted,fault):
    collectors={};c,_,_=profile();ms={}
    for name in NAMES:
        def factory(cfg,name=name):
            o=CheckedOff(cfg,fitted[CANDIDATES[0]]['command_map']) if name=='off' else make(cfg,None if name=='main' else fitted[name]['command_map'])
            tr=Trace(o);collectors[name]=tr;return tr
        ms[name]=(factory,type(c)(**asdict(c)))
    out=h11.compare_common(events,refs,ms,fault);check_schedules(collectors)
    return out,collectors


def low_speed_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    # Exact anchor predicate from PR13 low_speed.py (blob7705f88), identical windows.
    idx=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2) & (u>=0) & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
            yield dict(kind='lock',start=anchor,end=anchor+duration),window


def transition_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid;phase=np.where(u>.04,1,np.where(u<-.04,-1,0))
    for value,label in ((1,'traction'),(-1,'braking'),(0,'coast')):
        idx=np.flatnonzero(valid & np.r_[False,phase[1:]!=phase[:-1]] & (phase==value) & (t>25)&(t<t[-1]-25))
        if len(idx):
            anchor=float(t[idx[0]]+.5)
            fault=dict(kind='dropout',start=anchor,end=anchor+5.)
            window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+15.1)]
            yield label,fault,window


def phase_scores(collectors,refs,meta):
    rows=[];b=collectors['main'].rows
    if not b:return rows
    t=np.array([r[0] for r in b]);phase=np.array([r[3] for r in b])
    for ph,label in ((1,'traction'),(-1,'braking'),(2,'coast')):
        receivers={}
        for receiver,values in refs.items():
            target=ev.ex.match(values,t);mask=np.isfinite(target)&(phase==ph);s={}
            for name,tr in collectors.items():
                s[name]=ev.ex.metrics(t,np.array([r[1] for r in tr.rows]),target,mask)
            receivers[receiver]=s
        rows.append(dict(**meta,phase=label,receivers=receivers))
    return rows


def dump_trace(path,collectors):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wt',encoding='utf-8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['model','t','published_v','published_s','phase','target_delta',
                 'inner_v','drive_a','disturbance','command','mode','front_status','rear_status','variance_v','variance_s'])
        for name,tr in collectors.items():
            if name=='off':continue
            writer.writerows((name,*r) for r in tr.rows)


def worker(args):
    bag,fitted,output=args;store=DevelopmentStore();events,refs=store.load(bag,'development')
    meta=dict(bag=bag,group=store.records[bag]['group']);raw,coll=score(events,refs,fitted,official_check=True)
    clean=dict(**meta,**raw);phases=phase_scores(coll,refs,meta)
    b=np.array([r[1] for r in coll['main'].rows]);activation={}
    reference=any(m['main']['n']>0 for m in clean['receivers'].values())
    for name in CANDIDATES:
        tr=coll[name];activation[name]=dict(target_changed=sum(abs(r[4])>1e-8 for r in tr.rows),
            output_changed=int(np.sum(abs(np.array([r[1] for r in tr.rows])-b)>1e-8)),reference=reference)
    if bag=='30618_0652866c':dump_trace(output/'traces'/f'{bag}-clean.csv.gz',coll)
    original=[];low=[];common=[];switch=[]
    for i,(fault,window) in enumerate(guarded.fault_windows(events)):
        raw,tr=score(window,refs,fitted,fault)
        original.append(dict(**meta,fault=fault,**raw))
        if bag=='30618_0652866c' and i==2:dump_trace(output/'traces'/f'{bag}-original-dropout10.csv.gz',tr)
    for fault,window in low_speed_windows(events):
        raw,_=score(window,refs,fitted,fault);low.append(dict(**meta,fault=fault,**raw))
    for fault,window in h11.common_fault_windows(events):
        raw,_=common_score(window,refs,fitted,fault);common.append(dict(**meta,**raw))
    for label,fault,window in transition_windows(events):
        raw,tr=score(window,refs,fitted,fault);switch.append(dict(**meta,phase=label,fault=fault,**raw))
        if bag=='30618_0652866c':dump_trace(output/'traces'/f'{bag}-transition-{label}.csv.gz',tr)
    print('DEVELOP',bag,activation,flush=True)
    return dict(clean=clean,original=original,low_speed=low,common_mode=common,transition=switch,
                phases=phases,activation=dict(**meta,models=activation),access=store.access)


def metric(rows,name,key):return v6.macro(rows,name,key)


def increased(a,b,ratio):
    if a is None or b is None:return True
    return a>b*(1+ratio)+1e-12


def row_veto(rows,name,clean=False):
    reasons=[]
    for row in rows:
        loc=row['bag']+('/'+str(row.get('fault',{})) if 'fault' in row else '')
        run=row.get('runtime',{}).get(name,{})
        if run.get('causal_errors',0) or run.get('resets',0):reasons.append('causality_or_reset:'+loc)
        for receiver,scores in row['receivers'].items():
            a,b=scores[name],scores['main'];r=loc+'/'+receiver
            if a['n']!=b['n'] or a['coverage']!=b['coverage']:reasons.append('coverage:'+r)
            if a.get('false_stop_samples',0)>b.get('false_stop_samples',0):reasons.append('false_stops:'+r)
            if b.get('event_rmse') is not None and b.get('recovery_s') is not None and a.get('recovery_s') is None:
                reasons.append('individual_unrecovered:'+r)
            if clean and b['rmse'] is not None and (a['rmse'] is None or a['rmse']>b['rmse']+max(.005,.05*b['rmse'])):
                reasons.append('clean_per_bag:'+r)
    return reasons


def decide(data,fitted):
    clean=data['clean'];original=data['original'];names=NAMES
    summary={n:v6.summary(clean,original,n) for n in names}
    decision={};b=summary['main']
    for name in CANDIDATES:
        a=summary[name];reasons=[]
        def gain(key):
            x,y=a[key],b[key]
            if x is None or y is None:
                reasons.append('missing_metric:'+key);return None
            if y==0:return 0. if x<=1e-12 else -1.
            return 1-x/y
        cg=gain('clean_rmse');fg=gain('fault_rmse')
        if (cg is None or cg<.02) and (fg is None or fg<.05):reasons.append('insufficient_gain')
        for key,tol in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
            if increased(a[key],b[key],tol):reasons.append('aggregate_regression:'+key)
        for suite in ('clean','original','low_speed','common_mode','transition'):
            reasons.extend(row_veto(data[suite],name,clean=suite=='clean'))
        extras={}
        for suite in ('low_speed','common_mode'):
            ba=metric(data[suite],'main','event_rmse');ca=metric(data[suite],name,'event_rmse')
            extras[suite]=dict(baseline=ba,candidate=ca)
            if increased(ca,ba,.005):reasons.append('extra_suite_regression:'+suite)
        phase_summary={}
        for phase in ('traction','braking','coast'):
            rows=[r for r in data['phases'] if r['phase']==phase];ba=metric(rows,'main','rmse');ca=metric(rows,name,'rmse')
            groups={r['group'] for r in rows if any(s['main']['n']>0 for s in r['receivers'].values())}
            phase_summary[phase]=dict(baseline=ba,candidate=ca,reference_groups=len(groups))
            if increased(ca,ba,.005):reasons.append('side_phase_regression:'+phase)
            if len(groups)<2:reasons.append('side_phase_missing_coverage:'+phase)
        acts=data['activation'];target=sum(r['models'][name]['target_changed'] for r in acts)
        changed=sum(r['models'][name]['output_changed'] for r in acts)
        tg={r['group'] for r in acts if r['models'][name]['target_changed']>0}
        vg={r['group'] for r in acts if r['models'][name]['output_changed']>0 and r['models'][name]['reference']}
        covered=target>=100 and changed>=100 and len(tg)>=3 and len(vg)>=3
        if not covered:reasons.append('mechanism_coverage')
        if not fitted[name]['success']:reasons.append('fit_not_converged')
        decision[name]=dict(eligible=not reasons,rejection_reasons=sorted(set(reasons)),clean_gain=cg,fault_gain=fg,
                           coverage=covered,activation=dict(target_ticks=target,output_ticks=changed,target_groups=len(tg),
                           changed_reference_groups=len(vg)),phases=phase_summary,extra_suites=extras)
    eligible=[n for n in CANDIDATES if decision[n]['eligible']]
    selected=min(eligible,key=lambda n:(summary[n]['fault_rmse'],summary[n]['clean_rmse'],-fitted[n]['lambda_'])) if eligible else None
    return dict(summary=summary,candidates=decision,selected=selected,accuracy_contract_passed=bool(selected),
                scientific_verdict='DEVELOPMENT_PASS_PENDING_VALIDATION' if selected else
                    ('REJECTED' if all(d['coverage'] for d in decision.values()) else 'INCONCLUSIVE'),
                validation_evaluated=False,test_evaluated=False,ready_to_merge=False,runtime_verified=False)


def tables(output,data):
    rows=[]
    # Compact clean table only; full per-fault/raw metrics have one JSON representation.
    for suite in ('clean',):
        for r in data[suite]:
            for recv,scores in r['receivers'].items():
                for name in NAMES:
                    m=scores[name]
                    rows.append(dict(suite=suite,bag=r['bag'],group=r['group'],receiver=recv,model=name,
                         phase=r.get('phase'),fault=json.dumps(r.get('fault'),sort_keys=True),
                         **{k:m.get(k) for k in ('rmse','mae','bias','p95','n','coverage','false_stop_samples','event_rmse','recovery_s')},
                         distance_rmse=m.get('distance_surrogate',{}).get('reanchored_span_rmse_m')))
    with (output/'per_bag.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    groups=sorted({r['group'] for r in data['clean']});out=[]
    for group in groups:
        for name in NAMES:
            s=v6.summary([r for r in data['clean'] if r['group']==group],[r for r in data['original'] if r['group']==group],name)
            out.append(dict(group=group,model=name,**s))
    save(output/'per_group.json',out)


class Timed:
    def __init__(self,o,start):self.o=o;self.start=start;self.cpu=0.;self.count=0
    def __getattr__(self,k):return getattr(self.o,k)
    def reset(self,**kw):self.o.reset(**kw)
    def step(self,*args,**kw):
        start=time.process_time();out=self.o.step(*args,**kw);elapsed=time.process_time()-start
        if out.t>=self.start+10.:self.cpu+=elapsed;self.count+=1
        return out


def cost(fitted,output):
    store=DevelopmentStore();bag=store.plan['splits']['development'][0];events,_=store.load(bag,'development')
    start=float(events[:,0].min());events=events[events[:,0]<start+190.];c,r,ops=profile();rows=[]
    for name in CANDIDATES:
        for cycle in range(3):
            for order in (('main',name),(name,'main')):
                for model in order:
                    used=[]
                    def factory(cfg):
                        o=Timed(make(cfg,None if model=='main' else fitted[model]['command_map']),start);used.append(o);return o
                    old=ev.Observer
                    try:
                        ev.Observer=factory;t0=time.perf_counter();p0=time.process_time();a,info=ev.replay(events,c,ops)
                        cpu=time.process_time()-p0;wall=time.perf_counter()-t0
                    finally:ev.Observer=old
                    o=used[0];rows.append(dict(pair_candidate=name,cycle=cycle,order=list(order),model=model,
                        step_cpu_s=o.cpu,measured_steps=o.count,step_us=o.cpu/o.count*1e6,
                        replay_cpu_s=cpu,replay_wall_s=wall,outputs=len(a),
                        process_peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024),
                        output_sha256=hashlib.sha256(a.tobytes()).hexdigest(),runtime=info))
    med={}
    for candidate in CANDIDATES:
        med[candidate]={}
        for model in ('main',candidate):
            r=[x for x in rows if x['pair_candidate']==candidate and x['model']==model]
            assert len({x['output_sha256'] for x in r})==1
            med[candidate][model]={k:float(np.median([x[k] for x in r])) for k in
                 ('step_us','replay_cpu_s','replay_wall_s','process_peak_rss_bytes')}
    save(output/'cost.json',dict(bag=bag,warmup_s=10.,measured_s=180.,rows=rows,medians=med,
         qualification='Offline Python process with scientific imports/collectors; not installed ROS latency or node RSS'))
    return store.access


def main():
    p=argparse.ArgumentParser();p.add_argument('--fit',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=2);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    pin=integrity();fitted={n:json.loads((args.fit/(n+'.json')).read_text()) for n in CANDIDATES}
    if not all(d['success'] for d in fitted.values()):
        save(args.output/'decision.json',dict(scientific_verdict='INCONCLUSIVE',reason='fit_not_converged',validation_evaluated=False));return
    store=DevelopmentStore();save(args.output/'started.json',dict(source=os.environ.get('GITHUB_SHA'),baseline=BASE,
         source_sha256=pin,fit_sha256={n:sha(args.fit/(n+'.json')) for n in CANDIDATES},
         plan_sha256=sha(ROOT/'research/R3_H24/PLAN.md'),validation_evaluated=False,test_evaluated=False))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        result=list(pool.map(worker,[(b,fitted,args.output) for b in store.plan['splits']['development']]))
    data={suite:[r[suite] for r in result] if suite in ('clean','activation') else [v for r in result for v in r[suite]]
          for suite in ('clean','original','low_speed','common_mode','transition','phases','activation','access')}
    decision=decide(data,fitted)
    with gzip.open(args.output/'results.json.gz','wt',encoding='utf-8') as raw:
        json.dump(data,raw,ensure_ascii=False,allow_nan=False)
    save(args.output/'decision.json',decision)
    tables(args.output,data);access=cost(fitted,args.output);save(args.output/'access.json',data['access']+access)
    print(json.dumps(decision,indent=2),flush=True)


if __name__=='__main__':main()

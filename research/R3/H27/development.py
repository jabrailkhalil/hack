"""Fixed R3-H27 development only. Scorer/replay/aggregation stay canonical.

This driver has no validation/test stage. Diagnostic references never enter an
Observer. Large traces are gzip; compact raw score rows are retained once.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import subprocess
import time
from common import ROOT,HERE,BASE,ev,OPS,profile,integrity,VehicleStore,save,sha,GuardedReadoutObserver
from probe import original
from reserve_odometry.core import Config,Sample,clip
from reserve_odometry.committed_disturbance import CommittedDisturbanceObserver

SPEC=importlib.util.spec_from_file_location('h27_v6_aggregation',ROOT/'tools/research_v6/compare.py')
v6=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(v6)
NAMES=('R3_v8','v8_control','H27_off','H27_l020','H27_l040')
ALIASES=dict(baseline_v2='R3_v8',balanced_physics='v8_control',off='H27_off',H27_l020='H27_l020',H27_l040='H27_l040')
CANDIDATES=('H27_l020','H27_l040')
THRESHOLD=.0823180344240239
SCALE_SHA='fd6cc4152626c6b71f1c34d8d9a429d4f2df0fd816fe252937690bd3fb437847'
FOUNDATION='464ed0b779cd4059bbdade279a99edd2dcafdc34'
ORIGINAL_REPLAY=ev.replay


def source_manifest():
    p=integrity()
    if sha(HERE/'TRAIN_SCALE.json')!=SCALE_SHA:raise ValueError('Frozen scale changed')
    native=ROOT/'src/reserve_odometry/reserve_odometry'
    if (native/'committed_history.py').read_bytes()!=(HERE/'history.py').read_bytes():
        raise ValueError('History no longer matches foundation')
    p['candidate_code']={str((native/n).relative_to(ROOT)):sha(native/n) for n in ('committed_history.py','committed_disturbance.py')}
    p['scale_sha256']=SCALE_SHA
    p['python']=platform.python_version();p['numpy']=ev.np.__version__
    return p


def checked_class(cls,name,collector,trace):
    class Checked(cls):
        def __init__(self,c,**kwargs):
            self._reference=GuardedReadoutObserver(c,readout=kwargs['readout'])
            super().__init__(c,**kwargs)
        def reset(self,**kwargs):
            super().reset(**kwargs);self._reference.reset(**kwargs)
        def step(self,t,command=None,front=None,rear=None):
            old_d=self.disturbance
            result=super().step(t,command,front,rear)
            expected=self._reference.step(t,command,front,rear)
            for key,value in vars(self._reference).items():
                actual=(self._committed_native_estimate if key=='last_estimate' and getattr(self,'enabled',False)
                        else getattr(self,key))
                if actual!=value:raise AssertionError('Canonical inner state changed: '+key)
            if name in ('R3_v8','v8_control','H27_off') and result!=expected:
                raise AssertionError('Off/control Estimate differs')
            collector['ticks']+=1
            enabled=getattr(self,'enabled',False)
            dv=self._committed_dv if enabled else 0.
            ds=self._committed_ds if enabled else 0.
            da=self._committed_applied_da if enabled else 0.
            active=abs(da)>1e-12 and abs(dv)>1e-12 and result.mode=='MODEL_ONLY'
            collector['effective_ticks']+=int(active)
            collector['effective_entries']+=int(active and enabled and self._committed_eligible_entry)
            collector['tail_ticks']+=int(abs(dv)>1e-12 and not active)
            collector['history_peak']=max(collector['history_peak'],self._committed_history.peak if enabled else 0)
            if trace:
                row=[t,command.value if command else None,front.value if front else None,rear.value if rear else None,
                     old_d,self.disturbance,self.drive_a,self.v,expected.v,result.v,expected.s,result.s,
                     self._committed_d if enabled else None,dv,ds,da,result.mode,result.front_status,result.rear_status]
                trace.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
            return result
    return Checked


def compare(events,refs,fault=None,trace_dir=None,prefix=''):
    cfg,readout=profile();stats={};arrays={};configs={};registry={};streams=[]
    for internal,name in ALIASES.items():
        c=Config(**asdict(cfg));configs[internal]=c
        stats[name]=dict(ticks=0,effective_ticks=0,effective_entries=0,tail_ticks=0,history_peak=0)
        trace=gzip.open(trace_dir/(prefix+'-'+name+'.jsonl.gz'),'wt',compresslevel=6) if trace_dir else None
        if trace:streams.append(trace)
        if name in ('R3_v8','v8_control'):
            cls=checked_class(GuardedReadoutObserver,name,stats[name],trace)
            factory=partial(cls,readout=readout)
        else:
            cls=checked_class(CommittedDisturbanceObserver,name,stats[name],trace)
            factory=partial(cls,readout=readout,lag_s=.2 if name=='H27_l020' else .4,
                            threshold=THRESHOLD,enabled=name!='H27_off')
        registry[id(c)]=(name,factory)
    def capture(events,c,ops,fault=None):
        a,info=ORIGINAL_REPLAY(events,c,ops,fault)
        name=registry[id(c)][0];arrays[name]=a
        stats[name]['outputs_sha256']=hashlib.sha256(a.tobytes()).hexdigest()
        return a,info
    old_observer,old_replay=ev.Observer,ev.replay
    try:
        ev.Observer=lambda c:registry[id(c)][1](c)
        ev.replay=capture
        row=ev.score(events,refs,configs,OPS,fault)
    finally:
        ev.Observer,ev.replay=old_observer,old_replay
        for stream in streams:stream.close()
    base=arrays['R3_v8']
    for name in NAMES:
        if not ev.np.array_equal(base[:,0],arrays[name][:,0]):raise AssertionError('Schedule changed')
    for name in ('v8_control','H27_off'):
        if not ev.np.array_equal(base,arrays[name],equal_nan=True):raise AssertionError('Control replay changed')
    for internal,name in ALIASES.items():
        row['runtime'][name]=row['runtime'].pop(internal) if internal!=name else row['runtime'][name]
        for scores in row['receivers'].values():
            if internal!=name:scores[name]=scores.pop(internal)
    return dict(**row,activation=stats)


def low_speed_windows(events):
    # Exact selector from PR13/f10e3cfc tools/research_lock/low_speed.py;
    # only membership changes from historical validation to current development.
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=ev.np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2)
                        & (u>=0) & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            fault=dict(kind='lock',start=anchor,end=anchor+duration)
            yield fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


def common_windows(events):
    # Exact baseline H11 selector and injection, with no model/profile changes.
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    idx=ev.np.flatnonzero(valid & ((f+r)/2>2) & (abs(f-r)<.15)
                         & (t>max(25.,.1*t[-1])) & (t<t[-1]-35.))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (.7,1.2):
            fault=dict(kind='common_bias',start=anchor,end=anchor+duration,offset=5.)
            window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)].copy()
            mask=(window[:,0]>=anchor)&(window[:,0]<anchor+duration)&(window[:,1]!=0)
            window[mask,2]+=5.
            yield fault,window


def transition_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    mode=ev.np.where(u>.04,1,ev.np.where(u<-.04,-1,0))
    change=ev.np.r_[False,mode[1:]!=mode[:-1]]
    for new_mode in (-1,0,1):
        idx=ev.np.flatnonzero(change & (mode==new_mode) & valid & (abs(f-r)<.15)
                             & ((f+r)/2>1) & (t>25) & (t<t[-1]-15))
        if len(idx):
            start=float(t[idx[0]])+.3
            yield dict(kind='dropout',start=start,end=start+5,command_mode=new_mode),events[(events[:,0]>=start-20)&(events[:,0]<=start+15.1)]


def slow_drift_windows(events):
    first=next(iter(original.fault_windows(events)),None)
    if first is None:return
    anchor=first[0]['start']
    for slope in (-.15,.15):
        fault=dict(kind='dropout',start=anchor,end=anchor+5,drift_slope=slope)
        w=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+15.1)].copy()
        mask=(w[:,0]>=anchor-2)&(w[:,0]<anchor)&(w[:,1]!=0)
        w[mask,2]+=slope*(w[mask,0]-(anchor-2))
        yield fault,w


def synthetic_case(delta_d,delay):
    cfg,_=profile();model=GuardedReadoutObserver(cfg,readout=profile()[1])
    v=2.;drive=0.;events=[];reference=[];dt=.05
    for i in range(901):
        t=i*dt
        if i:
            target=model.drive_target(.2,v)
            drive+=(1-math.exp(-dt/cfg.actuator_tau_s))*(target-drive)
            load=delta_d if t>=30. else 0.
            v=clip(v+dt*clip(drive-model.resistance(v)+load,-cfg.max_accel_mps2,cfg.max_accel_mps2),-cfg.max_speed_mps,cfg.max_speed_mps)
        events.append((t,0,.2))
        if i%2==0:events.extend(((t,1,v),(t,2,v)))
        reference.append((t,abs(v)))
    fault=dict(kind='dropout',start=30.+delay,end=35.+delay,true_load_change=delta_d)
    return ev.np.array(events),dict(master=reference,rover=[]),fault


def worker(args):
    bag,out=args;out=Path(out);store=VehicleStore();events,refs=store.load(bag,'development',reference=True)
    meta=dict(bag=bag,group=store.records[bag]['group'],role='development')
    rows=[]
    rows.append(dict(**meta,suite='clean',case='natural',fault=None,**compare(events,refs)))
    sets=[('original',original.fault_windows),('low_speed',low_speed_windows),('common_mode',common_windows),
          ('transition',transition_windows),('slow_drift',slow_drift_windows)]
    for suite,windows in sets:
        for i,(fault,window) in enumerate(windows(events)):
            trace=out/'traces'
            row=compare(window,refs,fault,trace,bag+'-'+suite+'-'+str(i))
            rows.append(dict(**meta,suite=suite,case=('original-'+str(i) if suite=='original' else suite+'-'+str(i)),fault=fault,**row))
    save(out/'bags'/(bag+'.json'),dict(rows=rows,access=store.access))
    print('DEVELOPMENT',bag,'cases',len(rows),flush=True)
    return rows,store.access


def guards(clean,stress,extra,name):
    b=v6.summary(clean,stress,'R3_v8');c=v6.summary(clean,stress,name);reasons=[]
    for key,allowance in [('clean_rmse',.005),('fault_rmse',.005),('pooled_rmse',.005),('distance_rmse',.01)]:
        if b[key] is None or c[key] is None:reasons.append('missing:'+key)
        elif c[key]>b[key]*(1+allowance)+(1e-6 if b[key]==0 else 0):reasons.append('aggregate_regression:'+key)
    gains={k:(1-c[k]/b[k] if b[k] else None) for k in ('clean_rmse','fault_rmse')}
    if not ((gains['clean_rmse'] is not None and gains['clean_rmse']>=.02) or (gains['fault_rmse'] is not None and gains['fault_rmse']>=.05)):
        reasons.append('insufficient_gain')
    for row in clean+stress+extra:
        if row['runtime'][name]['causal_errors'] or row['runtime'][name]['resets']:reasons.append('causality_or_reset')
        for receiver,scores in row['receivers'].items():
            b1,c1=scores['R3_v8'],scores[name]
            key=row['bag']+'/'+row['case']+'/'+receiver
            if c1['n']!=b1['n'] or c1['coverage']!=b1['coverage']:reasons.append('coverage:'+key)
            if c1['false_stop_samples']>b1['false_stop_samples']:reasons.append('false_stop:'+key)
            if row['fault'] and b1.get('recovery_s') is not None and c1.get('recovery_s') is None:reasons.append('new_unrecovered:'+key)
            if row['suite']=='clean' and b1['rmse'] is not None and (c1['rmse'] is None or c1['rmse']>b1['rmse']+max(.005,.05*b1['rmse'])):
                reasons.append('per_bag:'+key)
    risk={}
    expected_families={'low_speed','common_mode','transition','slow_drift','genuine_load','late_update'}
    for missing in sorted(expected_families-{r['suite'] for r in extra}):
        reasons.append('missing_counterexample:'+missing)
    for family in sorted({r['suite'] for r in extra}):
        rows=[r for r in extra if r['suite']==family]
        rb=v6.macro(rows,'R3_v8','event_rmse');rc=v6.macro(rows,name,'event_rmse')
        passed=rb is not None and rc is not None and rc<=rb*1.005+(1e-6 if rb==0 else 0)
        risk[family]=dict(baseline=rb,candidate=rc,passed=passed)
        if not passed:reasons.append('counterexample_veto:'+family)
    entries=sum(r['activation'][name]['effective_entries'] for r in clean+stress)
    ticks=sum(r['activation'][name]['effective_ticks'] for r in clean+stress)
    groups=sorted({r['group'] for r in clean+stress if r['activation'][name]['effective_entries']})
    coverage=entries>=10 and ticks>=100 and len(groups)>=3
    if not coverage:reasons.append('insufficient_mechanism_coverage')
    return dict(summary=c,gains=gains,rejection_reasons=sorted(set(reasons)),risk=risk,
                coverage=dict(passed=coverage,effective_entries=entries,effective_ticks=ticks,groups=groups),
                eligible=not reasons,scientific_verdict='INCONCLUSIVE' if not coverage else 'REJECTED' if reasons else 'DEVELOPMENT_PASS')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    if not 1<=a.workers<=4:raise ValueError('workers1..4')
    a.output.mkdir(parents=True,exist_ok=False);(a.output/'traces').mkdir();(a.output/'bags').mkdir()
    prov=source_manifest();save(a.output/'started.json',prov)
    store=VehicleStore();allrows=[];access=[]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for rows,journal in pool.map(worker,[(b,str(a.output)) for b in store.plan['splits']['development']]):
            allrows.extend(rows);access.extend(journal)
    for family,delay in [('genuine_load',.7),('late_update',.4)]:
        for change in (-.3,.3):
            events,refs,fault=synthetic_case(change,delay)
            label=family+('_negative' if change<0 else '_positive')
            allrows.append(dict(bag=label,group=family,role='synthetic_counterexample',suite=family,case=label,fault=fault,
                                **compare(events,refs,fault,a.output/'traces',label)))
    # Compare to already measured full canonical v8 foundation, not historical v5 figures.
    path='reports/research_R3/H27/36220511208-1/foundation/baseline_replays.json'
    previous=json.loads(subprocess.check_output(['git','show',FOUNDATION+':'+path],cwd=ROOT))
    lookup={(r['bag'],r['suite']):r for r in previous}
    reproduced=0
    for r in allrows:
        if r['suite'] in ('clean','original'):
            old=lookup[(r['bag'],r['case'])]
            if old['output_sha256']!=r['activation']['R3_v8']['outputs_sha256'] or old['runtime']!=r['runtime']['R3_v8']:
                raise AssertionError('Foundation baseline replay mismatch: '+r['bag']+'/'+r['case'])
            reproduced+=1
    clean=[r for r in allrows if r['suite']=='clean'];stress=[r for r in allrows if r['suite']=='original']
    extra=[r for r in allrows if r['suite'] not in ('clean','original')]
    summaries={n:v6.summary(clean,stress,n) for n in NAMES}
    decisions={n:guards(clean,stress,extra,n) for n in CANDIDATES}
    eligible=[n for n in CANDIDATES if decisions[n]['eligible']]
    selected=min(eligible,key=lambda n:(summaries[n]['fault_rmse'],summaries[n]['clean_rmse'],n)) if eligible else None
    verdict='DEVELOPMENT_PASS' if selected else 'REJECTED' if any(d['coverage']['passed'] for d in decisions.values()) else 'INCONCLUSIVE'
    summary=dict(hypothesis='R3-H27',baseline=BASE,provenance=prov,threshold=THRESHOLD,
                 mechanism_status='ACTIVE' if any(d['coverage']['effective_ticks'] for d in decisions.values()) else 'INACTIVE',
                 coverage_status='SUFFICIENT' if any(d['coverage']['passed'] for d in decisions.values()) else 'INSUFFICIENT',
                 scientific_verdict=verdict,accuracy_contract_passed=bool(selected),runtime_verified=False,ready_to_merge=False,
                 selected=selected,candidates=decisions,aggregates=summaries,baseline_reproduction=dict(replays=reproduced,exact=True),
                 cases={s:sum(r['suite']==s for r in allrows) for s in sorted({r['suite'] for r in allrows})},
                 validation_opened=False,test_evaluated=False)
    # Raw scores are stored once; compressed traces separately, no duplicated per-bag giant JSON.
    save(a.output/'counterexamples.json',[r for r in extra if r['role']=='synthetic_counterexample'])
    save(a.output/'SUMMARY.json',summary);save(a.output/'access.json',access)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()

"""Frozen evaluation only: validation, freeze, then explicitly authorized test.
No fitting, no model selection, no test-based parameter changes. The legacy
research Store remains locked; this separate final loader checks an immutable
source/config/evaluator manifest and records access before test database IO.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/research_v3'), str(ROOT/'tools'), str(ROOT/'src/reserve_odometry')]
import numpy as np
import experiment as ex
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.timeline import Timeline
from export_bags import decode


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def configuration():
    expected=json.loads((ROOT/'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    operational=dict(alignment_delay_s=.06,rate_hz=20.); actual={}
    for line in (ROOT/'src/reserve_odometry/config/default.yaml').read_text().splitlines():
        text=line.strip()
        if ':' not in text or text.startswith('#'): continue
        key,value=text.split(':',1)
        if key.startswith('model.'): actual[key[6:]]=float(value)
        if key in operational: operational[key]=float(value)
    if actual!=expected: raise ValueError('Physics changed from selected v3 calibration')
    return {'baseline_v2':Config(),'balanced_physics':Config(**actual)},operational


def protected_files():
    files=[]
    for pattern in ('*.py','*.yaml','*.msg','package.xml','CMakeLists.txt','setup.cfg'):
        files+=list((ROOT/'src').rglob(pattern))
    files += [ROOT/p for p in ['tools/finalization/evaluate.py','tools/research_v3/experiment.py',
        'tools/research_v3/manifest.py','tools/export_bags.py','research/split_v3.json','research/plan_v3.json',
        'src/reserve_odometry/config/candidates_v3/balanced_physics.json','Dockerfile.environment']]
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(set(files))}


def freeze(path,source_ref):
    if path.exists(): raise FileExistsError('Do not overwrite the freeze')
    store=ex.Store();models,ops=configuration()
    save(path,dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_ref=source_ref,
        source_sha256=protected_files(),test_bags=store.plan['splits']['test'],split_sha256=sha(ROOT/'research/split_v3.json'),
        models={k:asdict(v) for k,v in models.items()},operational=ops,
        authorization='Owner requested final submission completion; final measurement access requires explicit CLI opt-in',
        evaluation='No fitting or selection; both receivers retained; baseline parameters use the same final runtime'))


def verify_freeze(path):
    data=json.loads(path.read_text())
    if data['source_sha256']!=protected_files(): raise ValueError('Source/config/evaluator changed after freeze')
    if data['test_bags']!=ex.Store().plan['splits']['test']: raise ValueError('Test membership changed')
    return data


class FinalStore(ex.Store):
    def __init__(self,authorized=False,freeze_path=None,journal=None):
        super().__init__();self.authorized=authorized;self.journal=journal
        self.frozen=verify_freeze(freeze_path) if authorized else None

    def load(self,bag,purpose):
        if purpose!='test': return super().load(bag,purpose)
        row=self.records[bag]
        if not self.authorized or row['split']!='test' or bag not in self.frozen['test_bags']:
            raise PermissionError('Final test remains locked')
        path=self.root/bag/(bag+'_0.db3'); allowed=list(ex.CHANNELS)+list(ex.REFS)
        self.access.append(dict(bag=bag,purpose='final_test',sha256=row['sha256'],topics=allowed))
        if self.journal: save(self.journal,dict(final_test_opened=True,access=self.access))
        if sha(path)!=row['sha256']: raise ValueError('Bag checksum mismatch')
        events=[];refs={'master':[],'rover':[]};origin=row['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            query=('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(query,allowed):
                stamp,values=decode(raw,typ);t=(stamp-origin)/1e9
                if topic in ex.CHANNELS:
                    ch=ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed): refs[ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs


def replay(events,config,ops,fault=None):
    timeline=Timeline(Observer(config),rate_hz=ops['rate_hz'],delay_s=ops['alignment_delay_s'])
    output=[];modes=Counter();causal_errors=0
    for t,ch,value in events:
        ch=int(ch)
        if fault and fault['start']<=t<fault['end']:
            if fault['kind']=='dropout' and ch in (1,2): continue
            if fault['kind']=='lock' and ch in (1,2): value=0.
            if fault['kind']=='bias' and ch==1: value+=5.
        timeline.ingest(ch,Sample(float(t),float(value)))
        for e,held in timeline.advance():
            if e.mode=='WAITING_FOR_INITIALIZATION':continue
            modes[e.mode]+=1
            causal_errors+=sum(s is not None and s.t>e.t+1e-9 for s in held)
            wheels=[s.value if s is not None and 0<=e.t-s.t<=config.max_age_s else np.nan for s in held[1:]]
            output.append((e.t,e.v,e.s,wheels[0],sum(wheels)/2,e.mode=='STOPPED'))
    a=np.asarray(output,float).reshape(-1,6)
    if len(a) and (not np.all(np.isfinite(a[:,:3])) or not np.all(np.diff(a[:,0])>0)):
        raise AssertionError('Nonfinite/nonmonotone inference')
    return a,dict(resets=timeline.resets,dropped=timeline.dropped,catchups=timeline.catchup_events,
        causal_errors=causal_errors,mode_counts=dict(modes))


def distance_surrogate(prediction,target):
    """Scalar distance vs GNSS-speed integral, NOT xyz/ENU position accuracy."""
    t,s=prediction[:,0],prediction[:,2];valid=np.isfinite(target)
    result=dict(definition='s versus integral matched horizontal GNSS speed; NOT xyz',full_span_terminal_error_m=None,
        full_span_reference_distance_m=None,full_span_terminal_drift_percent=None,continuous_spans=0,reanchored_span_rmse_m=None)
    if len(t)<2:return result
    edge=valid[:-1]&valid[1:]&(np.diff(t)<=.051)
    starts=np.flatnonzero(edge & np.r_[True,~edge[:-1]])
    ends=np.flatnonzero(edge & np.r_[~edge[1:],True])+1
    squares=0.;count=0;longest=None
    for begin,end in zip(starts,ends):
        if t[end]-t[begin]<1.:continue
        ts=t[begin:end+1];v=target[begin:end+1]
        reference_s=np.r_[0.,np.cumsum((v[1:]+v[:-1])*.5*np.diff(ts))]
        error=s[begin:end+1]-s[begin]-reference_s;squares+=float(np.sum(error**2));count+=len(error)
        result['continuous_spans']+=1
        span=dict(start_s=float(t[begin]),duration_s=float(t[end]-t[begin]),reference_distance_m=float(reference_s[-1]),terminal_error_m=float(error[-1]))
        if longest is None or span['duration_s']>longest['duration_s']:longest=span
    result['longest_reference_span']=longest
    if count:result['reanchored_span_rmse_m']=math.sqrt(squares/count)
    if np.all(edge):
        distance=float(np.sum((target[1:]+target[:-1])*.5*np.diff(t)));error=float(s[-1]-s[0]-distance)
        result.update(full_span_terminal_error_m=error,full_span_reference_distance_m=distance,
            full_span_terminal_drift_percent=100*error/distance if distance>1. else None)
    return result


def score(events,refs,models,ops,fault=None):
    predictions={};info={}
    for name,c in models.items():predictions[name],info[name]=replay(events,c,ops,fault)
    base=predictions['baseline_v2'];t=base[:,0]
    if not len(t):return dict(outputs=0,receivers={},runtime=info)
    for name,a in predictions.items():
        if a.shape!=base.shape or not np.allclose(a[:,0],t,rtol=0,atol=1e-8):raise AssertionError('Output schedule differs: '+name)
    receivers={}
    for receiver,values in refs.items():
        target=ex.match(values,t);mask=np.isfinite(target)
        if fault:mask &= (t>=fault['start'])&(t<fault['end']+10.)
        scores={}
        for name,a in predictions.items():
            m=ex.metrics(t,a[:,1],target,mask)
            m['false_stop_samples']=int(np.sum(mask&(target>1.)&(a[:,5]>0)))
            if fault:
                m['event_rmse']=ex.metrics(t,a[:,1],target,mask&(t<fault['end']))['rmse']
                good=mask&(t>=fault['end'])&(np.abs(a[:,1]-target)<.25)
                runs=np.convolve(good.astype(int),np.ones(20,int),mode='valid') if len(t)>=20 else np.array([])
                hits=np.flatnonzero(runs==20);m['recovery_s']=float(t[hits[0]]-fault['end']) if len(hits) else None
            else:m['distance_surrogate']=distance_surrogate(a,target)
            scores[name]=m
        if not fault:
            for label,column in [('front_scaled',3),('mean_scaled',4)]:
                common=mask&np.isfinite(base[:,column]);scores[label]=ex.metrics(t,base[:,column],target,common)
                scores['balanced_physics']['common_'+label+'_rmse']=ex.metrics(t,predictions['balanced_physics'][:,1],target,common)['rmse']
        receivers[receiver]=scores
    return dict(outputs=len(t),expected_ticks=int(np.floor((events[:,0].max()-events[:,0].min())*ops['rate_hz']))+1,
        output_span_s=float(t[-1]-t[0]),first_output_s=float(t[0]),last_output_s=float(t[-1]),
        sensor_duration_s=float(events[:,0].max()-events[:,0].min()),receivers=receivers,runtime=info)


def aggregate(clean,stress):
    result={}
    for name in ['baseline_v2','balanced_physics','front_scaled','mean_scaled']:
        groups={};fg={};missing=[];se=0.;n=0
        for row in clean:
            for receiver,models in row['receivers'].items():
                m=models[name]
                if m['rmse'] is None:missing.append(row['bag']+'/'+receiver);continue
                groups.setdefault(row['group'],[]).append(m['rmse']);se+=m['rmse']**2*m['n'];n+=m['n']
        for row in stress:
            for receiver,models in row['receivers'].items():
                m=models.get(name,{})
                if m.get('event_rmse') is not None:fg.setdefault(row['group'],[]).append(m['event_rmse'])
        result[name]=dict(group_macro_rmse=float(np.mean([np.mean(v) for v in groups.values()])) if groups else None,
            pooled_rmse=math.sqrt(se/n) if n else None,samples=n,groups_with_reference=len(groups),missing_bag_receivers=missing,
            group_macro_fault_event_rmse=float(np.mean([np.mean(v) for v in fg.values()])) if fg else None)
    return result


def run(stage,freeze_path,output,authorize):
    if stage=='test' and not authorize:raise PermissionError('Pass --authorize-final-test')
    if output.exists():raise FileExistsError('Preserve evidence; select a fresh output directory')
    output.mkdir(parents=True)
    store=FinalStore(authorized=stage=='test',freeze_path=freeze_path,journal=output/'access.json')
    models,ops=configuration();clean=[];stress=[];started=time.perf_counter()
    save(output/'started.json',dict(stage=stage,source_sha256=protected_files(),time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    for bag in store.plan['splits'][stage]:
        events,refs=store.load(bag,stage);group=store.records[bag]['group']
        row=dict(bag=bag,group=group,**score(events,refs,models,ops));clean.append(row);faults=[];grid=ex.grid_channels(events)
        if grid is not None:
            t,u,f,r,valid=grid
            indices=np.flatnonzero(valid&((f+r)/2>2.)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25.))
            if len(indices):
                anchor=float(t[indices[0]])
                for kind,duration in [('bias',5.),('dropout',5.),('dropout',10.),('lock',3.)]:
                    fault=dict(kind=kind,start=anchor,end=anchor+duration)
                    window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
                    item=dict(bag=bag,group=group,fault=fault,**score(window,refs,models,ops,fault));stress.append(item);faults.append(item)
        save(output/'bags'/f'{bag}.json',dict(clean=row,stress=faults))
        save(output/'access.json',dict(final_test_opened=stage=='test',access=store.access))
        print(stage,bag,{r:v['balanced_physics']['rmse'] for r,v in row['receivers'].items()},flush=True)
    result=dict(stage=stage,models={k:asdict(v) for k,v in models.items()},operational=ops,test_evaluated=stage=='test',
        source_sha256=protected_files(),elapsed_s=time.perf_counter()-started,python=platform.python_version(),numpy=np.__version__,
        source_ref=os.environ.get('GITHUB_SHA','local'),freeze_sha256=sha(freeze_path) if stage=='test' else None,
        bags=len(clean),fault_scenarios=len(stress),summary=aggregate(clean,stress),clean=clean,stress=stress,
        limitations=['No xyz/map accuracy claimed','Wheel scale 1/3.6 unconfirmed','Scalar distance surrogate is not 3D error',
            'Offline compute is not ROS latency','Baseline uses old parameters with the SAME final runtime fixes'])
    save(output/'results.json',result);print(json.dumps(result['summary'],indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['validation','freeze','test'],required=True)
    p.add_argument('--freeze',type=Path,default=ROOT/'submission/FREEZE.json');p.add_argument('--output',type=Path)
    p.add_argument('--source-ref',default=os.environ.get('GITHUB_SHA','local'));p.add_argument('--authorize-final-test',action='store_true')
    args=p.parse_args()
    if args.stage=='freeze':freeze(args.freeze,args.source_ref)
    else:run(args.stage,args.freeze,args.output or ROOT/'reports/final'/args.stage,args.authorize_final_test)

if __name__=='__main__':main()

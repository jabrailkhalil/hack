"""Original low-speed/H11/H13 generators, independent of candidate selection.

Low-speed predicate: H44 develop.py blob 8fcb8188bef2bc6a1b96b3f68d3cbf5be32b0792.
Slow generator: H13 run.py blob 658a81d311969f771dd0683407695e4081d6930d.
These generators are copied without threshold/anchor changes; no tuning here.
"""
from concurrent.futures import ProcessPoolExecutor
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('targeted_eval',HERE/'evaluate.py')
e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
np=e.np


def low_windows(events):
    grid=e.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid;v=(f+r)/2
    ids=np.flatnonzero(valid&(v>1)&(v<2)&(u>=0)&(t>max(25.,.1*t[-1]))&(t<t[-1]-25.))
    if len(ids):
        anchor=float(t[ids[0]])
        for duration in (3.,5.):
            fault=dict(kind='lock',start=anchor,end=anchor+duration)
            yield fault,events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]


def common_windows(events):
    grid=e.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    indices=np.flatnonzero(valid & ((f+r)/2>2) & (np.abs(f-r)<.15)
                           & (t>max(25.,.1*t[-1])) & (t<t[-1]-35.))
    if not len(indices):return
    anchor=float(t[indices[0]])
    for duration in (.7,1.2):
        fault=dict(kind='common_bias',start=anchor,end=anchor+duration,offset=5.)
        changed=events[(events[:,0]>=anchor-20.)&(events[:,0]<=anchor+duration+10.1)].copy()
        mask=(changed[:,0]>=fault['start'])&(changed[:,0]<fault['end'])&np.isin(changed[:,1],(1,2))
        changed[mask,2]+=fault['offset']
        yield fault,changed


def slow_windows(events):
    grid=e.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    suitable=valid&(np.abs(u)<=.05)&(np.abs(f-r)<.15)&((f+r)*.5>2)
    neutral=(np.abs(u)<=.05)&valid;streak=0;start=None
    for i,ok in enumerate(neutral):
        streak=streak+1 if ok else 0
        if streak>=11 and suitable[i] and t[i]>max(25.,.1*t[-1]) and t[i]<t[-1]-35:
            start=float(t[i]);break
    if start is None:return
    for height,ramp in ((5.,3.),(4.,4.)):
        fault=dict(kind='slow_common',start=start,ramp_end=start+ramp,end=start+ramp+1.,height=height)
        changed=events[(events[:,0]>=start-20)&(events[:,0]<=fault['end']+10.1)].copy()
        mask=(changed[:,0]>=start)&(changed[:,0]<fault['end'])&np.isin(changed[:,1],(1,2))
        changed[mask,2]+=height*np.minimum(1.,(changed[mask,0]-start)/ramp)
        yield fault,changed


def compare_injected(events,refs,models,fault):
    arrays,info=e.predictions(events,models)
    t=arrays['main'][:,0];receivers={}
    for rec,values in refs.items():
        target=e.ex.match(values,t);mask=np.isfinite(target)&(t>=fault['start'])&(t<fault['end']+10)
        scores={}
        for name,a in arrays.items():
            m=e.ex.metrics(t,a[:,1],target,mask)
            m['event_rmse']=e.ex.metrics(t,a[:,1],target,mask&(t<fault['end']))['rmse']
            m['false_stop_samples']=int(np.sum(mask&(target>1)&(a[:,5]>0)))
            good=mask&(t>=fault['end'])&(np.abs(a[:,1]-target)<.25)
            hits=np.flatnonzero(np.convolve(good.astype(int),np.ones(20,int),mode='valid')==20) if len(t)>=20 else []
            m['recovery_s']=float(t[hits[0]]-fault['end']) if len(hits) else None
            scores[name]=m
        receivers[rec]=scores
    return dict(receivers=receivers,runtime=info,outputs=len(t))


def worker(args):
    bag,root,names=args;s=e.DevelopmentStore(root);events,refs=s.load(bag);models=e.c.models(names)
    out={k:[] for k in ['low','common','slow']};meta=dict(bag=bag,group=s.records[bag]['group'],db_sha256=s.records[bag]['sha256'])
    for fault,w in low_windows(events):out['low'].append(dict(meta,fault=fault,**e.g.compare(w,refs,models,fault)))
    for k,fun in [('common',common_windows),('slow',slow_windows)]:
        for fault,w in fun(events):out[k].append(dict(meta,fault=fault,**compare_injected(w,refs,models,fault)))
    return out


def run(root,out,names):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);s=e.DevelopmentStore(root)
    e.save(out/'started.json',dict(models=e.c.manifest(names),source_sha256=e.ev.sha(Path(__file__)),pins=e.pins()))
    with ProcessPoolExecutor(4) as pool:rows=list(pool.map(worker,[(b,str(root),names) for b in s.plan['splits']['development']]))
    all_rows={k:[r for b in rows for r in b[k]] for k in ['low','common','slow']}
    summary={}
    for scope in ['all','30618','30639']:
        summary[scope]={}
        for k,rs in all_rows.items():
            selected=[r for r in rs if scope=='all' or r['bag'].startswith(scope+'_')]
            summary[scope][k]={'scenarios':len(selected),'models':{n:dict(event_rmse=e.v6.macro(selected,n,'event_rmse'),
                false_stops=e.v6.total(selected,n,'false_stop_samples'),unrecovered=e.v6.unrecovered(selected,n)) for n in names}}
    e.save(out/'raw.json',all_rows);e.save(out/'summary.json',summary);print(json.dumps(summary,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',required=True);p.add_argument('--output',required=True)
    p.add_argument('--names',default='main,brake_090');a=p.parse_args();run(a.data_root,a.output,a.names.split(','))

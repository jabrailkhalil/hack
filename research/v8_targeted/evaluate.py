"""Development-only runner, unchanged native timeline/scorer and fixed variants."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import candidates as c
ROOT = c.ROOT


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m


def pins():
    values=json.loads((HERE/'BASELINE_PINS.json').read_text())
    for path,h in values.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=h: raise ValueError('Pin changed: '+path)
    return values

pins()
g=load('targeted_guarded',ROOT/'tools/research_guarded/compare.py')
v6=load('targeted_v6',ROOT/'tools/research_v6/compare.py')
ev,np,ex=g.ev,g.np,g.ev.ex


def save(path,x):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


class DevelopmentStore(ex.Store):
    def load(self,bag,purpose='development'):
        row=self.records[bag]
        if purpose!='development' or row['split']!='development' or bag not in self.plan['splits']['development']:
            raise PermissionError('Only frozen development allowed')
        path=self.root/bag/(bag+'_0.db3')
        if ev.sha(path)!=row['sha256']: raise ValueError('DB checksum mismatch '+bag)
        allowed=list(ex.CHANNELS)+list(ex.REFS)
        self.access.append({'bag':bag,'purpose':purpose,'sha256':row['sha256'],'topics':allowed})
        events=[];refs={'master':[],'rover':[]}
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            q='SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id'
            for topic,typ,raw in con.execute(q,allowed):
                stamp,values=ex.decode(raw,typ);t=(stamp-row['sensor_start_ns'])/1e9
                if topic in ex.CHANNELS:
                    ch=ex.CHANNELS[topic];events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed=math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed):refs[ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float).reshape(-1,3),refs


def score_arrays(arrays,info,refs):
    scores={};t=arrays['main'][:,0]
    for r,values in refs.items():
        target=ex.match(values,t);scores[r]={}
        for name,a in arrays.items():
            m=ex.metrics(t,a[:,1],target,np.isfinite(target))
            m['distance_surrogate']=ev.distance_surrogate(a,target)
            m['false_stop_samples']=int(np.sum(np.isfinite(target)&(target>1)&(a[:,5]>0)))
            scores[r][name]=m
    return dict(receivers=scores,runtime=info,outputs=len(t))


def predictions(events,models,fault=None):
    arrays={};infos={}
    for name,m in models.items():arrays[name],infos[name]=g.predict(events,m,fault)
    for name,a in arrays.items():
        if a.shape!=arrays['main'].shape or not np.array_equal(a[:,0],arrays['main'][:,0]): raise AssertionError('Schedule mismatch')
        if infos[name]['causal_errors'] or infos[name]['resets']: raise AssertionError('Causal/reset error')
    return arrays,infos


def worker(args):
    bag,root,out,names,full=args
    t0=time.monotonic();store=DevelopmentStore(root);events,refs=store.load(bag)
    models=c.models(names);meta=dict(bag=bag,group=store.records[bag]['group'],db_sha256=store.records[bag]['sha256'])
    clean_arrays,clean_info=predictions(events,models)
    clean=dict(meta,**score_arrays(clean_arrays,clean_info,refs))
    stress=[];fulls=[]
    for i,(fault,window) in enumerate(g.fault_windows(events)):
        stress.append(dict(meta,fault=fault,**g.compare(window,refs,models,fault)))
        if full:
            arrays,info=predictions(events,models,fault)
            for name,a in arrays.items():
                ca=clean_arrays[name];pref=a[:,0]<fault['start']
                if not np.array_equal(a[pref,:3],ca[pref,:3]):raise AssertionError('Prefault discrepancy')
                dv=a[:,1]-ca[:,1];ds=a[:,2]-ca[:,2]
                integ=np.r_[0.,np.cumsum(.5*(dv[1:]+dv[:-1])*np.diff(a[:,0]))]
                if np.max(np.abs(ds-ds[0]-integ))>1e-7:raise AssertionError('Integral inconsistency')
            fulls.append(dict(meta,fault=fault,**score_arrays(arrays,info,refs)))
            np.savez_compressed(Path(out)/'arrays'/f'{bag}-fault-{i}.npz',**arrays)
    if full:np.savez_compressed(Path(out)/'arrays'/f'{bag}-clean.npz',**clean_arrays)
    row=dict(clean=clean,stress=stress,full=fulls,access=store.access,seconds=time.monotonic()-t0)
    save(Path(out)/'bags'/f'{bag}.json',row)
    print(bag,round(row['seconds'],2),'s',flush=True)
    return row


def summarize(rows,names,full):
    clean=[r['clean'] for r in rows];stress=[s for r in rows for s in r['stress']];fr=[s for r in rows for s in r['full']]
    scopes={}
    for scope in ['all','30618','30639']:
        filt=lambda r:scope=='all' or r['bag'].startswith(scope+'_')
        cr=list(filter(filt,clean));sr=list(filter(filt,stress));ff=list(filter(filt,fr))
        scopes[scope]={}
        for name in names:
            s=v6.summary(cr,sr,name)
            if full:s['full_faulted_distance_rmse']=v6.macro(ff,name,'distance')
            scopes[scope][name]=s
    return scopes


def run(data_root,output,names,full,workers):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);(output/'bags').mkdir();(output/'arrays').mkdir()
    store=DevelopmentStore(data_root);bags=store.plan['splits']['development']
    started=dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline='b2783206000091ab11a1c11ac3ff79082188a4fb',
        pins=pins(),sources={p.name:ev.sha(p) for p in HERE.iterdir() if p.is_file()},models=c.manifest(names),full=full,
        python=platform.python_version(),numpy=np.__version__,workers=workers,role='reused_development',fitting_calls=0)
    save(output/'started.json',started)
    t0=time.monotonic()
    args=[(b,str(data_root),str(output),names,full) for b in bags]
    with ProcessPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(worker,args))
    scopes=summarize(rows,names,full)
    expected={'clean_rmse':.09266814298282507,'fault_rmse':.2375486120563008,'pooled_rmse':.1293056944774334,'distance_rmse':5.310295004801444,'samples':394221}
    for k,v in expected.items():
        if scopes['all']['main'][k]!=v:raise AssertionError(('Baseline fingerprint',k,scopes['all']['main'][k],v))
    result=dict(scopes=scopes,baseline_fingerprint='EXACT_PASS',seconds=time.monotonic()-t0,ready_to_merge=False)
    save(output/'summary.json',result)
    print(json.dumps(result,indent=2),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--names',default=','.join(c.VARIANTS));p.add_argument('--full',action='store_true');p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();names=a.names.split(',')
    if 'main' not in names or len(set(names))!=len(names):p.error('Unique profiles including main required')
    run(a.data_root,a.output,names,a.full,a.workers)

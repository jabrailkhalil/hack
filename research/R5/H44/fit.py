"""H44 matched offline identification. No train GNSS enters an Observer.

G and W share windows, weights, prior, bounds and scalar runtime; only labels
change. No validation/test path. Preregistered in FIT_PLAN commit353f5657.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from functools import partial
import numpy as np
from scipy.optimize import least_squares
from interface import ROOT, BASE, profile, effective, with_effective
from baseline_preflight import ex, g, write, sha, source_integrity
from reserve_odometry.core import Sample
from reserve_odometry.guarded_readout import GuardedReadoutObserver

FIT_PLAN_SHA = '353f5657b32c331f792cb164400db940c16686ea'
HORIZONS = np.array([.5, 2., 5.])
INDICES = np.array([10, 40, 100])
SCALES = .1 + .2 * HORIZONS
LOW, HIGH = np.array([.05, 1., .05]), np.array([5., 100., 5.])
TEACHER_HASH = '5c8129133758bbb715f2e170122b976f95d0240c18daa731472d910f0bf274d0'


def dependencies(lock_path, teacher):
    lock = json.loads(Path(lock_path).read_text())
    if lock.get('status') != 'VERIFIED' or lock.get('baseline_sha') != BASE:
        raise PermissionError('Missing verified dependencies')
    for x in lock['files'].values():
        if sha(x['path']) != x['sha256']:
            raise ValueError('Dependency hash mismatch: ' + x['path'])
    if sha(teacher/'R5_HANDOFF.json') != TEACHER_HASH:
        raise ValueError('Unexpected teacher')
    handoff = json.loads((teacher/'R5_HANDOFF.json').read_text())
    for entry in handoff['files']:
        if sha(teacher/entry['path']) != entry['sha256']:
            raise ValueError('Changed teacher payload: ' + entry['path'])
    return lock, handoff


def teacher_grid(native_ns, values, accepted, query_ns):
    """Interpolate only adjacent accepted rows, not across a masked row/gap."""
    native_ns = np.asarray(native_ns, dtype=np.int64)
    result = np.full(len(query_ns), np.nan)
    if not len(native_ns):
        return result
    if np.any(np.diff(native_ns) <= 0):
        raise ValueError('Teacher source grid must strictly increase')
    j = np.searchsorted(native_ns, query_ns, side='left')
    jj = np.minimum(j, len(native_ns)-1)
    exact = (j < len(native_ns)) & (native_ns[jj] == query_ns)
    ok = exact & accepted[jj] & np.isfinite(values[jj])
    result[ok] = values[jj[ok]]
    between = ~exact & (j > 0) & (j < len(native_ns))
    idx = np.flatnonzero(between)
    a, b = j[idx]-1, j[idx]
    valid = (accepted[a] & accepted[b] & np.isfinite(values[a]) & np.isfinite(values[b])
             & (native_ns[b]-native_ns[a] <= 200_000_000))
    idx, a, b = idx[valid], a[valid], b[valid]
    weight = (query_ns[idx]-native_ns[a])/(native_ns[b]-native_ns[a])
    result[idx] = values[a] + weight*(values[b]-values[a])
    return result


class Capture:
    def __init__(self, c, readout):
        self.o = GuardedReadoutObserver(c, readout=readout)
        self.rows = []
    def __getattr__(self, key):
        return getattr(self.o, key)
    def reset(self, **kw):
        self.o.reset(**kw)
    def step(self, t, command=None, front=None, rear=None):
        e = self.o.step(t, command, front, rear)
        row = [t]
        for s in (command, front, rear):
            row.extend((s.t,s.value) if s is not None else (np.nan,np.nan))
        self.rows.append(row)
        return e


def capture(events):
    c, r, _ = profile(); instances = []
    def factory(config):
        instance = Capture(config, r); instances.append(instance); return instance
    output, info = g.predict(events, (factory, c))
    return np.asarray(instances[0].rows), output, info


def build(args):
    args.output.mkdir(parents=True, exist_ok=False)
    lock, h = dependencies(args.lock, args.teacher)
    source_integrity(args.source_receipt)
    foldfile = Path(lock['files']['folds']['path'])
    folds = {x['bag']:x for x in json.loads(foldfile.read_text())['records']}
    entries = {x['bag']:x for x in h['files'] if x.get('kind') == 'teacher_array'}
    store = ex.Store(args.data_root); cfg, _, _ = profile()
    canonical = {}
    for b in sorted(folds):
        canonical.setdefault(folds[b]['wire_sha256'], b)
    windows, gt, wt, meta, stats = [], [], [], [], []
    write(args.output/'started.json', dict(stage='MATCHED_WINDOW_BUILD',fit_plan_sha=FIT_PLAN_SHA,
          dependencies_sha256=sha(args.lock),source_sha256=sha(__file__),train_only=True,
          teacher_offline_only=True,validation_opened=False,test_opened=False))
    for bag in sorted(folds):
        f = folds[bag]; entry = entries[bag]
        if store.records[bag]['split'] != 'train' or entry['db_sha256'] != store.records[bag]['sha256']:
            raise PermissionError('Teacher/DB role identity mismatch')
        events, _ = store.load(bag, 'train')
        rows, _, info = capture(events)
        if info['causal_errors'] or info['resets']:
            raise AssertionError('Unexpected training schedule failure')
        p = args.teacher/entry['path']
        with np.load(p, allow_pickle=False) as teacher:
            t_ns = np.rint(rows[:,0]*1e9).astype(np.int64) + store.records[bag]['sensor_start_ns']
            targets = teacher_grid(teacher['stamp_ns'], teacher['speed_mps'], teacher['accepted'], t_ns)
        reject = Counter(); chosen = Counter(); duplicates = canonical[f['wire_sha256']] != bag
        for k in range(100, len(rows)-100, 100):
            phase = 'traction' if rows[k,2]>cfg.command_deadband else 'braking' if rows[k,2]<-cfg.command_deadband else 'coast'
            if duplicates: reject['wire_duplicate']+=1; continue
            if chosen[phase]>=2: continue
            w = rows[k-100:k+101]
            if not np.all(np.isfinite(w)) or not np.allclose(np.diff(w[:,0]),.05,rtol=0,atol=1e-9):
                reject['missing_or_grid']+=1; continue
            ages=w[:,0,None]-w[:,[1,3,5]]
            if np.any(ages < -1e-9) or np.any(ages > np.array([cfg.command_timeout_s,cfg.max_age_s,cfg.max_age_s])):
                reject['stale_or_future']+=1; continue
            if (np.any(np.abs(w[:,2])>1.000001) or np.any(np.abs(w[:,[4,6]])>cfg.max_speed_mps)
                 or np.any(np.abs(w[:,3]-w[:,5])>cfg.pair_skew_s)
                 or np.any(np.abs(w[:,4]-w[:,6])>cfg.disagreement_mps)):
                reject['wheel_or_command_invalid']+=1; continue
            if not np.any(np.abs(w[100:,4]+w[100:,6])*.5 > .5):
                reject['no_motion']+=1; continue
            target=targets[k:k+101]
            if not np.all(np.isfinite(target)):
                reject['teacher_missing_or_masked']+=1; continue
            chosen[phase]+=1
            windows.append(w.copy());gt.append(target.copy());wt.append(np.abs(w[100:,[4,6]]).mean(axis=1))
            meta.append(dict(bag=bag,group=f['group'],label=f['vehicle_manifest_label'],fold=f['fold'],phase=phase,
                             anchor_s=float(rows[k,0]),wire_sha256=f['wire_sha256']))
        stats.append(dict(bag=bag,group=f['group'],fold=f['fold'],outputs=len(rows),selected=dict(chosen),
                          rejections=dict(reject),teacher_grid_points=int(np.isfinite(targets).sum()),
                          wire_representative=canonical[f['wire_sha256']],runtime=info))
        print('WINDOWS',bag,dict(chosen),flush=True)
    counts = {fold:dict(windows=sum(x['fold']==fold for x in meta),
                        groups=len({x['group'] for x in meta if x['fold']==fold}),
                        phases={ph:len({x['group'] for x in meta if x['fold']==fold and x['phase']==ph}) for ph in ('traction','braking','coast')}) for fold in ('fit','check')}
    passed=(len(meta)>=30 and counts['fit']['groups']>=3 and counts['check']['groups']>=2
            and all(counts['fit']['phases'][p]>=3 and counts['check']['phases'][p]>=2 for p in ('traction','braking')))
    np.savez_compressed(args.output/'windows.npz',samples=np.asarray(windows),gnss=np.asarray(gt),wheel=np.asarray(wt))
    write(args.output/'windows.json',meta);write(args.output/'coverage.json',dict(passed=passed,counts=counts,bags=stats))
    write(args.output/'access.json',store.access)
    write(args.output/'WINDOWS_LOCK.json',dict(fit_plan_sha=FIT_PLAN_SHA,dependencies_sha256=sha(args.lock),
        source_sha256=sha(__file__),files={n:sha(args.output/n) for n in ('windows.npz','windows.json','coverage.json','access.json')}))
    print('COVERAGE',passed,counts,flush=True)


def tuples(window):
    return [(float(row[0]), *(Sample(float(row[j]),float(row[j+1])) for j in (1,3,5))) for row in window]


class Predictor:
    """Actual scalar Observer.step is used throughout warmup and forecast."""
    def __init__(self, samples):
        self.samples = [tuples(w) for w in samples]
        self.config, self.readout, _ = profile()
    def predict(self, logratio, indices=None):
        cfg=with_effective(self.config, np.asarray(effective(self.config))*np.exp(logratio))
        indices=range(len(self.samples)) if indices is None else indices
        vs=[]
        for i in indices:
            w=self.samples[i]; o=GuardedReadoutObserver(cfg,readout=self.readout)
            for t,c,f,r in w[:101]:
                e=o.step(t,c,f,r)
            if not o.initialized:
                raise AssertionError('Window did not initialize')
            values=[e.v]
            for t,c,_,_ in w[101:]:
                values.append(o.step(t,c,None,None).v)
            vs.append(values)
        return np.asarray(vs)


def prefixes(v, samples):
    return np.cumsum(.5*(np.abs(v[:,1:])+np.abs(v[:,:-1]))*np.diff(samples[:,100:,0],axis=1),axis=1)[:,INDICES-1]


def balanced_weights(meta):
    bygroup=defaultdict(lambda:defaultdict(list))
    for i,m in enumerate(meta):bygroup[m['group']][m['bag']].append(i)
    weights=np.zeros(len(meta))
    for bags in bygroup.values():
        for idx in bags.values():weights[idx]=1/(len(bygroup)*len(bags)*len(idx))
    return weights


def errors(pred, target, samples):
    return np.abs(pred[:,INDICES])-target[:,INDICES], prefixes(pred,samples)-prefixes(target,samples)


def describe(pred, target, samples, meta):
    ve,ie=errors(pred,target,samples)
    def section(idx):
        weights=balanced_weights([meta[i] for i in idx]);v=ve[idx];s=ie[idx]
        return dict(windows=len(idx),groups=len({meta[i]['group'] for i in idx}),
            velocity_rms=float(np.sqrt(np.sum(weights*np.mean(v*v,axis=1)))),
            integral_rms=float(np.sqrt(np.sum(weights*np.mean(s*s,axis=1)))),
            velocity_by_horizon=np.sqrt(np.sum(weights[:,None]*v*v,axis=0)).tolist(),
            integral_by_horizon=np.sqrt(np.sum(weights[:,None]*s*s,axis=0)).tolist(),
            signed_velocity_bias=np.sum(weights[:,None]*v,axis=0).tolist(),
            signed_integral_bias=np.sum(weights[:,None]*s,axis=0).tolist())
    result={}
    for fold in ('fit','check'):
        ids=[i for i,m in enumerate(meta) if m['fold']==fold]
        result[fold]=dict(all=section(ids),groups={},phases={})
        for field in ('group','phase'):
            for name in sorted({meta[i][field] for i in ids}):
                idx=[i for i in ids if meta[i][field]==name]
                result[fold]['groups' if field=='group' else 'phases'][name]=section(idx)
    return result


def fit(args):
    args.output.mkdir(parents=True,exist_ok=False)
    cov=json.loads((args.windows/'coverage.json').read_text())
    if not cov['passed']:raise PermissionError('Coverage gate failed; no optimization')
    wl=json.loads((args.windows/'WINDOWS_LOCK.json').read_text())
    if wl['source_sha256']!=sha(__file__):raise ValueError('Source changed since window lock')
    for n,h in wl['files'].items():
        if sha(args.windows/n)!=h:raise ValueError('Changed windows')
    meta=json.loads((args.windows/'windows.json').read_text())
    with np.load(args.windows/'windows.npz',allow_pickle=False) as z:
        samples=z['samples'];targets={n:z[n] for n in ('gnss','wheel')}
    predictor=Predictor(samples);prior=np.asarray(effective(predictor.config))
    idx=np.array([i for i,m in enumerate(meta) if m['fold']=='fit']);weights=balanced_weights([meta[i] for i in idx])
    count=0;measurements={};start=time.perf_counter()
    write(args.output/'started.json',dict(fit_plan_sha=FIT_PLAN_SHA,source_sha256=sha(__file__),window_lock_sha256=sha(args.windows/'WINDOWS_LOCK.json'),
            dependencies_sha256=wl['dependencies_sha256'],theta0=prior.tolist(),bounds=[LOW.tolist(),HIGH.tolist()],
            teacher_runtime=False,validation_opened=False,test_opened=False))
    base_pred=predictor.predict(np.zeros(3));predictions={'baseline':base_pred}
    for name,target in targets.items():
        local_calls=[]
        def residual(x):
            nonlocal count
            count+=1
            if count>1000:raise RuntimeError('Total fitting call budget exhausted')
            pred=predictor.predict(x,idx)
            ve,ie=errors(pred,target[idx],samples[idx])
            res=np.concatenate([ve/SCALES,ie/(HORIZONS*SCALES)],axis=1)
            res=(res*np.sqrt(weights[:,None]/6)).ravel()
            record=dict(call=count,fit_call=len(local_calls)+1,logratio=x.tolist(),data_loss=float(res@res),prior_loss=float(.01*np.mean(x*x)))
            local_calls.append(record)
            with (args.output/(name+'_calls.jsonl')).open('a') as f:f.write(json.dumps(record)+'\n')
            if len(local_calls)%10==0:print('FIT',name,len(local_calls),record['data_loss'],flush=True)
            return np.r_[res,np.sqrt(.01/3)*x]
        r=least_squares(residual,np.zeros(3),bounds=(np.log(LOW/prior),np.log(HIGH/prior)),method='trf',jac='2-point',
                        x_scale=1.,max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        cfg=with_effective(predictor.config,prior*np.exp(r.x))
        result=dict(name=name,success=bool(r.success),message=r.message,nfev=r.nfev,njev=r.njev,actual_residual_calls=len(local_calls),
                    cost=float(r.cost),optimality=float(r.optimality),logratio=r.x.tolist(),effective=effective(cfg),config=asdict(cfg),
                    readout=asdict(predictor.readout),fit_plan_sha=FIT_PLAN_SHA,window_lock_sha256=sha(args.windows/'WINDOWS_LOCK.json'),
                    source_sha256=sha(__file__),deployable_only_parameters=True)
        write(args.output/(name+'.json'),result)
        predictions[name]=predictor.predict(r.x)
        print('FIT DONE',name,result['effective'],r.nfev,len(local_calls),flush=True)
    for name,pred in predictions.items():
        measurements[name]={target:describe(pred,y,samples,meta) for target,y in targets.items()}
    check={}
    for name in targets:
        a=measurements['baseline'][name]['check'];b=measurements[name][name]['check'];fail=[]
        for metric in ('velocity_rms','integral_rms'):
            if b['all'][metric]>a['all'][metric]*1.005+1e-12:fail.append('aggregate:'+metric)
            for group,v in a['groups'].items():
                if b['groups'][group][metric]>v[metric]*1.05+1e-12:fail.append(group+':'+metric)
        check[name]=dict(passed=not fail,reasons=fail)
    write(args.output/'metrics.json',measurements);write(args.output/'check_gate.json',check)
    np.savez_compressed(args.output/'predictions.npz',**predictions)
    write(args.output/'FIT_LOCK.json',dict(source_sha256=sha(__file__),files={n:sha(args.output/n) for n in ('gnss.json','wheel.json','metrics.json','check_gate.json','predictions.npz')},
                                        total_residual_calls=count,elapsed_s=time.perf_counter()-start,optimizer_calls=2))
    print('CHECK',json.dumps(check),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='stage',required=True)
    b=sub.add_parser('build');b.add_argument('--teacher',type=Path,required=True);b.add_argument('--lock',type=Path,required=True);b.add_argument('--data-root',type=Path,required=True);b.add_argument('--source-receipt',type=Path,required=True)
    f=sub.add_parser('fit');f.add_argument('--windows',type=Path,required=True)
    for q in (b,f):q.add_argument('--output',type=Path,required=True)
    args=p.parse_args();(build if args.stage=='build' else fit)(args)
if __name__=='__main__':main()

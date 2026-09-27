"""R6-H54: exactly two preregistered fits on immutable H44 recorded windows.

This module changes ONLY the group aggregation of the offline objective. The
numerical predictor is imported unchanged from the hash-verified H44 delivery.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.metadata, json, math, platform, sys, time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'research/R5/H44'), str(ROOT/'src/reserve_odometry')]
import fit as h44
PLAN_COMMIT='440921dc3ea3b37b8462034c7a0c5296608ab0a2'
BASE='b2783206000091ab11a1c11ac3ff79082188a4fb'
METRICS=('velocity_rms','integral_rms')

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def now(): return datetime.now(timezone.utc).isoformat()

def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def table(path, rows):
    if not rows: raise ValueError('Do not emit empty metric placeholders')
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def sources():
    paths=[Path(__file__),Path(__file__).with_name('R6-H54_PLAN.md'),
           ROOT/'research/R5/H44/fit.py',ROOT/'research/R5/H44/interface.py',
           ROOT/'research/R5/H44/baseline_preflight.py',
           ROOT/'src/reserve_odometry/config/champion_v8.yaml',
           ROOT/'src/reserve_odometry/reserve_odometry/core.py',
           ROOT/'src/reserve_odometry/reserve_odometry/guarded_readout.py',
           ROOT/'src/reserve_odometry/reserve_odometry/timeline.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}

def load(args, fold):
    lock=json.loads(args.lock.read_text())
    assert lock['status']=='VERIFIED' and lock['baseline_sha']==BASE
    for row in lock['files'].values():
        if sha(row['path'])!=row['sha256']:raise ValueError('Dependency changed: '+row['path'])
    meta=json.loads((args.windows/'windows.json').read_text())
    ids=np.array([i for i,m in enumerate(meta) if m['fold']==fold],dtype=int)
    # One archived container includes both folds; only the specified slice is
    # exposed to this stage. No check prediction/loss before FITS_FREEZE.
    with np.load(args.windows/'windows.npz',allow_pickle=False) as z:
        samples=z['samples'][ids];target=z['gnss'][ids]
    if not len(ids) or not np.isfinite(samples).all() or not np.isfinite(target).all():
        raise ValueError('Missing/nonfinite frozen input')
    return samples,target,[meta[i] for i in ids],ids

def six(pred, target, samples):
    v,s=h44.errors(pred,target,samples)
    return np.concatenate([v/h44.SCALES,s/(h44.HORIZONS*h44.SCALES)],axis=1)

class Objective:
    def __init__(self,meta,denominators):
        self.groups=sorted({m['group'] for m in meta});self.G=len(self.groups);self.K=(self.G+1)//2
        self.ids=[np.array([i for i,m in enumerate(meta) if m['group']==g]) for g in self.groups]
        self.within=[h44.balanced_weights([meta[i] for i in ix]) for ix in self.ids]
        self.den=np.array([denominators[g] for g in self.groups])
        if np.any(self.den<=0) or not np.isfinite(self.den).all(): raise ValueError('Invalid denominators')
        self.window_den=np.array([denominators[m['group']] for m in meta])
        self.weights=h44.balanced_weights(meta)
    def losses(self,e):
        return np.array([np.sum(w*np.mean(e[ix]**2,axis=1)) for ix,w in zip(self.ids,self.within)])
    def residual(self,e,x,robust):
        losses=self.losses(e);ratios=losses/self.den
        top=np.argsort(-ratios,kind='stable')[:self.K]
        block=(e*np.sqrt(self.weights[:,None]/self.window_den[:,None]/6)).ravel()
        if robust: block=block*np.sqrt(.5); tail=np.sqrt(.5/self.K)*np.sqrt(ratios[top])
        else: tail=np.zeros(self.K)
        r=np.r_[block,tail,np.sqrt(.01/3)*x]
        cost=(.5*np.mean(ratios)+.5*np.mean(ratios[top]) if robust else np.mean(ratios))+.01*np.mean(x*x)
        if not math.isclose(float(r@r),float(cost),rel_tol=3e-14,abs_tol=3e-14):
            raise AssertionError('Residual representation changes objective')
        return r,losses,ratios,top

def prepare(args):
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'OBJECTIVE_CONTRACT.json').exists():raise FileExistsError('Objective already frozen')
    samples,target,meta,idx=load(args,'fit');s0=sources();t0=time.perf_counter()
    predictor=h44.Predictor(samples);pred=predictor.predict(np.zeros(3))
    dummy=Objective(meta,{m['group']:1. for m in meta});lg=dummy.losses(six(pred,target,samples))
    positive=lg[lg>0]
    if not len(positive):raise ValueError('No positive baseline losses')
    eps=.01*float(np.median(positive));den=np.maximum(lg,eps)
    old=args.windows.parent/'fitting/predictions.npz'
    with np.load(old,allow_pickle=False) as z:historical=z['baseline'][idx]
    difference=float(np.max(np.abs(pred-historical)))
    if not np.array_equal(pred,historical):raise AssertionError('Canonical H44 baseline prediction differs')
    rows=[]
    for g,loss,d,ix in zip(dummy.groups,lg,den,dummy.ids):
        mm=[meta[i] for i in ix]
        rows.append(dict(group=g,fold='fit',label=mm[0]['label'],windows=len(ix),bags=len({m['bag'] for m in mm}),
                         Lg0=float(loss),eps=eps,denominator=float(d),clipped_by_eps=bool(loss<eps)))
    table(args.output/'GROUP_LOSS_BASELINE.csv',rows)
    np.savez_compressed(args.output/'BASELINE_FIT_PREDICTIONS.npz',velocity=pred,window_indices=idx)
    obj=dict(schema_version=1,hypothesis_id='R6-H54',created_utc=now(),plan_commit=PLAN_COMMIT,
        dependency_lock_sha256=sha(args.lock),source_hashes=s0,fit_only=True,check_evaluated=False,
        groups=rows,G=dummy.G,K=dummy.K,eps=eps,theta0=list(h44.effective(predictor.config)),
        absolute_bounds=[h44.LOW.tolist(),h44.HIGH.tolist()],initial_logratio=[0.,0.,0.],
        horizons=h44.HORIZONS.tolist(),scales=h44.SCALES.tolist(),warmup_steps=101,forecast_steps=100,
        C0='mean_g(Lg/max(Lg0,eps)) + 0.01*mean(logratio**2)',
        C1='0.5*mean_g(Rg) + 0.5*mean(worst_ceil_G_over_2_Rg) + 0.01*mean(logratio**2)',
        group_mass='equal; bags then windows balanced within group; exact H44 duplicates/windows',
        nonsmooth='Continuous sorted sqrt(group-loss-ratio) tail; stable descending order; no smoothing; forward 2-point Jacobian',
        solver=dict(method='trf',jac='2-point',x_scale=1.,loss='linear',max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8),
        optimizer_runs=2,total_actual_residual_cap=1000,
        h44_fit_baseline_max_abs_difference=difference,baseline_replay_elapsed_s=time.perf_counter()-t0,
        environment=dict(python=platform.python_version(),numpy=np.__version__,scipy=importlib.metadata.version('scipy'),platform=platform.platform()),
        preregistered_admission=dict(aggregate_max_regression=.005,per_group_max_regression=.05,worst_material_gain=.05,other_worst_max_regression=.005,
          loo='Frozen models, no refits. Material metric must retain nonnegative aggregate and worst gains after excluding each check group.'))
    assert sources()==s0
    write(args.output/'OBJECTIVE_CONTRACT.json',obj)
    print('OBJECTIVE_FROZEN',eps,dummy.G,dummy.K,'baseline_difference',difference,flush=True)

def fit(args):
    out=args.output;contract=json.loads((out/'OBJECTIVE_CONTRACT.json').read_text())
    if (out/'CONTROL_FIT.json').exists() or (out/'ROBUST_FIT.json').exists():raise FileExistsError('Never restart fits')
    assert contract['source_hashes']==sources() and contract['dependency_lock_sha256']==sha(args.lock)
    samples,target,meta,idx=load(args,'fit');predictor=h44.Predictor(samples)
    obj=Objective(meta,{r['group']:r['denominator'] for r in contract['groups']})
    prior=np.array(contract['theta0']);total=0;fits=[];preds={};t0=time.perf_counter()
    write(out/'FIT_STARTED.json',dict(created_utc=now(),objective_sha256=sha(out/'OBJECTIVE_CONTRACT.json'),source_hashes=sources(),check_evaluated=False))
    for name,robust in [('CONTROL',False),('ROBUST',True)]:
        local=0;callpath=out/(name+'_CALLS.jsonl')
        if callpath.exists():raise FileExistsError('Call ledger already exists')
        def residual(x):
            nonlocal total,local
            total+=1;local+=1
            if total>1000:raise RuntimeError('Actual residual budget exhausted')
            pred=predictor.predict(x);r,l,rat,top=obj.residual(six(pred,target,samples),x,robust)
            sr=np.sort(rat)[::-1];gap=float(sr[obj.K-1]-sr[obj.K]) if obj.K<obj.G else None
            row=dict(created_utc=now(),call=total,fit_call=local,logratio=x.tolist(),objective=float(r@r),
                     group_losses=l.tolist(),group_ratios=rat.tolist(),top_groups=[obj.groups[i] for i in top],cutoff_gap=gap)
            with callpath.open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n');f.flush()
            if local%10==0:print(name,'actual_calls',local,'objective',float(r@r),flush=True)
            return r
        result=least_squares(residual,np.zeros(3),bounds=(np.log(h44.LOW/prior),np.log(h44.HIGH/prior)),**contract['solver'])
        cfg=h44.with_effective(predictor.config,prior*np.exp(result.x))
        pred=predictor.predict(result.x);preds[name]=pred
        r,l,rat,top=obj.residual(six(pred,target,samples),result.x,robust)
        data=dict(name=name,created_utc=now(),success=bool(result.success),status=int(result.status),message=result.message,
            nfev=int(result.nfev),njev=int(result.njev),actual_residual_calls=local,objective=float(r@r),scipy_cost=float(result.cost),
            optimality=float(result.optimality),logratio=result.x.tolist(),effective=list(h44.effective(cfg)),
            config=asdict(cfg),readout=asdict(predictor.readout),group_order=obj.groups,group_losses=l.tolist(),group_ratios=rat.tolist(),
            top_groups=[obj.groups[i] for i in top],plan_commit=PLAN_COMMIT,objective_sha256=sha(out/'OBJECTIVE_CONTRACT.json'),
            source_hashes=sources(),trained_on='train-fit only',check_evaluated=False)
        write(out/(name+'_FIT.json'),data);fits.append(data)
        print('FIT_DONE',name,data['effective'],'nfev',result.nfev,'actual_calls',local,flush=True)
    np.savez_compressed(out/'FITTED_TRAIN_PREDICTIONS.npz',**preds)
    names=['CONTROL_FIT.json','ROBUST_FIT.json','CONTROL_CALLS.jsonl','ROBUST_CALLS.jsonl','FITTED_TRAIN_PREDICTIONS.npz','BASELINE_FIT_PREDICTIONS.npz','OBJECTIVE_CONTRACT.json','GROUP_LOSS_BASELINE.csv']
    freeze=dict(schema_version=1,hypothesis_id='R6-H54',created_utc=now(),plan_commit=PLAN_COMMIT,source_hashes=sources(),
        dependency_lock_sha256=sha(args.lock),total_actual_residual_calls=total,optimizer_calls=2,restarts=0,
        files={n:sha(out/n) for n in names},check_evaluated=False,development_opened=False,validation_opened=False,final_test_opened=False,
        elapsed_s=time.perf_counter()-t0,convergence_passed=all(x['success'] for x in fits))
    assert sources()==contract['source_hashes']
    write(out/'FITS_FREEZE.json',freeze)
    print('FITS_FROZEN',sha(out/'FITS_FREEZE.json'),flush=True)

def physical(pred,target,samples,meta):
    v,s=h44.errors(pred,target,samples);w=h44.balanced_weights(meta)
    z=dict(windows=len(meta),bags=len({m['bag'] for m in meta}),groups=len({m['group'] for m in meta}),
        velocity_rms=float(np.sqrt(np.sum(w*np.mean(v*v,axis=1)))),integral_rms=float(np.sqrt(np.sum(w*np.mean(s*s,axis=1)))))
    for j,h in enumerate(h44.HORIZONS):
        for name,e in [('velocity',v),('integral',s)]:
            z[f'{name}_rms_{h:g}s']=float(np.sqrt(np.sum(w*e[:,j]**2)))
            z[f'{name}_signed_proxy_bias_{h:g}s']=float(np.sum(w*e[:,j]))
    return z

def confirm(args):
    out=args.output;frozen=json.loads((out/'FITS_FREEZE.json').read_text())
    assert frozen['source_hashes']==sources() and not frozen['check_evaluated']
    for n,h in frozen['files'].items():assert sha(out/n)==h,n
    if (out/'CHECK_STARTED.json').exists():raise FileExistsError('No repeated check')
    write(out/'CHECK_STARTED.json',dict(created_utc=now(),freeze_sha256=sha(out/'FITS_FREEZE.json'),retuning_allowed=False))
    fits={n:json.loads((out/(n+'_FIT.json')).read_text()) for n in ('CONTROL','ROBUST')}
    allrows=[];grouprows=[];slicerows=[];loorows=[];raw={};metrics={};worst=[]
    for fold in ('fit','check'):
        samples,target,meta,idx=load(args,fold)
        if fold=='fit':
            with np.load(out/'BASELINE_FIT_PREDICTIONS.npz',allow_pickle=False) as z:base=z['velocity']
            with np.load(out/'FITTED_TRAIN_PREDICTIONS.npz',allow_pickle=False) as z:preds={'BASELINE':base,**{n:z[n] for n in fits}}
        else:
            p=h44.Predictor(samples);preds={'BASELINE':p.predict(np.zeros(3)),**{n:p.predict(np.array(f['logratio'])) for n,f in fits.items()}}
        raw.update({fold+'_'+n:a for n,a in preds.items()});metrics[fold]={}
        groups=sorted({m['group'] for m in meta})
        for name,pred in preds.items():
            assert np.isfinite(pred).all()
            agg=physical(pred,target,samples,meta);metrics[fold][name]={'aggregate':agg,'groups':{}}
            allrows.append(dict(fold=fold,model=name,**agg))
            for g in groups:
                ids=[i for i,m in enumerate(meta) if m['group']==g]
                z=physical(pred[ids],target[ids],samples[ids],[meta[i] for i in ids])
                metrics[fold][name]['groups'][g]=z
                grouprows.append(dict(fold=fold,model=name,group=g,label=meta[ids[0]]['label'],**z))
            for field in ('label','phase'):
                for value in sorted({m[field] for m in meta}):
                    ids=[i for i,m in enumerate(meta) if m[field]==value]
                    slicerows.append(dict(fold=fold,model=name,slice_by=field,slice=value,**physical(pred[ids],target[ids],samples[ids],[meta[i] for i in ids])))
            for metric in METRICS:
                vals={g:m[metric] for g,m in metrics[fold][name]['groups'].items()}
                worst.append(dict(fold=fold,model=name,metric=metric,worst_group=max(vals,key=vals.get),worst_rms=max(vals.values()),median_group_rms=float(np.median(list(vals.values())))))
        for excluded in groups:
            ids=[i for i,m in enumerate(meta) if m['group']!=excluded]
            row=dict(fold=fold,excluded_group=excluded,remaining_groups=len(groups)-1,refit=False)
            for name in ('CONTROL','ROBUST'):
                agg=physical(preds[name][ids],target[ids],samples[ids],[meta[i] for i in ids])
                for metric in METRICS:
                    row[name+'_'+metric]=agg[metric]
                    row[name+'_worst_'+metric]=max(z[metric] for g,z in metrics[fold][name]['groups'].items() if g!=excluded)
            for metric in METRICS:
                row[metric+'_gain_pct']=100*(1-row['ROBUST_'+metric]/row['CONTROL_'+metric])
                row['worst_'+metric+'_gain_pct']=100*(1-row['ROBUST_worst_'+metric]/row['CONTROL_worst_'+metric])
            loorows.append(row)
    fail=[];check=metrics['check'];c=check['CONTROL'];r=check['ROBUST']
    if not frozen['convergence_passed']:fail.append('solver_not_converged')
    gains={};material=[]
    for metric in METRICS:
        if r['aggregate'][metric]>c['aggregate'][metric]*1.005+1e-12:fail.append('aggregate:'+metric)
        for g in c['groups']:
            if r['groups'][g][metric]>c['groups'][g][metric]*1.05+1e-12:fail.append('per_group:'+g+':'+metric)
        cw=max(z[metric] for z in c['groups'].values());rw=max(z[metric] for z in r['groups'].values())
        gains[metric]=dict(control_worst=cw,robust_worst=rw,worst_gain_pct=100*(1-rw/cw),
            control_aggregate=c['aggregate'][metric],robust_aggregate=r['aggregate'][metric],aggregate_gain_pct=100*(1-r['aggregate'][metric]/c['aggregate'][metric]))
        if rw<=.95*cw+1e-12:material.append(metric)
        if rw>cw*1.005+1e-12:fail.append('worst_regression:'+metric)
    if not material:fail.append('no_material_worst_group_gain')
    stable=[]
    for metric in material:
        bad=[z['excluded_group'] for z in loorows if z['fold']=='check' and (z['ROBUST_'+metric]>z['CONTROL_'+metric]+1e-12 or z['ROBUST_worst_'+metric]>z['CONTROL_worst_'+metric]+1e-12)]
        if not bad:stable.append(metric)
    if material and not stable:fail.append('loo_concentration_or_sign_reversal')
    diff=float(np.max(np.abs(np.array(fits['ROBUST']['logratio'])-np.array(fits['CONTROL']['logratio']))))
    if diff<1e-3 and max(v['worst_gain_pct'] for v in gains.values())<1.:fail.append('near_identical_no_check_benefit')
    table(out/'CHECK_RESULTS.csv',[z for z in allrows if z['fold']=='check'])
    table(out/'FIT_RESULTS.csv',[z for z in allrows if z['fold']=='fit'])
    table(out/'PER_GROUP.csv',grouprows);table(out/'LABEL_PHASE_RESULTS.csv',slicerows)
    table(out/'WORST_MEDIAN_GROUP.csv',worst);table(out/'LOO_SENSITIVITY.csv',loorows)
    np.savez_compressed(out/'RAW_PREDICTIONS.npz',**raw)
    write(out/'PHYSICAL_METRICS.json',metrics)
    verdict=dict(hypothesis_id='R6-H54',created_utc=now(),scientific_verdict='CHECK_ADMITTED_DEVELOPMENT_PENDING' if not fail else 'REJECTED',
        development_admitted=not fail,reasons=fail,check_comparison=gains,material_metrics=material,loo_stable_material_metrics=stable,
        logratio_max_difference=diff,freeze_sha256=sha(out/'FITS_FREEZE.json'),source_hashes=sources(),retuned_on_check=False,
        optimizer_calls=2,total_actual_residual_calls=frozen['total_actual_residual_calls'],
        train_check_reused=True,loo_is_reaggregation_not_refit=True,development_opened=False,validation_opened=False,final_test_opened=False,
        accuracy_contract_L_evaluated=False,ready_to_merge=False)
    write(out/'ADMISSION.json',verdict)
    print('ADMISSION',json.dumps(verdict,ensure_ascii=False),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['prepare','fit','confirm']);p.add_argument('--lock',type=Path,required=True)
    p.add_argument('--windows',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();globals()[args.stage](args)
if __name__=='__main__':main()

"""Exactly two preregistered bounded train fits; no SQLite or validation access."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import time
from scipy.optimize import least_squares
from common import ROOT, BASE, np, profile, integrity, save, sha, GuardedReadoutObserver
from preflight import samples
from reserve_odometry.command_map import CommandMap, CommandMapObserver


def decode(a):
    result = []
    for i in (0, 3):
        q1 = a[i]; q2 = q1 + (1-q1)*a[i+1]; q3 = q2 + (1-q2)*a[i+2]
        result.extend((float(q1), float(q2), float(q3)))
    return np.asarray(result)


def encode(q):
    result = []
    for i in (0, 3):
        result.extend((q[i], (q[i+1]-q[i])/(1-q[i]), (q[i+2]-q[i+1])/(1-q[i+1])))
    return np.asarray(result)


def observer(q, enabled=True):
    c, r, _ = profile()
    if q is None:
        return GuardedReadoutObserver(c, readout=r)
    return CommandMapObserver(c, readout=r,
        command_map=CommandMap(tuple(q[:3]), tuple(q[3:]), enabled))


def prepare(windows):
    return [[(float(row[0]), *samples(row)) for row in window] for window in windows]


def rollouts(prepared, q):
    outputs = []
    for window in prepared:
        o = observer(q)
        for row in window[:101]:
            o.step(*row)
        result = []
        for k, row in enumerate(window[101:], 1):
            e = o.step(row[0], row[1], None, None)
            if k in (10, 40):
                result.append(e.v)
        outputs.append(result)
    return np.asarray(outputs)


def weights(meta):
    n = Counter(x['group'] for x in meta)
    return np.asarray([1.0/(len(n)*n[x['group']]*2) for x in meta])[:, None]


def data_residual(prediction, target, w):
    r = (prediction-target)/np.array([.2, .5])
    transformed = np.sqrt(2.)*r/np.sqrt(np.sqrt(1+r*r)+1)
    return (np.sqrt(w)*transformed).ravel()


def describe(meta, target, pred):
    rows = []
    for idx, m in enumerate(meta):
        rows.append({k:v for k,v in m.items() if k not in ('baseline_prediction','residual_mps','wheel_target')} |
                    dict(target=target[idx].tolist(), prediction=pred[idx].tolist(),
                         residual_mps=(pred[idx]-target[idx]).tolist()))
    stats = []
    for role in ('fitting', 'check'):
        for phase in ('all','traction','braking','coast'):
            ix = [i for i,m in enumerate(meta) if m['role']==role and (phase=='all' or m['phase']==phase)]
            if not ix:
                continue
            mm = [meta[i] for i in ix]; ww = weights(mm)
            stats.append(dict(role=role,phase=phase,windows=len(ix),groups=len({m['group'] for m in mm}),
                data_loss=float(np.sum(data_residual(pred[ix],target[ix],ww)**2)),
                horizon_group_rms=np.sqrt(np.sum(2*ww*(pred[ix]-target[ix])**2,axis=0)).tolist()))
    return dict(stats=stats, per_window=rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--preflight',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False); pinned=integrity()
    coverage=json.loads((args.preflight/'coverage.json').read_text())
    assert coverage['eligible'] and len(coverage['free_nodes'])==6
    assert sha(args.preflight/'train_windows.npz') == '0f2303b11ebe327cbefe990e958b6d3d3e97db95684ca9d5cc7decd74bacaf37'
    assert sha(args.preflight/'windows.json') == '4a592f54b564873b08d1b374c62829f78a1b39545a48fa8da7209fb159944fc7'
    assert sha(args.preflight/'coverage.json') == '0efbb7e526c77c4271c17a4a03ba93be6886cab89a1b000ef60a6f333aeef6ac'
    meta=json.loads((args.preflight/'windows.json').read_text())
    windows=np.load(args.preflight/'train_windows.npz',allow_pickle=False)['windows']
    prepared=prepare(windows);target=np.asarray([m['wheel_target'] for m in meta])
    c,r,ops=profile(); prior=np.tile(np.array([.25,.5,.75])**c.command_exponent,2); start=encode(prior)
    fit_ix=[i for i,m in enumerate(meta) if m['role']=='fitting']; fp=[prepared[i] for i in fit_ix]
    w=weights([meta[i] for i in fit_ix]);ft=target[fit_ix]
    baseline=rollouts(prepared,None)
    old=np.asarray([m['baseline_prediction'] for m in meta]); delta=float(np.max(abs(old-baseline)))
    assert delta<=1e-10, ('preflight baseline mismatch',delta)
    save(args.output/'baseline.json',describe(meta,target,baseline))
    prior_pred=rollouts(fp,prior)
    jac=[]
    for j in range(6):
        plus=start.copy();minus=start.copy();plus[j]+=1e-5;minus[j]-=1e-5
        jac.append(((rollouts(fp,decode(plus))-rollouts(fp,decode(minus)))/(2e-5)/np.array([.2,.5])).ravel())
    singular=np.linalg.svd(np.stack(jac,axis=1),compute_uv=False)
    save(args.output/'started.json',dict(baseline=BASE,source=os.environ.get('GITHUB_SHA'),source_sha256=pinned,
         plan_sha256=sha(ROOT/'research/R3_H24/PLAN.md'),prior_nodes=prior.tolist(),fractions=start.tolist(),
         fitting_windows=len(fit_ix),check_windows=len(meta)-len(fit_ix),
         baseline_reproduction_max_abs_delta=delta,data_only_jacobian_singular_values=singular.tolist(),
         data_only_jacobian_rank=int(np.sum(singular>1e-8)),
         warning='finite differences are local sensitivity, not physical identifiability; no regularization rows',
         validation_evaluated=False,test_evaluated=False))
    if not np.any(singular>1e-8):
        save(args.output/'decision.json',dict(verdict='INCONCLUSIVE',reason='zero_recursive_sensitivity',variants=[]));return
    results=[]
    for label,lam in [('H24_L01',.1),('H24_L1',1.)]:
        calls=0;clock=time.perf_counter()
        def residual(a):
            nonlocal calls
            calls+=1;q=decode(a)
            data=data_residual(rollouts(fp,q),ft,w)
            penalty=np.sqrt(lam/6.)*(q-prior)/.25
            return np.r_[data,penalty]
        fit=least_squares(residual,start,bounds=(np.zeros(6),np.ones(6)),method='trf',jac='2-point',
                          max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        q=decode(fit.x);pred=rollouts(prepared,q)
        result=dict(name=label,lambda_=lam,success=bool(fit.success),status=int(fit.status),message=fit.message,
                    nfev=int(fit.nfev),njev=int(fit.njev),actual_objective_calls=calls,elapsed_s=time.perf_counter()-clock,
                    objective=float(2*fit.cost),fractions=fit.x.tolist(),knots=q.tolist(),
                    active_mask=fit.active_mask.tolist(),config=asdict(c),readout=asdict(r),operational=ops,
                    command_map=dict(traction=q[:3].tolist(),braking=q[3:].tolist(),enabled=True),
                    **describe(meta,target,pred))
        save(args.output/(label+'.json'),result);results.append({k:result[k] for k in
             ('name','lambda_','success','nfev','njev','actual_objective_calls','knots','objective','stats')})
        print('FIT',json.dumps(results[-1]),flush=True)
    save(args.output/'decision.json',dict(variants=results,selected=None,selection_stage='development only',
                                       validation_evaluated=False,test_evaluated=False))


if __name__=='__main__':main()

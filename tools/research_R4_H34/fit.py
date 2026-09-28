"""Exactly one matched seven-parameter fit for each H34 scheme A/B."""
import argparse
from collections import Counter
from dataclasses import asdict
import datetime
import inspect
import json
import os
from pathlib import Path
import time
from scipy.optimize import least_squares
from common import ROOT,D,BASE,np,profile,theta0,configuration,make,integrity,save,sha,NAMES,LOW,HIGH
from foundation import load_input,scalar,vector


def data_residual(prediction,target,groups):
    counts=Counter(groups)
    w=np.array([1./(2*len(counts)*counts[g]) for g in groups])[:,None]
    r=(prediction-target)/np.array([.2,.5])
    return (np.sqrt(w)*np.sqrt(2.)*r/np.sqrt(np.sqrt(1+r*r)+1)).ravel()


def describe(meta,windows,prepared,scheme,theta,pred,target):
    anchors=[]
    for w in prepared:
        o=make(scheme,theta)
        for row in w[:101]:e=o.step(*row)
        anchors.append(e.s)
    reference=.5*(windows[:,:,4]+windows[:,:,6]);dt=np.diff(windows[:,100:,0],axis=1)
    integral=np.cumsum(.5*(reference[:,100:-1]+reference[:,101:])*dt,axis=1)[:,[9,39]]
    velocity=pred[:,[9,39],0]-target
    distance=pred[:,[9,39],1]-np.array(anchors)[:,None]-integral
    rows=[]
    for i,m in enumerate(meta):
        rows.append(dict(bag=m['bag'],group=m['group'],role=m['role'],phase=m['phase'],anchor=m['anchor'],
            target_mps=target[i].tolist(),velocity_error_mps=velocity[i].tolist(),integral_error_m=distance[i].tolist()))
    stats=[]
    for role in ('fitting','check'):
        for phase in ('all','traction','braking','coast'):
            ix=[i for i,m in enumerate(meta) if m['role']==role and (phase=='all' or phase==m['phase'])]
            if not ix:continue
            groups=sorted({meta[i]['group'] for i in ix});vg=[];sg=[];per_group={}
            for g in groups:
                j=[i for i in ix if meta[i]['group']==g];v=velocity[j];s=distance[j]
                vg.append(np.mean(v*v,axis=0));sg.append(np.mean(s*s,axis=0))
                per_group[g]=dict(windows=len(j),velocity_rmse=np.sqrt(np.mean(v*v,axis=0)).tolist(),
                    signed_velocity_bias=np.mean(v,axis=0).tolist(),integral_rmse=np.sqrt(np.mean(s*s,axis=0)).tolist(),
                    signed_integral_bias=np.mean(s,axis=0).tolist())
            stats.append(dict(role=role,phase=phase,windows=len(ix),groups=len(groups),
                data_loss=float(np.sum(data_residual(pred[ix][:,[9,39],0],target[ix],[meta[i]['group'] for i in ix])**2)),
                velocity_group_rms=np.sqrt(np.mean(vg,axis=0)).tolist(),integral_group_rms=np.sqrt(np.mean(sg,axis=0)).tolist(),per_group=per_group))
    return dict(stats=stats,per_window=rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--train',type=Path,required=True);p.add_argument('--foundation',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();decision=json.loads((args.foundation/'decision.json').read_text());assert decision['foundation_passed']
    args.output.mkdir(parents=True,exist_ok=False);pins=integrity();meta,w,prepared,target,receipt=load_input(args.train)
    ix=[i for i,m in enumerate(meta) if m['role']=='fitting'];wp=w[ix];pp=[prepared[i] for i in ix];tg=target[ix];groups=[meta[i]['group'] for i in ix]
    initial=theta0();kwargs=dict(method='trf',jac='2-point',max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8,x_scale='jac')
    save(args.output/'started.json',dict(baseline=BASE,source_ref=os.environ.get('GITHUB_SHA'),
       timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),theta0=initial.tolist(),bounds=[LOW.tolist(),HIGH.tolist()],
       parameter_names=NAMES,solver_kwargs=kwargs,objective_source_sha256=__import__('hashlib').sha256(inspect.getsource(data_residual).encode()).hexdigest(),
       foundation_sha256=sha(args.foundation/'decision.json'),input=receipt,baseline_integrity=pins,
       fitting_windows=len(ix),check_windows=len(meta)-len(ix),selectable=['B'],control=['A'],validation_opened=False,test_opened=False))
    bp=vector(prepared,w,'baseline')
    save(args.output/'baseline.json',describe(meta,w,prepared,'baseline',None,bp,target))
    for scheme in ('A','B'):
        calls=0;start=time.perf_counter();trace=[]
        def residual(theta):
            nonlocal calls
            calls+=1;pred=vector(pp,wp,scheme,theta)[:,[9,39],0]
            r=data_residual(pred,tg,groups)
            trace.append(dict(call=calls,theta=theta.tolist(),loss=float(r@r)))
            if calls%20==0:print(scheme,'residual_call',calls,'loss',float(r@r),flush=True)
            return r
        fit=least_squares(residual,initial.copy(),bounds=(LOW.copy(),HIGH.copy()),**kwargs)
        pred=vector(prepared,w,scheme,fit.x);actual=scalar(prepared,scheme,fit.x)
        parity=np.max(abs(pred-actual),axis=(0,1));assert np.all(parity<=1e-9),(scheme,parity)
        result=dict(scheme=scheme,selectable=(scheme=='B'),success=bool(fit.success),status=int(fit.status),
           message=fit.message,nfev=int(fit.nfev),njev=int(fit.njev),actual_residual_calls=calls,
           theta=fit.x.tolist(),config=asdict(configuration(fit.x)),readout=asdict(profile()[1]),
           active_mask=fit.active_mask.tolist(),optimizer_cost=float(fit.cost),elapsed_s=time.perf_counter()-start,
           scalar_vector_parity_max_abs=parity.tolist(),jacobian_singular_values=np.linalg.svd(fit.jac,compute_uv=False).tolist(),
           **describe(meta,w,prepared,scheme,fit.x,pred,target))
        save(args.output/(scheme+'.json'),result);save(args.output/(scheme+'-residual_calls.json'),trace)
        np.savez_compressed(args.output/(scheme+'-prediction.npz'),prediction=pred)
        print('FIT_DONE',scheme,fit.success,'nfev',fit.nfev,'njev',fit.njev,'calls',calls,'theta',fit.x.tolist(),flush=True)
    save(args.output/'COMPLETED.json',dict(fits=['A','B'],selectable=['B'],refits=0,validation_opened=False,test_opened=False))

if __name__=='__main__':main()

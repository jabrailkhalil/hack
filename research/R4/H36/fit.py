"""One profiled fit plus one nonselectable b=0 control. Fixed H36 budget."""
import argparse
from dataclasses import asdict
import datetime
import json
import os
from pathlib import Path
import time
from scipy.optimize import least_squares
from model import *
from foundation import integrity


def load_data(directory, role):
    with np.load(Path(directory)/(role+'.npz'),allow_pickle=False) as z:
        data={k:z[k] for k in ('u','v','y')}
    data['meta']=json.loads((Path(directory)/(role+'-windows.json')).read_text())
    return data


def stats(theta,data):
    error=physical(theta,data['u'],data['v'])-data['y']
    b=profile_load(error);corrected=error+BIN*b[:,None];w=weights(data['meta'])
    by_group={};by_phase={}
    for name,field,result in [('group','group',by_group),('phase','phase',by_phase)]:
        for key in sorted({m[field] for m in data['meta']}):
            idx=np.array([m[field]==key for m in data['meta']])
            e=error[idx];p=corrected[idx]
            result[key]=dict(windows=int(idx.sum()),raw_increment_rmse_mps=float(np.sqrt(np.mean(e*e))),
                raw_increment_bias_mps=float(e.mean()),profiled_increment_rmse_mps=float(np.sqrt(np.mean(p*p))),
                profiled_increment_bias_mps=float(p.mean()))
    r=residual(theta,data,True);r0=residual(theta,data,False)
    return dict(profiled_objective=float(r@r),unprofiled_objective=float(r0@r0),
        raw_increment_rmse_mps=float(np.sqrt(np.sum(w*np.mean(error*error,axis=1)))),
        raw_increment_bias_mps=float(np.sum(w*error.mean(axis=1))),
        profiled_increment_rmse_mps=float(np.sqrt(np.sum(w*np.mean(corrected**2,axis=1)))),
        loads_min=float(b.min()),loads_max=float(b.max()),loads_mean=float(w@b),
        bound_windows=int(np.sum(np.abs(b)>=profile()[0].disturbance_limit_mps2-1e-9)),
        by_group=by_group,by_phase=by_phase),b,error,corrected


def yaml_text(theta):
    cfg=asdict(configuration(theta));lines=[]
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        key=line.strip().partition(':')[0]
        if key.startswith('model.') and key[6:] in FIELDS:
            line='    '+key+': '+repr(float(cfg[key[6:]]))
        lines.append(line)
    return '# H36 research calibration, not canonical default. No window loads exported.\n'+'\n'.join(lines)+'\n'


def run(foundation,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    integrity();foundation=Path(foundation)
    if not json.loads((foundation/'result.json').read_text())['foundation_passed']:
        raise PermissionError('No fitting after failed foundation')
    fitting,check=load_data(foundation,'fitting'),load_data(foundation,'check')
    save(output/'started.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        baseline=BASE,plan_commit=PLAN_SHA,source_ref=os.environ.get('H36_SOURCE_SHA','local-uncommitted'),
        code_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
        foundation_sha256=sha(foundation/'result.json'),split_sha256=sha(foundation/'groups.json'),
        fitting_npz_sha256=sha(foundation/'fitting.npz'),check_npz_sha256=sha(foundation/'check.npz'),
        max_nfev_per_fit=80,actual_calls_cap_per_fit=640,candidate='profiled',control_selectable=False,
        validation_opened=False,test_opened=False))
    results={'baseline':dict(theta=theta0().tolist(),config=asdict(configuration()))}
    for name,nuisance in [('profiled',True),('control_no_nuisance',False)]:
        calls=0;begin=time.perf_counter()
        def fun(x):
            nonlocal calls
            calls+=1
            if calls>640:raise RuntimeError('Prospective actual-call cap exceeded')
            return residual(x,fitting,nuisance)
        opt=least_squares(fun,theta0(),bounds=(LOW,HIGH),method='trf',jac='2-point',
                          max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        results[name]=dict(theta=opt.x.tolist(),config=asdict(configuration(opt.x)),
            selectable=nuisance,success=bool(opt.success),status=int(opt.status),message=opt.message,
            nfev=opt.nfev,njev=opt.njev,actual_residual_calls=calls,
            cost=float(2*opt.cost),elapsed_s=time.perf_counter()-begin,
            near_bound_parameters=[PARAMETERS[k] for k in range(3) if min(opt.x[k]-LOW[k],HIGH[k]-opt.x[k])<1e-5])
        print('FIT',name,results[name],flush=True)
    for name,model in results.items():
        model['roles']={}
        for role,data in [('fitting',fitting),('check',check)]:
            s,b,e,p=stats(model['theta'],data)
            model['roles'][role]=s
            np.savez_compressed(output/(name+'-'+role+'-diagnostics.npz'),load=b,error=e,profiled_error=p)
        if name!='baseline':
            save(output/(name+'.json'),dict(config=model['config'],theta=model['theta'],
                readout=asdict(profile()[1]),runtime_class='GuardedReadoutObserver',
                baseline=BASE,window_nuisance_exported=False,selectable=model['selectable']))
            (output/(name+'.yaml')).write_text(yaml_text(model['theta']))
    candidate=results['profiled'];base=results['baseline'];reasons=[]
    ranks={role:rank_report(candidate['theta'],d) for role,d in [('fitting',fitting),('check',check)]}
    if not candidate['success']:reasons.append('optimizer_unsuccessful')
    if not all(r['passed'] for r in ranks.values()):reasons.append('postfit_rank_or_coverage')
    if candidate['roles']['check']['profiled_objective']>base['roles']['check']['profiled_objective']*1.005:
        reasons.append('check_profiled_objective_regression')
    summary=dict(models=results,rank_after_fit=ranks,prerequisite_passed=not reasons,
        prerequisite_failures=reasons,selected_for_development='profiled',control_selectable=False,
        validation_opened=False,test_opened=False)
    save(output/'results.json',summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--foundation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.foundation,a.output)

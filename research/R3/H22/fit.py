"""Two fixed H22 objectives; train-only fitting and pre-development selection."""
import argparse
from collections import Counter
from pathlib import Path
import time
import numpy as np
from scipy.optimize import least_squares
from scipy.special import logsumexp
import data as d

SIGMA_S=d.HORIZONS*d.SIGMA
LAMBDA_S=1.0
LAMBDA_W=1.0
TEMPERATURE=.1
TOTAL_CALL_LIMIT=1600


def rho(x):return 2*x*x/(np.sqrt(1+x*x)+1)
def robust_residual(x):return x*np.sqrt(2/(np.sqrt(1+x*x)+1))

def cells(windows):
    return {g:np.array([i for i,w in enumerate(windows) if (w.group,w.phase)==g])
            for g in sorted({(w.group,w.phase) for w in windows})}

def group_mean(values,windows):
    return np.mean([np.mean(values[[i for i,w in enumerate(windows) if w.group==g]],axis=0)
                    for g in sorted({w.group for w in windows})],axis=0)

def loss_components(e,s,windows,base_cells=None):
    lv=rho(e/d.SIGMA);ls=rho(s/SIGMA_S)
    cell={g:float(np.mean(lv[ii])+LAMBDA_S*np.mean(ls[ii])) for g,ii in cells(windows).items()}
    worst=None
    if base_cells is not None:
        differences=np.array([cell[g]-base_cells[g] for g in sorted(cell)])
        worst=float(TEMPERATURE*np.logaddexp(0,logsumexp(differences/TEMPERATURE)-np.log(len(differences))))
    return dict(velocity=float(np.mean(group_mean(lv,windows))),
                prefix_integral=float(np.mean(group_mean(ls,windows))),
                smooth_worst_regression=worst),cell


def summarize(theta,windows,check_groups,baseline_cells):
    ev,es,pred=d.proxy_errors(theta,windows);summary={};records=[]
    for role in ['fitting','check']:
        ix=[i for i,w in enumerate(windows) if (w.group in check_groups)==(role=='check')]
        ws=[windows[i] for i in ix];e,s=ev[ix],es[ix]
        losses,_=loss_components(e,s,ws,baseline_cells[role]);rows=[]
        keys=[('all','all')]+[('group',g) for g in sorted({w.group for w in ws})]
        keys += [('phase',p) for p in ['traction','coast','braking']]
        keys += [('group_phase',g+'|'+p) for g,p in sorted(cells(ws))]
        for kind,key in keys:
            ii=[i for i,w in enumerate(ws) if kind=='all' or (kind=='group' and w.group==key)
                or (kind=='phase' and w.phase==key) or (kind=='group_phase' and w.group+'|'+w.phase==key)]
            if not ii:continue
            selected=[ws[i] for i in ii];ee,ss=e[ii],s[ii]
            rows.append(dict(kind=kind,key=key,windows=len(ii),groups=len({w.group for w in selected}),
                velocity_rmse=group_mean_root_square(ee,selected),signed_bias=group_mean(ee,selected).tolist(),
                prefix_rmse=group_mean_root_square(ss,selected),signed_integral_bias=group_mean(ss,selected).tolist()))
        summary[role]=dict(loss=losses,rows=rows,windows=len(ws))
    for w,e,s in zip(windows,ev,es):
        records.append(dict(bag=w.bag,group=w.group,phase=w.phase,anchor=w.anchor,
            role='check' if w.group in check_groups else 'fitting',velocity_error=e.tolist(),prefix_error=s.tolist()))
    return dict(summary=summary,per_window=records)


def group_mean_root_square(x,ws):
    return np.mean([np.sqrt(np.mean(x[[i for i,w in enumerate(ws) if w.group==g]]**2,axis=0))
                   for g in sorted({w.group for w in ws})],axis=0).tolist()


def check_veto(base,candidate):
    b=base['summary']['check'];c=candidate['summary']['check'];reasons=[]
    for key in ['velocity','prefix_integral']:
        if c['loss'][key]>b['loss'][key]*1.005+1e-12:reasons.append('check_component:'+key)
    br={(r['kind'],r['key']):r for r in b['rows']}
    for row in c['rows']:
        if row['kind'] not in ('group','phase'):continue
        old=br[row['kind'],row['key']]
        for j,h in enumerate(d.HORIZONS):
            if row['velocity_rmse'][j]>old['velocity_rmse'][j]+max(.02,.1*old['velocity_rmse'][j]):
                reasons.append(f'check_velocity:{row["kind"]}:{row["key"]}:{h}')
            bias=abs(old['signed_integral_bias'][j])
            if abs(row['signed_integral_bias'][j])>bias+max(.02,.1*bias):
                reasons.append(f'check_integral_bias:{row["kind"]}:{row["key"]}:{h}')
    return sorted(set(reasons))


class BudgetExceeded(RuntimeError):pass
class Budget:
    def __init__(self,limit=TOTAL_CALL_LIMIT):self.limit=limit;self.used=0
    def charge(self):
        if self.used>=self.limit:raise BudgetExceeded('Fixed total residual-call budget exhausted')
        self.used+=1


def export_yaml(path,theta):
    c=d.config_for(theta);lines=[]
    for line in d.PROFILE.with_suffix('.yaml').read_text().splitlines():
        k,sep,_=line.strip().partition(':')
        if sep and k.startswith('model.'):line='    '+k+': '+repr(float(getattr(c,k[6:])))
        lines.append(line)
    Path(path).write_text('# R3-H22 experimental calibration; use canonical guarded executable\n'+'\n'.join(lines)+'\n')


def run(output,premise):
    out=d.new_dir(output);d.save(out/'started.json',d.provenance('fitting'))
    pre=d.json.loads(premise.read_text())
    if not pre.get('sufficient_premise'):raise PermissionError('Premise/coverage failed; no fitting')
    groups=d.json.loads((d.HERE/'train_groups.json').read_text());assert groups==pre['groups']
    store=d.Store(out/'access.json');windows,inventory=d.collect_windows(store)
    meta=[(w.bag,w.group,w.phase,w.anchor) for w in windows]
    expected=[(w['bag'],w['group'],w['phase'],w['anchor']) for w in pre['per_window']]
    assert meta==expected,'Diagnostic windows changed'
    chk=set(groups['check']);fit=[w for w in windows if w.group not in chk]
    check=[w for w in windows if w.group in chk]
    base_cells={}
    for role,ws in [('fitting',fit),('check',check)]:
        e,s,_=d.proxy_errors(d.THETA0,ws);_,base_cells[role]=loss_components(e,s,ws)
    baseline=summarize(d.THETA0,windows,chk,base_cells);d.save(out/'baseline_proxy.json',baseline)
    counter=Counter(w.group for w in fit)
    weights=np.sqrt(np.array([1/(len(counter)*counter[w.group]*3) for w in fit]))[:,None]
    budget=Budget();models={}
    for name in ['A','B']:
        trace=[];start=time.perf_counter();calls_before=budget.used
        def residual(theta):
            budget.charge();e,s,_=d.proxy_errors(theta,fit)
            rv=(robust_residual(e/d.SIGMA)*weights).ravel()
            rs=(robust_residual(s/SIGMA_S)*weights*np.sqrt(LAMBDA_S)).ravel()
            pieces=[rv,rs]
            components,_=loss_components(e,s,fit,base_cells['fitting'])
            if name=='B':pieces.append(np.array([np.sqrt(LAMBDA_W*components['smooth_worst_regression'])]))
            r=np.concatenate(pieces)
            trace.append(dict(call=budget.used,theta=theta.tolist(),loss=float(r@r),components=components))
            if len(trace)%25==0:
                d.save(out/(name+'_progress.json'),dict(calls=len(trace),total_calls=budget.used,last=trace[-1]))
                print('FIT',name,len(trace),'loss',float(r@r),flush=True)
            return r
        try:
            result=least_squares(residual,d.THETA0,bounds=(d.LOW,d.HIGH),method='trf',jac='2-point',
                loss='linear',x_scale=d.SCALE,max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        except BudgetExceeded as exc:
            d.save(out/(name+'_calls.json'),trace)
            models[name]=dict(completed=False,reason=str(exc),residual_calls=budget.used-calls_before)
            continue
        theta=result.x;proxy=summarize(theta,windows,chk,base_cells)
        fast=d.predict_windows(theta,windows);slow=np.stack([d.original_rollout(theta,w) for w in windows])
        parity=float(np.max(abs(fast-slow)))
        veto=check_veto(baseline,proxy)
        if parity>1e-10:veto.append('rollout_parity')
        if not result.success:veto.append('solver_not_converged')
        models[name]=dict(completed=True,theta=theta.tolist(),config=d.asdict(d.config_for(theta)),readout=dict(gain=1.,holdoff_s=.5),
            success=bool(result.success),status=int(result.status),message=str(result.message),nfev=int(result.nfev),njev=int(result.njev),
            residual_calls=budget.used-calls_before,objective=float(2*result.cost),elapsed_s=time.perf_counter()-start,
            scaled_jac_singular_values=np.linalg.svd(result.jac*d.SCALE[None,:],compute_uv=False).tolist(),
            near_bounds=[d.NAMES[j] for j in range(7) if min(theta[j]-d.LOW[j],d.HIGH[j]-theta[j])<=1e-5*(d.HIGH[j]-d.LOW[j])],
            check_veto=veto,rollout_parity_max_abs=parity,proxy=proxy)
        d.save(out/(name+'.json'),models[name]);export_yaml(out/(name+'.yaml'),theta)
        d.save(out/(name+'_calls.json'),trace)
        print('FIT_DONE',name,'calls',budget.used-calls_before,'veto',veto,flush=True)
    finite=[n for n in models if models[n]['completed']]
    eligible=[n for n in finite if not models[n]['check_veto']]
    def rank(n):
        loss=models[n]['proxy']['summary']['check']['loss']
        return (loss['velocity']+LAMBDA_S*loss['prefix_integral']+LAMBDA_W*loss['smooth_worst_regression'],n)
    selected=min(eligible or finite,key=rank) if finite else None
    selection=dict(selected=selected,selection_role='train-check only',
        development_is_diagnostic_only=not bool(eligible),
        check_veto=models[selected]['check_veto'] if selected else ['no_completed_fit'],
        total_residual_calls=budget.used,residual_call_limit=budget.limit,
        max_nfev_per_fit=80,candidates_considered=2,validation_opened=False,test_evaluated=False,
        configs_sha256={n:d.sha(out/(n+'.yaml')) for n in finite},
        candidate_sha256=d.sha(out/(selected+'.json')) if selected else None,
        source_sha256=d.source_hashes())
    d.save(out/'selection.json',selection)
    d.save(out/'results.json',dict(baseline=d.BASE,models=models,selection=selection,
        theta0=d.THETA0.tolist(),bounds=[d.LOW.tolist(),d.HIGH.tolist()],scales=dict(velocity=d.SIGMA.tolist(),prefix=SIGMA_S.tolist()),
        groups=groups,inventory=inventory,baseline_proxy=baseline,test_evaluated=False))
    print(d.json.dumps(selection,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--premise',type=Path,required=True)
    a=p.parse_args();run(a.output,a.premise)

"""Baseline-only premise probe; no fitting and no validation access."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
import data as d


def proxy_table(windows,errors,integrals):
    rows=[]
    for label,key in [('all',None),('group','group'),('phase','phase')]:
        values=['all'] if key is None else sorted({getattr(w,key) for w in windows})
        for value in values:
            ii=[i for i,w in enumerate(windows) if key is None or getattr(w,key)==value]
            e,s=errors[ii],integrals[ii]
            rows.append(dict(kind=label,value=value,windows=len(ii),
                independent_groups=len({windows[i].group for i in ii}),
                rmse_mps=np.sqrt(np.mean(e*e,axis=0)).tolist(),
                signed_bias_mps=np.mean(e,axis=0).tolist(),
                prefix_rmse_m=np.sqrt(np.mean(s*s,axis=0)).tolist(),
                signed_integral_bias_m=np.mean(s,axis=0).tolist()))
    return rows


def main(output):
    output=d.new_dir(output)
    d.save(output/'started.json',d.provenance('baseline_diagnosis'))
    store=d.Store(output/'access.json')
    groups=sorted({r['group'] for r in store.records.values() if r['split']=='train'})
    groups=dict(fitting=sorted(set(groups)-set(groups[::4])),check=groups[::4])
    d.save(output/'train_groups.json',groups)
    windows,inventory=d.collect_windows(store)
    fit=[w for w in windows if w.group in groups['fitting']]
    chk=[w for w in windows if w.group in groups['check']]
    if not windows:
        d.save(output/'diagnosis.json',dict(sufficient_premise=False,reason='no_windows'));return
    e,s,fast=d.proxy_errors(d.THETA0,windows)
    slow=np.stack([d.original_rollout(d.THETA0,w) for w in windows])
    discrepancy=float(np.max(np.abs(fast-slow)))
    if discrepancy>1e-10:raise AssertionError(('full_rollout_mismatch',discrepancy))
    phases=Counter(w.phase for w in windows);affected=np.abs(s[:,-1])>=.10
    affected_groups=sorted({w.group for w,a in zip(windows,affected) if a})
    coverage=dict(fitting_groups=len({w.group for w in fit}),check_groups=len({w.group for w in chk}),
        fitting_windows=len(fit),check_windows=len(chk),phases=dict(phases),
        prefix_bias_windows_ge_0p1m=int(affected.sum()),prefix_bias_groups=affected_groups,
        hypothetical_prefix_outputs=len(windows)*101)
    sufficient=(coverage['fitting_groups']>=8 and coverage['check_groups']>=3
        and len(fit)>=30 and len(chk)>=9 and all(phases[p]>=5 for p in ['traction','coast','braking'])
        and int(affected.sum())>=20 and len(affected_groups)>=3)
    result=dict(**d.provenance('baseline_diagnosis_complete'),coverage=coverage,
        sufficient_premise=sufficient,full_rollout_parity_max_abs_mps=discrepancy,
        actual_candidate_interventions=0,interpretation='Baseline forecast defect versus wheel proxy; not ground truth or demonstrated candidate benefit',
        rows=proxy_table(windows,e,s),inventory=inventory,groups=groups,
        per_window=[dict(bag=w.bag,group=w.group,phase=w.phase,anchor=w.anchor,
            velocity_error_mps=ee.tolist(),prefix_integral_error_m=ss.tolist()) for w,ee,ss in zip(windows,e,s)])
    d.save(output/'diagnosis.json',result)
    print(d.json.dumps({k:result[k] for k in ['sufficient_premise','coverage','full_rollout_parity_max_abs_mps']},indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)

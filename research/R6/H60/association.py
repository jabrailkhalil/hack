"""Preregistered group-LOO associations, never independent-tick statistics."""
import argparse,json,sys,math
from pathlib import Path
import numpy as np
from scipy.stats import rankdata
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Odometry_Failure_Discovery_v1'))
from failure_discovery.common import write_json,write_csv,sha

PREDICTORS={'innovation':'signed','d':'signed','drive_a':'signed','model_residual':'signed',
            'P':'absolute','gain':'absolute','readout_delta':'signed'}

def weights(groups):
    unique,counts=np.unique(groups,return_counts=True);sizes=dict(zip(unique,counts))
    w=np.array([1./sizes[g] for g in groups]);return w/w.sum()

def correlation(x,y,w):
    x=rankdata(x,method='average');y=rankdata(y,method='average')
    x=x-np.sum(w*x);y=y-np.sum(w*y)
    denom=math.sqrt(np.sum(w*x*x)*np.sum(w*y*y))
    return float(np.sum(w*x*y)/denom) if denom>1e-20 else 0.

def single_model(x,y,w):
    mx=np.sum(w*x);sx=math.sqrt(np.sum(w*(x-mx)**2));my=np.sum(w*y)
    if sx<=1e-12:return mx,sx,my,0.
    z=(x-mx)/sx
    beta=np.sum(w*z*(y-my))/(np.sum(w*z*z)+1e-3)
    return mx,sx,my,float(beta)

def analyze(rows):
    rows=sorted(rows,key=lambda r:(r["group"],r["bag"],r["event_id"]))
    assoc=[];folds=[]
    for name,kind in PREDICTORS.items():
        usable=[r for r in rows if not r.get('natural') and r.get('trusted_remaining_integral_10s') is not None
                and r.get('first_trusted_'+name) is not None and math.isfinite(r['first_trusted_'+name])]
        x=np.array([r['first_trusted_'+name] for r in usable]);y=np.array([r['trusted_remaining_integral_10s'] for r in usable])
        if kind=='absolute':y=np.abs(y)
        groups=np.array([r['group'] for r in usable]);gg=np.unique(groups)
        if len(gg)<3:
            assoc.append({'predictor':name,'target':kind,'groups':len(gg),'n':len(y),'passed':False,'reason':'coverage'});continue
        rho=correlation(x,y,weights(groups));errors=[];baseerrors=[];signs=[]
        for group in gg:
            tr=groups!=group;te=~tr;w=weights(groups[tr]);mx,sx,my,beta=single_model(x[tr],y[tr],w)
            pred=my+beta*((x[te]-mx)/sx if sx>1e-12 else np.zeros(te.sum()))
            mse=float(np.mean((pred-y[te])**2));base=float(np.mean((my-y[te])**2))
            rr=correlation(x[tr],y[tr],w);signs.append(np.sign(rr)==np.sign(rho))
            errors.append(mse);baseerrors.append(base)
            folds.append({'predictor':name,'held_out_group':group,'test_n':int(te.sum()),'train_n':int(tr.sum()),
                          'training_rho':rr,'coefficient_standardized':beta,'training_x_mean':mx,'training_x_sd':sx,
                          'training_y_mean':my,'heldout_mse':mse,'intercept_mse':base,
                          'training_rho_sign_matches_full':bool(signs[-1])})
        mse=float(np.mean(errors));bmse=float(np.mean(baseerrors));gain=(bmse-mse)/bmse if bmse>0 else 0.
        stable=float(np.mean(signs))
        passed=abs(rho)>=.30 and stable>=.80 and gain>=.05
        assoc.append({'predictor':name,'target':kind,'groups':len(gg),'n':len(y),'weighted_spearman':rho,
                      'loo_sign_stability':stable,'loo_mse':mse,'intercept_loo_mse':bmse,
                      'loo_mse_improvement_pct':100*gain,'passed':bool(passed),
                      'heldout_groups_improved':sum(a<b for a,b in zip(errors,baseerrors)),
                      'weighted_rank_definition':'ordinary tied ranks, covariance weighted equally per source group'})
    return assoc,folds

def run(root,out):
    summaries=json.loads((root/'SUMMARY.json').read_text());assert summaries['complete']
    rows=[];phases=[]
    import csv
    for s in summaries['bags']:
        p=root/'bags'/s['bag'];rows.extend(json.loads((p/'EPISODES.json').read_text()))
        with (p/'PHASES.csv').open() as f:phases.extend(csv.DictReader(f))
    rows.sort(key=lambda r:(r["group"],r["bag"],r["event_id"]))
    assoc,folds=analyze(rows)
    groups=sorted({r['group'] for r in rows})
    support=[]
    for g in groups:
        rr=[r for r in rows if r['group']==g and not r.get('natural')]
        complete=[r for r in rr if r.get('trusted_remaining_integral_10s') is not None]
        anchors={r['anchor_id'] for r in complete if abs(r['trusted_remaining_integral_10s'])>=.05}
        endcomplete=[r for r in rr if r.get('fault_end_remaining_integral_10s') is not None]
        support.append({'group':g,'episodes':len(rr),'complete_after_trust_10s':len(complete),
            'supporting_anchors':len(anchors),'supported':len(anchors)>=2,
            'mean_abs_after_trust_10s':float(np.mean([abs(r['trusted_remaining_integral_10s']) for r in complete])) if complete else None,
            'mean_abs_after_fault_end_10s':float(np.mean([abs(r['fault_end_remaining_integral_10s']) for r in endcomplete])) if endcomplete else None,
            'mean_abs_terminal_delta_s':float(np.mean([abs(r['terminal_delta_s']) for r in rr])) if rr else None})
    qualifying=sum(x['supported'] for x in support);passed=qualifying>=3 and any(r['passed'] for r in assoc)
    verdict='FOUNDATION_PASSED' if passed else 'FOUNDATION_FAILED'
    numeric=[r for r in assoc if 'loo_mse_improvement_pct' in r]
    strongest=max(numeric,key=lambda r:r['loo_mse_improvement_pct']) if numeric else None
    stable_results=[]
    for g in groups:
        # This is a sensitivity diagnostic, NOT a refit using check or a new candidate.
        reduced=[r for r in rows if r['group']!=g];aa,_=analyze(reduced)
        stable_results.extend([dict(r,omitted_group=g) for r in aa])
    result={'status':verdict,'scientific_verdict':'INCONCLUSIVE' if not passed else 'FOUNDATION_ONLY',
            'candidate_evaluated':False,'bags':len(summaries['bags']),'source_groups_with_episodes':len(groups),
            'episodes':len(rows),'natural_episodes':sum(r.get('natural',False) for r in rows),
            'complete_after_trust_10s':sum(r.get('trusted_remaining_integral_10s') is not None for r in rows),
            'without_first_trusted_pair':sum(r.get('first_trusted_t') is None for r in rows),
            'supporting_groups':qualifying,'strongest_predictor':strongest,'associations':assoc,
            'group_support':support,'integral_max_defect_m':max(r['integral_defect'] for r in rows),
            'exact_velocity_rejoins':sum(r['joined'] for r in rows),
            'exact_full_replay_verifications':[v for s in summaries['bags'] for v in s['replay_checks']],
            'thresholds':{'supporting_groups':3,'anchors_per_group':2,'abs_after_trust_integral_m':.05,
                          'abs_rho':.30,'loo_sign_stability':.80,'loo_mse_improvement_pct':5.},
            'target':'faulted-minus-clean counterfactual velocity integral; not official XYZ error',
            'selection_role':'train-fit only','check_opened':False,'development_opened':False,
            'validation_opened':False,'final_test_opened':False}
    out.mkdir(parents=True,exist_ok=True)
    write_json(out/'RECOVERY_FOUNDATION.json',result)
    write_csv(out/'STATE_ERROR_ASSOCIATION.csv',assoc);write_csv(out/'CV_RESULTS.csv',folds)
    write_csv(out/'GROUP_SUPPORT.csv',support);write_csv(out/'GROUP_OMISSION_SENSITIVITY.csv',stable_results)
    write_csv(out/'RECOVERY_PHASES.csv',phases);write_csv(out/'RECOVERY_EPISODES.csv',rows)
    print(json.dumps({k:v for k,v in result.items() if k not in ('group_support','exact_full_replay_verifications')},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.input,a.output)

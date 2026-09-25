"""Summarize committed round-three evidence; no measurement access or selection tuning."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/research_v5'))
import compare as v5
np = v5.np


def main():
    directory = ROOT/'reports/research_v5'
    data = json.loads((directory/'round3/results.json').read_text())
    decision = v5.decision(data['clean'], data['stress'], data['plan']['candidates'])
    if decision != json.loads((directory/'round3/decision.json').read_text()):
        raise ValueError('Committed decision does not reproduce')
    eligible = [n for n, s in decision.items() if s['eligible']]
    if len(eligible) != 1:
        raise ValueError('This export requires exactly one eligible candidate')
    selected = eligible[0]
    profile = json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())
    if profile['config'] != data['models'][selected]:
        raise ValueError('Export differs from evaluated candidate')
    original = json.loads((ROOT/'reports/final/validation/results.json').read_text())
    original_rows = {r['bag']:r for r in original['clean']}
    for row in data['clean']:
        for receiver, scores in row['receivers'].items():
            a = scores['main']['rmse']
            b = original_rows[row['bag']]['receivers'][receiver]['balanced_physics']['rmse']
            if a != b:
                raise ValueError('Main baseline did not reproduce exactly')
    summary = dict(selected=selected, base_commit=data['plan']['base_commit'],
                   dataset_sha256=v5.ex.Store().plan['dataset_sha256'],
                   validation_run='https://github.com/jabrailkhalil/hack/actions/runs/36163407638',
                   main_reproduced_exactly=True, test_evaluated=False, default_changed=False,
                   acceptance=decision[selected], evaluated_config=data['models'][selected],
                   selection_rounds=3, nonbaseline_candidates_evaluated=10,
                   limitations=['Reused validation selected the model; not independent test evidence',
                                'Scalar distance is not xyz accuracy',
                                'Small scalar-distance regression is retained',
                                'No new long-duration ROS latency benchmark'])
    summary['metrics'] = {}
    for name in ['main',selected]:
        scores=[s[name] for r in data['clean'] for s in r['receivers'].values()]
        usable=[s for s in scores if s['rmse'] is not None]
        fault=[s[name] for r in data['stress'] for s in r['receivers'].values() if s[name]['rmse'] is not None]
        groups={}
        for row in data['clean']:
            for s in row['receivers'].values():
                value=s[name]['distance_surrogate']['reanchored_span_rmse_m']
                if value is not None:groups.setdefault(row['group'],[]).append(value)
        summary['metrics'][name]=dict(
            clean_group_macro_rmse=decision[name]['group_macro_rmse'],
            fault_group_macro_event_rmse=decision[name]['group_macro_fault_event_rmse'],
            pooled_rmse=float(np.sqrt(sum(s['n']*s['rmse']**2 for s in usable)/sum(s['n'] for s in usable))),
            matched_samples=sum(s['n'] for s in usable),
            clean_false_stop_samples=sum(s.get('false_stop_samples',0) for s in scores),
            fault_false_stop_samples=sum(s['false_stop_samples'] for s in fault),
            fault_recovery_missing=sum(s['recovery_s'] is None for s in fault),
            scalar_span_group_macro_rmse=float(np.mean([np.mean(v) for v in groups.values()])))
    rng=np.random.default_rng(20260925)
    summary['descriptive_post_selection_bootstrap']={}
    for label,rows,key in [('clean',data['clean'],'rmse'),('fault',data['stress'],'event_rmse')]:
        groups={}
        for row in rows:
            for scores in row['receivers'].values():
                if scores['main'].get(key) is not None:
                    groups.setdefault(row['group'],[]).append([scores['main'][key],scores[selected][key]])
        pairs=np.array([np.mean(values,axis=0) for values in groups.values()])
        sample=pairs[rng.integers(0,len(pairs),size=(10000,len(pairs)))].mean(axis=1)
        gain=1-sample[:,1]/sample[:,0]
        summary['descriptive_post_selection_bootstrap'][label]=dict(groups=len(pairs),
            gain_interval_95=np.quantile(gain,[.025,.975]).tolist(), independent_significance_test=False)
    v5.ev.save(directory/'selection.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()

"""Isolated decay prototype versus both deployed profiles; validation only."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/research_v5'))
import compare as v5
import prototype_core
sys.path.insert(0,str(ROOT/'tools/research_lock'))
import baseline_core
np=v5.np
PLAN=ROOT/'research/plan_disturbance_decay.json'
OriginalObserver=baseline_core.Observer


def models():
    base=json.loads((ROOT/'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    selected=json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())['config']
    result={'baseline_v2':v5.ex.Config(**selected),'main_v4':v5.ex.Config(**base)}
    plan=json.loads(PLAN.read_text())
    for name,tau in plan['candidates'].items():
        if tau is not None:
            c=v5.ex.Config(**selected);c.decay_tau_s=tau;result[name]=c
    return plan,result


def observer(config):
    if hasattr(config,'decay_tau_s'):
        return prototype_core.Observer(config,decay_tau_s=config.decay_tau_s)
    return OriginalObserver(config)


def replay(events,config,fault=None):
    result=v5.ev.replay(events,config,json.loads(PLAN.read_text())['runtime'],fault)
    v5.PREDICTIONS[id(config)]=result[0]
    return result


def run_bag(bag):
    v5.configuration=models
    v5.replay=replay
    v5.ev.Observer=observer
    return v5.validate_bag(bag)


def distance(rows,name):
    groups={}
    for row in rows:
        for scores in row['receivers'].values():
            value=scores[name]['distance_surrogate']['reanchored_span_rmse_m']
            if value is not None:groups.setdefault(row['group'],[]).append(value)
    return float(np.mean([np.mean(v) for v in groups.values()]))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    plan,config=models();start=time.perf_counter()
    provenance=dict(plan=plan,source_ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        python=platform.python_version(),numpy=np.__version__,test_evaluated=False,
        source_sha256=v5.ev.protected_files(),prototype_sha256=v5.ev.sha(Path(__file__).with_name('prototype_core.py')),
        runner_sha256=v5.ev.sha(__file__),plan_sha256=v5.ev.sha(PLAN),
        aliases={'main':'main_v5 (current optional profile)','main_v4':'current default'},
        configs={n:asdict(c) for n,c in config.items()})
    v5.ev.save(args.output/'started.json',provenance)
    with ProcessPoolExecutor(max_workers=3) as pool:
        result=list(pool.map(run_bag,v5.ex.Store().plan['splits']['validation']))
    clean=[r[0] for r in result];stress=[s for r in result for s in r[1]]
    names=['main','main_v4','v5_decay_2s','v5_decay_5s']
    decision=v5.decision(clean,stress,names)
    base_distance=distance(clean,'main')
    for name in names:
        d=decision[name];d['scalar_span_group_macro_rmse']=distance(clean,name)
        d['scalar_relative_change']=d['scalar_span_group_macro_rmse']/base_distance-1
        if d['scalar_relative_change']>.005:d['rejection_reasons'].append('scalar_regression')
        for row in stress:
            for s in row['receivers'].values():
                if s['main']['rmse'] is not None and s['main']['recovery_s'] is not None and s[name]['recovery_s'] is None:
                    d['rejection_reasons'].append('lost_recovery')
        d['rejection_reasons']=sorted(set(d['rejection_reasons']));d['eligible']=not d['rejection_reasons']
    v5.ev.save(args.output/'results.json',dict(**provenance,clean=clean,stress=stress,access=[a for r in result for a in r[2]],elapsed_s=time.perf_counter()-start))
    v5.ev.save(args.output/'decision.json',decision)
    print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()

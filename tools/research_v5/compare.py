"""Paired main-vs-candidate validation using the unchanged v4 replay and v3 split."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/finalization'))
import evaluate as ev
ex = ev.ex
np = ev.np
PLAN = ROOT / 'research/plan_v5.json'


def configuration():
    plan = json.loads(PLAN.read_text())
    base = json.loads((ROOT / 'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    models = {('baseline_v2' if n == 'main' else n): ex.Config(**(base | changes))
              for n, changes in plan['candidates'].items()}
    return plan, models


def replay(events, config, fault=None):
    return ev.replay(events, config, json.loads(PLAN.read_text())['operational'], fault)


def validate_bag(bag):
    plan, models = configuration()
    store = ex.Store()
    events, refs = store.load(bag, 'validation')
    ex.replay = replay
    clean = dict(bag=bag, group=store.records[bag]['group'], **ex.compare(events, refs, models))
    stress = []
    grid = ex.grid_channels(events)
    if grid is not None:
        t, u, f, r, valid = grid
        indices = np.flatnonzero(valid & ((f+r)/2 > 2) & (t > max(25, .1*t[-1])) & (t < t[-1]-25))
        if len(indices):
            anchor = float(t[indices[0]])
            for kind, duration in [('bias', 5.), ('dropout', 5.), ('dropout', 10.), ('lock', 3.)]:
                window = events[(events[:, 0] >= anchor-20) & (events[:, 0] <= anchor+duration+10.1)]
                fault = dict(kind=kind, start=anchor, end=anchor+duration)
                stress.append(dict(bag=bag, group=store.records[bag]['group'], fault=fault,
                                   **ex.compare(window, refs, models, fault)))
    # The legacy comparison helper requires this alias; make public evidence explicit.
    for row in [clean] + stress:
        row['counts']['main'] = row['counts'].pop('baseline_v2')
        for scores in row['receivers'].values():
            scores['main'] = scores.pop('baseline_v2')
    print('VALIDATED', bag, flush=True)
    return clean, stress, store.access


def macro(rows, name, key):
    groups = {}
    for row in rows:
        for scores in row['receivers'].values():
            value = scores[name].get(key)
            if value is not None:
                groups.setdefault(row['group'], []).append(value)
    return float(np.mean([np.mean(v) for v in groups.values()])) if groups else None


def decision(clean, stress, names):
    base = macro(clean, 'main', 'rmse')
    fault_base = macro(stress, 'main', 'event_rmse')
    result = {}
    for name in names:
        score = macro(clean, name, 'rmse')
        fault_score = macro(stress, name, 'event_rmse')
        reasons = []
        if score is None or fault_score is None:
            reasons.append('missing_aggregate')
        else:
            if score > base * .98 and fault_score > fault_base * .95:
                reasons.append('insufficient_gain')
            if score > base * 1.01 or fault_score > fault_base * 1.01:
                reasons.append('aggregate_regression')
        for row in clean:
            for receiver, scores in row['receivers'].items():
                a, b = scores[name], scores['main']
                if b['rmse'] is not None and (a['rmse'] is None or a['rmse'] > b['rmse'] + max(.01, .1*b['rmse'])):
                    reasons.append('bag_regression:' + row['bag'] + '/' + receiver)
        for row in clean + stress:
            if row['counts'][name]['causal_errors']:
                reasons.append('causality')
            for scores in row['receivers'].values():
                a, b = scores[name], scores['main']
                if a['n'] < b['n'] or a['coverage'] < b['coverage']:
                    reasons.append('coverage')
                if a.get('false_stop_samples', 0) > b.get('false_stop_samples', 0):
                    reasons.append('false_stops')
        result[name] = dict(group_macro_rmse=score, group_macro_fault_event_rmse=fault_score,
                            clean_gain=1-score/base if score is not None else None,
                            fault_gain=1-fault_score/fault_base if fault_score is not None else None,
                            rejection_reasons=sorted(set(reasons)), eligible=not reasons)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve prior evidence; choose a fresh directory')
    args.output.mkdir(parents=True)
    plan, models = configuration()
    store = ex.Store()
    start = time.perf_counter()
    provenance = dict(plan=plan, plan_sha256=ev.sha(PLAN), source_sha256=ev.protected_files(),
                      runner_sha256=ev.sha(__file__), source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                      python=platform.python_version(), numpy=np.__version__, test_evaluated=False)
    ev.save(args.output/'started.json', provenance)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(validate_bag, store.plan['splits']['validation']))
    clean = [r[0] for r in rows]
    stress = [s for r in rows for s in r[1]]
    result = dict(**provenance, clean=clean, stress=stress, access=[a for r in rows for a in r[2]],
                  elapsed_s=time.perf_counter()-start, models={('main' if n=='baseline_v2' else n):asdict(c) for n,c in models.items()})
    ev.save(args.output/'results.json', result)
    summary = decision(clean, stress, plan['candidates'])
    ev.save(args.output/'decision.json', summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()

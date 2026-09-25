"""Paired, bounded v6 search. Reused validation only; never loads final-test data.

Metric functions and fault locations are the published v4 definitions. An old
parameter alias inside score() is renamed only after scoring. All baselines and
rejected candidates are preserved; this script never changes the ROS default.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/finalization'))
import evaluate as ev
ex, np = ev.ex, ev.np
PLAN = ROOT / 'research/plan_v6.json'
ALIASES = {'baseline_v2': 'v4_default', 'balanced_physics': 'v5_adaptive_05s'}


def configurations():
    plan = json.loads(PLAN.read_text())
    base = json.loads((ROOT / 'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    adaptive = base | {'adaptation_tau_s': .5}
    models = {'baseline_v2': ex.Config(**base), 'balanced_physics': ex.Config(**adaptive)}
    for hypothesis in plan['hypotheses']:
        models[hypothesis['id']] = ex.Config(**(adaptive | {'wheel_projection_gain': hypothesis['wheel_projection_gain']}))
    return models


def validate_bag(bag):
    store = ex.Store()
    events, refs = store.load(bag, 'validation')  # gate BEFORE SQLite IO
    models = configurations()
    operational = dict(rate_hz=20., alignment_delay_s=0.)
    clean = dict(bag=bag, group=store.records[bag]['group'], **ev.score(events, refs, models, operational))
    stress = []
    grid = ex.grid_channels(events)
    if grid is not None:
        t, u, f, r, valid = grid
        indices = np.flatnonzero(valid & ((f+r)/2 > 2.) & (t > max(25., .1*t[-1])) & (t < t[-1]-25.))
        if len(indices):
            anchor = float(t[indices[0]])
            for kind, duration in [('bias', 5.), ('dropout', 5.), ('dropout', 10.), ('lock', 3.)]:
                fault = dict(kind=kind, start=anchor, end=anchor+duration)
                window = events[(events[:, 0] >= anchor-20) & (events[:, 0] <= anchor+duration+10.1)]
                stress.append(dict(bag=bag, group=store.records[bag]['group'], fault=fault,
                                   **ev.score(window, refs, models, operational, fault)))
    for row in [clean] + stress:
        for internal, public in ALIASES.items():
            row['runtime'][public] = row['runtime'].pop(internal)
            for scores in row['receivers'].values():
                scores[public] = scores.pop(internal)
    return clean, stress, store.access


def metric_value(metrics, key):
    if key == 'distance':
        return metrics.get('distance_surrogate', {}).get('reanchored_span_rmse_m')
    return metrics.get(key)


def macro(rows, name, key):
    groups = {}
    for row in rows:
        for scores in row['receivers'].values():
            value = metric_value(scores[name], key)
            if value is not None:
                groups.setdefault(row['group'], []).append(value)
    return float(np.mean([np.mean(v) for v in groups.values()])) if groups else None


def total(rows, name, key):
    return sum(scores[name].get(key, 0) for row in rows for scores in row['receivers'].values())


def unrecovered(rows, name):
    return sum(m.get('event_rmse') is not None and m.get('recovery_s') is None
               for row in rows for scores in row['receivers'].values() for m in [scores[name]])


def summary(clean, stress, name):
    n = total(clean, name, 'n')
    squares = sum(s[name]['rmse']**2*s[name]['n'] for r in clean for s in r['receivers'].values() if s[name]['rmse'] is not None)
    return dict(clean_rmse=macro(clean, name, 'rmse'), fault_rmse=macro(stress, name, 'event_rmse'),
                distance_rmse=macro(clean, name, 'distance'), samples=n, pooled_rmse=math.sqrt(squares/n) if n else None,
                false_stops_clean=total(clean, name, 'false_stop_samples'),
                false_stops_fault=total(stress, name, 'false_stop_samples'), unrecovered=unrecovered(stress, name))


def reproduce_published_v5(clean):
    """Check BOTH baselines against measured main, not against a refitted baseline."""
    old = json.loads((ROOT/'reports/research_v5/round3/results.json').read_text())
    by_bag = {r['bag']: r for r in old['clean']}
    maximum, comparisons = 0., 0
    for row in clean:
        for receiver, metrics in row['receivers'].items():
            for new, previous in [('v4_default', 'main'), ('v5_adaptive_05s', 'adaptation_05s')]:
                m, p = metrics[new], by_bag[row['bag']]['receivers'][receiver][previous]
                for key in ['rmse', 'mae', 'bias', 'p95', 'n', 'coverage', 'false_stop_samples']:
                    a, b = m.get(key), p.get(key)
                    if a is None or b is None:
                        if a != b:
                            raise AssertionError(('baseline_missingness', row['bag'], receiver, key))
                    else:
                        error = abs(a-b); maximum = max(maximum, error); comparisons += 1
                        if error > 1e-10:
                            raise AssertionError(('baseline_mismatch', row['bag'], receiver, new, key, a, b))
    return dict(compared_numeric_fields=comparisons, max_absolute_delta=maximum, passed=True)


def decide(clean, stress, names):
    entries = {name: summary(clean, stress, name) for name in names}
    champion = 'v5_adaptive_05s'
    base = entries[champion]
    for name, s in entries.items():
        reasons = []
        s['clean_gain_vs_v5'] = 1-s['clean_rmse']/base['clean_rmse']
        s['fault_gain_vs_v5'] = 1-s['fault_rmse']/base['fault_rmse']
        s['distance_change_vs_v5'] = s['distance_rmse']/base['distance_rmse']-1
        if name not in ('v4_default', champion):
            if s['clean_gain_vs_v5'] < .02 and s['fault_gain_vs_v5'] < .05:
                reasons.append('insufficient_gain')
            if s['clean_gain_vs_v5'] < -.005 or s['fault_gain_vs_v5'] < -.005:
                reasons.append('aggregate_regression')
            if s['distance_change_vs_v5'] > .01:
                reasons.append('distance_regression')
            if s['unrecovered'] > base['unrecovered']:
                reasons.append('unrecovered_increase')
            for row in clean:
                for receiver, scores in row['receivers'].items():
                    a, b = scores[name], scores[champion]
                    if b['rmse'] is not None and (a['rmse'] is None or a['rmse'] > b['rmse']+max(.005, .05*b['rmse'])):
                        reasons.append('bag_regression:'+row['bag']+'/'+receiver)
            for row in clean + stress:
                if row['runtime'][name]['causal_errors'] or row['runtime'][name]['resets']:
                    reasons.append('causality_or_reset')
                for receiver, scores in row['receivers'].items():
                    a, b = scores[name], scores[champion]
                    if a['n'] != b['n'] or a['coverage'] != b['coverage']:
                        reasons.append('coverage')
                    if a.get('false_stop_samples', 0) > b.get('false_stop_samples', 0):
                        reasons.append('false_stops:'+row['bag']+'/'+receiver)
            s['eligible'] = not reasons
        else:
            s['eligible'] = False  # baselines are not proposed innovations
        s['rejection_reasons'] = sorted(set(reasons))
    eligible = [name for name, s in entries.items() if s['eligible']]
    selected = min(eligible, key=lambda n: entries[n]['clean_rmse']) if eligible else champion
    # Fallback is only the already accepted v5 profile, with its published gate.
    v4 = entries['v4_default']
    if not eligible and not (base['fault_rmse'] <= v4['fault_rmse']*.95 and
                            base['clean_rmse'] <= v4['clean_rmse']*1.01 and
                            base['distance_rmse'] <= v4['distance_rmse']*1.01 and
                            base['false_stops_clean'] <= v4['false_stops_clean'] and
                            base['false_stops_fault'] <= v4['false_stops_fault']):
        selected = 'v4_default'
    return dict(selected=selected, candidates=entries, test_evaluated=False,
                scope='adaptive selection on reused validation; NOT independent generalization evidence',
                promotion_requires='passing ROS/default/offline integrity checks; runner never changes default')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError('workers must be between 1 and 8')
    args.output.mkdir(parents=True, exist_ok=False)
    plan = json.loads(PLAN.read_text()); store = ex.Store(); started = time.perf_counter()
    provenance = dict(plan=plan, plan_sha256=ev.sha(PLAN), source_sha256=ev.protected_files(),
        runner_sha256=ev.sha(__file__), source_ref=os.environ.get('GITHUB_SHA', 'local-working-copy'),
        python=platform.python_version(), numpy=np.__version__, test_evaluated=False)
    ev.save(args.output/'started.json', provenance)
    clean, stress, access = [], [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for c, faults, journal in pool.map(validate_bag, store.plan['splits']['validation']):
            clean.append(c); stress.extend(faults); access.extend(journal)
            ev.save(args.output/'bags'/(c['bag']+'.json'), dict(clean=c, stress=faults))
            ev.save(args.output/'access.json', dict(test_evaluated=False, access=access))
            print('CHECKPOINT', c['bag'], flush=True)
    reproduction = reproduce_published_v5(clean)
    names = [ALIASES.get(n,n) for n in configurations()]
    result = dict(**provenance, clean=clean, stress=stress, baseline_reproduction=reproduction,
                  elapsed_s=time.perf_counter()-started,
                  models={ALIASES.get(n,n):asdict(c) for n,c in configurations().items()})
    ev.save(args.output/'results.json', result)
    decision = decide(clean, stress, names); ev.save(args.output/'decision.json', decision)
    print(json.dumps(decision, indent=2), flush=True)


if __name__ == '__main__':
    main()

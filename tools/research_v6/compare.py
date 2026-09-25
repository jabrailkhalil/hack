"""Paired validation against both profiles in main 2f785136; never opens test bags.

The immutable v4 ZIP supplies the baseline core, whose Git blob is identical to
core.py in that main commit. All candidates use the unchanged main evaluator,
reference matching, fault injection, arrival order and output time grid.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
import types
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/finalization'))
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config, Observer

BASE_COMMIT = '2f7851364c6afe9786fad040e0938454d8b0d210'
BASE_CORE_BLOB = 'f6fc8ecd0b4e16018d814407b1944ce26ea550b0'
PINNED_FILES = {'src/reserve_odometry/reserve_odometry/timeline.py': 'ed63b44dede078cb3cde501bd1e5559260763c56ac9b832f39924c1d97b0bdbf', 'src/reserve_odometry/config/default.yaml': 'a29d075cbcca235a1cf5ab1f79a0a992f70ba788e729b452f732c273932eeb0e', 'src/reserve_odometry/config/adaptive_v5.json': '3b84e6eb09262ba7a24771e5a56e0aa3ecb89c67f18e501cd0d0366514e99da1', 'src/reserve_odometry/config/candidates_v3/balanced_physics.json': '68b81682f9ac48d11bf7d8e67418a45de546ab35526954c5f6fc3eda2d7ec425', 'tools/finalization/evaluate.py': 'f6a19a1727274ca88e1fe1a9fb76d31dbc8ce4e9bbabf669c488f053d76caec7', 'tools/research_v3/experiment.py': '95a398003530454457bacb2096fb6bc9d0d5ee32520420c43a9ebeb406376aa0', 'tools/export_bags.py': '696f6bdbf853dac4d4fe6286f6a7f4742f4aea5b1bc508efda52f5bc179c3b66', 'research/split_v3.json': '20928a29daad2b4178ddb92e2a4d9ddb347952f6c03845802a8d82fff7da5ae0', 'research/plan_v3.json': 'ddbc1130e214c3d338b3d292232391d3a329a0fd5f13a090027452ae070271b3'}
NAMES = ('main', 'main_v5', 'candidate')
OPS = {'rate_hz': 20., 'alignment_delay_s': 0.}


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def pinned_core():
    with zipfile.ZipFile(ROOT / 'submission/dist/reserve-odometry-v4.zip') as archive:
        raw = archive.read('reserve-odometry-v4/src/reserve_odometry/reserve_odometry/core.py')
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob != BASE_CORE_BLOB:
        raise ValueError('Archived core is not the pinned current-main estimator')
    mod = types.ModuleType('paired_v6_main_core')
    sys.modules[mod.__name__] = mod
    exec(compile(raw, '<verified-main-core>', 'exec'), mod.__dict__)
    return mod


def models():
    for path, expected in PINNED_FILES.items():
        if ev.sha(ROOT / path) != expected:
            raise ValueError('Pinned baseline/evaluator changed: ' + path)
    old = pinned_core()
    # configuration() also verifies default.yaml against the fitted physics JSON.
    _, operations = ev.configuration()
    if operations != OPS:
        raise ValueError('The comparison requires unchanged 20 Hz / zero-delay operation')
    cfg = ROOT / 'src/reserve_odometry/config'
    base = json.loads((cfg / 'candidates_v3/balanced_physics.json').read_text())['config']
    v5 = json.loads((cfg / 'adaptive_v5.json').read_text())['config']
    if v5 != dict(base, adaptation_tau_s=.5):
        raise ValueError('Baseline v5 differs from pinned main profile')
    candidate = json.loads((cfg / 'time_aligned_v6.json').read_text())['config']
    if candidate != dict(v5, wheel_time_compensation=1.):
        raise ValueError('Selected candidate changed: run a new experiment, not this confirmation')
    return {'main': (old.Observer, old.Config(**base)),
            'main_v5': (old.Observer, old.Config(**v5)),
            'candidate': (Observer, Config(**candidate))}


def predict(events, model, fault=None):
    observer, config = model
    previous = ev.Observer
    try:
        ev.Observer = observer
        return ev.replay(events, config, OPS, fault)
    finally:
        ev.Observer = previous


def compare(events, refs, model_set, fault=None, check_disabled=False):
    arrays, runtime = {}, {}
    for name, model in model_set.items():
        arrays[name], runtime[name] = predict(events, model, fault)
    base = arrays['main']
    t = base[:, 0]
    for name, a in arrays.items():
        if a.shape != base.shape or not np.array_equal(a[:, 0], t):
            raise AssertionError('Output schedule changed: ' + name)
        if runtime[name]['causal_errors']:
            raise AssertionError('Future input used: ' + name)
    if check_disabled:
        for name in ('main', 'main_v5'):
            model = (Observer, Config(**asdict(model_set[name][1]), wheel_time_compensation=0.))
            disabled, info = predict(events, model, fault)
            if not np.array_equal(disabled, arrays[name], equal_nan=True) or info != runtime[name]:
                raise AssertionError('Disabled compensation differs from pinned main: ' + name)
    receivers = {}
    for receiver, values in refs.items():
        target = ev.ex.match(values, t)
        mask = np.isfinite(target)
        if fault:
            mask &= (t >= fault['start']) & (t < fault['end'] + 10.)
        scores = {}
        for name, a in arrays.items():
            m = ev.ex.metrics(t, a[:, 1], target, mask)
            m['false_stop_samples'] = int(np.sum(mask & (target > 1.) & (a[:, 5] > 0)))
            if fault:
                m['event_rmse'] = ev.ex.metrics(t, a[:, 1], target, mask & (t < fault['end']))['rmse']
                good = mask & (t >= fault['end']) & (np.abs(a[:, 1] - target) < .25)
                runs = np.convolve(good.astype(int), np.ones(20, int), mode='valid') if len(t) >= 20 else np.array([])
                hits = np.flatnonzero(runs == 20)
                m['recovery_s'] = float(t[hits[0]] - fault['end']) if len(hits) else None
            else:
                m['distance_surrogate'] = ev.distance_surrogate(a, target)
            scores[name] = m
        receivers[receiver] = scores
    return dict(receivers=receivers, runtime=runtime, outputs=len(t), disabled_compatibility_checked=check_disabled)


def fault_windows(events):
    """Exactly the fault placement and warm-up window of the main v4 evaluator."""
    grid = ev.ex.grid_channels(events)
    if grid is None:
        return
    t, u, f, r, valid = grid
    indices = np.flatnonzero(valid & ((f + r) / 2 > 2) & (t > max(25., .1 * t[-1])) & (t < t[-1] - 25.))
    if len(indices):
        anchor = float(t[indices[0]])
        for kind, duration in [('bias', 5.), ('dropout', 5.), ('dropout', 10.), ('lock', 3.)]:
            fault = dict(kind=kind, start=anchor, end=anchor + duration)
            window = events[(events[:, 0] >= anchor - 20.) & (events[:, 0] <= anchor + duration + 10.1)]
            yield fault, window


def worker(args):
    bag, data_root, output, check_disabled = args
    store = ev.ex.Store(data_root)
    if bag not in store.plan['splits']['validation']:
        raise PermissionError('Only validation measurements are permitted')
    # Store enforces role before opening the DB and verifies its frozen checksum.
    events, refs = store.load(bag, 'validation')
    model_set = models()
    metadata = dict(bag=bag, group=store.records[bag]['group'], role='validation')
    clean = dict(**metadata, **compare(events, refs, model_set, check_disabled=check_disabled))
    stress = [dict(**metadata, fault=fault, **compare(window, refs, model_set, fault))
              for fault, window in fault_windows(events)]
    result = dict(clean=clean, stress=stress, access=store.access)
    save(output / 'bags' / (bag + '.json'), result)
    print(bag, 'outputs', clean['outputs'], 'faults', len(stress), flush=True)
    return result


def mean(values):
    return float(np.mean(values)) if len(values) else None


def aggregate(clean, stress):
    result = {}
    for name in NAMES:
        groups, distances, faults = defaultdict(list), defaultdict(list), defaultdict(list)
        n, squares, stops, fault_stops, missing = 0, 0., 0, 0, 0
        recoveries, no_reference = [], []
        for row in clean:
            for receiver, models_ in row['receivers'].items():
                m = models_[name]
                stops += m['false_stop_samples']
                if m['rmse'] is not None:
                    groups[row['group']].append(m['rmse'])
                    n += m['n']
                    squares += m['rmse'] ** 2 * m['n']
                else:
                    no_reference.append(row['bag'] + '/' + receiver)
                d = m['distance_surrogate']['reanchored_span_rmse_m']
                if d is not None:
                    distances[row['group']].append(d)
        for row in stress:
            for models_ in row['receivers'].values():
                m = models_[name]
                fault_stops += m['false_stop_samples']
                if m['event_rmse'] is not None:
                    faults[row['group']].append(m['event_rmse'])
                    if m['recovery_s'] is None:
                        missing += 1
                    else:
                        recoveries.append(m['recovery_s'])
        result[name] = dict(macro_rmse=mean([mean(v) for v in groups.values()]),
                            pooled_rmse=math.sqrt(squares / n) if n else None, n=n,
                            distance_macro=mean([mean(v) for v in distances.values()]),
                            false_stops=stops, fault_macro=mean([mean(v) for v in faults.values()]),
                            fault_false_stops=fault_stops, fault_missing_recovery=missing,
                            mean_recovery_s=mean(recoveries),
                            groups={k: mean(v) for k, v in groups.items()}, missing_bag_receivers=no_reference)
    return result


def decision(clean, summary):
    reasons, paired = [], {}
    candidate = summary['candidate']
    for name in ('main', 'main_v5'):
        base = summary[name]
        if candidate['macro_rmse'] is None or base['macro_rmse'] is None or candidate['macro_rmse'] >= base['macro_rmse']:
            reasons.append(name + ': no clean gain')
        for metric, limit in [('fault_macro', 1.05), ('distance_macro', 1.01)]:
            if candidate[metric] is None or base[metric] is None or candidate[metric] > base[metric] * limit:
                reasons.append(name + ': ' + metric)
        for metric in ('false_stops', 'fault_false_stops', 'fault_missing_recovery'):
            if candidate[metric] > base[metric]:
                reasons.append(name + ': ' + metric)
        wins, regressions, ties = 0, 0, 0
        for row in clean:
            for receiver, scores in row['receivers'].items():
                b, c = scores[name], scores['candidate']
                if b['n'] != c['n']:
                    reasons.append(name + ': coverage differs')
                if b['rmse'] is None or c['rmse'] is None:
                    if b['rmse'] != c['rmse']:
                        reasons.append(name + ': reference availability differs')
                    continue
                wins += c['rmse'] < b['rmse']
                regressions += c['rmse'] > b['rmse']
                ties += c['rmse'] == b['rmse']
                if c['rmse'] > b['rmse'] + max(.01, .1 * b['rmse']):
                    reasons.append(name + ': clean regression ' + row['bag'] + '/' + receiver)
        paired[name] = dict(improved=int(wins), worse=int(regressions), tied=int(ties))
    return dict(eligible=not reasons, rejection_reasons=reasons, paired=paired,
                qualification='Previously reused validation; not an independent held-out test')


def run(output, data_root, workers, check_disabled):
    if workers < 1:
        raise ValueError('workers must be positive')
    store = ev.ex.Store(data_root)
    model_set = models()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'bags').mkdir()
    paths = [Path(__file__), ROOT / 'src/reserve_odometry/reserve_odometry/core.py',
             ROOT / 'src/reserve_odometry/reserve_odometry/timeline.py',
             ROOT / 'tools/finalization/evaluate.py', ROOT / 'tools/research_v3/experiment.py',
             ROOT / 'tools/export_bags.py', ROOT / 'research/split_v3.json', ROOT / 'research/plan_v3.json']
    paths += list((ROOT / 'src/reserve_odometry/config').glob('*v[56].json'))
    plan = dict(base_commit=BASE_COMMIT, baseline_core_git_blob=BASE_CORE_BLOB,
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                models={name: asdict(m[1]) for name, m in model_set.items()}, operational=OPS,
                source_sha256={str(p.relative_to(ROOT)): ev.sha(p) for p in paths},
                split_sha256=store.plan['manifest_sha256'],
                python=platform.python_version(), numpy=np.__version__, workers=workers,
                role='validation', test_evaluated=False, check_disabled=check_disabled,
                selection='Selected on development, fixed before the original validation; this runner does not select or fit parameters')
    save(output / 'started.json', plan)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(worker, [(bag, data_root, output, check_disabled) for bag in store.plan['splits']['validation']]))
    clean = [r['clean'] for r in rows]
    stress = [s for r in rows for s in r['stress']]
    summary = aggregate(clean, stress)
    report = dict(plan=plan, summary=summary, clean=clean, stress=stress,
                  decision=decision(clean, summary), elapsed_s=time.perf_counter() - started)
    save(output / 'access.json', [a for r in rows for a in r['access']])
    save(output / 'results.json', report)
    print(json.dumps(dict(summary=summary, decision=report['decision']), indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=ROOT / 'dataset/data')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--check-disabled', action='store_true', help='Additionally replay both main profiles with the new feature disabled')
    args = parser.parse_args()
    report = run(args.output, args.data_root, args.workers, args.check_disabled)
    if not report['decision']['eligible']:
        raise SystemExit('Candidate did not pass the documented comparison gates')

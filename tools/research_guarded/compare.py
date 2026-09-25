"""Reproduce guarded-readout validation against pinned active main efc473e.

Only the existing validation role is allowed; no fitting or test DB access.
Source-time grid, fault placement, matching and metric definitions are unchanged.
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
from functools import partial

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/finalization'))
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config, Observer
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

BASE_COMMIT = 'efc473e415795d64770ef9dfa4f1bc417078da32'
BASE_CORE_BLOB = '1d698940cfac7de9d914e32cacf3e1f8fa618372'
PINNED_FILES = {'src/reserve_odometry/reserve_odometry/timeline.py': 'ed63b44dede078cb3cde501bd1e5559260763c56ac9b832f39924c1d97b0bdbf', 'src/reserve_odometry/config/default.yaml': 'dae5f5c80cd87e968b1e838c5b0d25cc531f816949b1fd2a59dd65e8e93efaec', 'src/reserve_odometry/config/adaptive_v5.json': '3b84e6eb09262ba7a24771e5a56e0aa3ecb89c67f18e501cd0d0366514e99da1', 'src/reserve_odometry/config/candidates_v3/balanced_physics.json': '68b81682f9ac48d11bf7d8e67418a45de546ab35526954c5f6fc3eda2d7ec425', 'tools/finalization/evaluate.py': 'f6a19a1727274ca88e1fe1a9fb76d31dbc8ce4e9bbabf669c488f053d76caec7', 'tools/research_v3/experiment.py': '95a398003530454457bacb2096fb6bc9d0d5ee32520420c43a9ebeb406376aa0', 'tools/export_bags.py': '696f6bdbf853dac4d4fe6286f6a7f4742f4aea5b1bc508efda52f5bc179c3b66', 'research/split_v3.json': '20928a29daad2b4178ddb92e2a4d9ddb347952f6c03845802a8d82fff7da5ae0', 'research/plan_v3.json': 'ddbc1130e214c3d338b3d292232391d3a329a0fd5f13a090027452ae070271b3'}
NAMES = ('main', 'candidate')
PINNED_FILES['src/reserve_odometry/reserve_odometry/core.py'] = '6e2063666eea57a8065f405e0953797b3036cc0b7204b18bfafe5458bce5b1db'
SELECTED_MODULE_SHA256 = '6303c1230ff800e370875f7238912e47a0564da1b21d42ccf8f417f75b2e05e0'
OPS = {'rate_hz': 20., 'alignment_delay_s': 0.}


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


class CheckedGuardedObserver(GuardedReadoutObserver):
    """Replay an independent baseline and assert every inner field each tick."""
    def __init__(self, config, **kwargs):
        self._reference = Observer(config)
        super().__init__(config, **kwargs)

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self._reference.reset(**kwargs)

    def step(self, *args, **kwargs):
        result = super().step(*args, **kwargs)
        self._reference.step(*args, **kwargs)
        for key, value in vars(self._reference).items():
            if key != 'last_estimate' and value != getattr(self, key):
                raise AssertionError('Readout fed back into baseline state: ' + key)
        return result


def models(check_inner=False):
    for path, expected in PINNED_FILES.items():
        if ev.sha(ROOT / path) != expected:
            raise ValueError('Pinned baseline/evaluator changed: ' + path)
    if ev.sha(ROOT / 'src/reserve_odometry/reserve_odometry/guarded_readout.py') != SELECTED_MODULE_SHA256:
        raise ValueError('Selected code changed: record a new experiment instead of overwriting evidence')
    cfg = ROOT / 'src/reserve_odometry/config'
    base = json.loads((cfg / 'adaptive_v5.json').read_text())['config']
    profile = json.loads((cfg / 'guarded_readout_v7.json').read_text())
    active = {}
    for line in (cfg / 'default.yaml').read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and key.startswith('model.'):
            active[key[6:]] = float(value)
    if active != base or profile['config'] != base:
        raise ValueError('Physical parameters differ from the current-main baseline')
    if profile['readout'] != {'gain': 1.0, 'holdoff_s': 0.5}:
        raise ValueError('Readout options differ from the pre-validation selection')
    cls = CheckedGuardedObserver if check_inner else GuardedReadoutObserver
    return {'main': (Observer, Config(**base)),
            'candidate': (partial(cls, readout=ReadoutConfig(**profile['readout'])), Config(**base))}


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
        model = (partial(GuardedReadoutObserver, readout=ReadoutConfig(gain=0.0)), model_set['main'][1])
        disabled, info = predict(events, model, fault)
        if not np.array_equal(disabled, arrays['main'], equal_nan=True) or info != runtime['main']:
            raise AssertionError('Disabled readout differs from pinned main')
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
    bag, data_root, output, check_disabled, check_inner = args
    store = ev.ex.Store(data_root)
    if bag not in store.plan['splits']['validation']:
        raise PermissionError('Only validation measurements are permitted')
    # Store enforces role before opening the DB and verifies its frozen checksum.
    events, refs = store.load(bag, 'validation')
    model_set = models(check_inner)
    metadata = dict(bag=bag, group=store.records[bag]['group'], role='validation')
    clean = dict(**metadata, **compare(events, refs, model_set, check_disabled=check_disabled))
    stress = [dict(**metadata, fault=fault, **compare(window, refs, model_set, fault, check_disabled=check_disabled))
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


def decision(clean, stress, summary):
    """Exact existing main limits; missing evidence cannot produce a winner."""
    reasons = []
    base, candidate = summary['main'], summary['candidate']
    required = ('macro_rmse', 'fault_macro', 'distance_macro')
    if any(base[k] is None or candidate[k] is None or not math.isfinite(base[k])
           or not math.isfinite(candidate[k]) or base[k] <= 0 for k in required):
        return dict(eligible=False, rejection_reasons=['missing or invalid aggregate evidence'])
    clean_gain = 1 - candidate['macro_rmse'] / base['macro_rmse']
    fault_gain = 1 - candidate['fault_macro'] / base['fault_macro']
    if clean_gain < .02 and fault_gain < .05:
        reasons.append('insufficient gain: need 2% clean or 5% fault')
    for metric, limit in [('macro_rmse', 1.005), ('fault_macro', 1.005), ('distance_macro', 1.01)]:
        if candidate[metric] > base[metric] * limit:
            reasons.append('aggregate regression: ' + metric)
    for metric in ('false_stops', 'fault_false_stops', 'fault_missing_recovery'):
        if candidate[metric] > base[metric]:
            reasons.append('increased ' + metric)
    wins = worse = ties = 0
    for rows, clean_role in ((clean, True), (stress, False)):
        for row in rows:
            if row['runtime']['main'] != row['runtime']['candidate']:
                reasons.append('baseline runtime counters changed: ' + row['bag'])
            for receiver, scores in row['receivers'].items():
                b, c = scores['main'], scores['candidate']
                if b['n'] != c['n'] or b['coverage'] != c['coverage']:
                    reasons.append('coverage differs: ' + row['bag'] + '/' + receiver)
                if b['rmse'] is None or c['rmse'] is None:
                    if b['rmse'] != c['rmse']:
                        reasons.append('reference availability differs')
                    continue
                if clean_role:
                    wins += c['rmse'] < b['rmse']
                    worse += c['rmse'] > b['rmse']
                    ties += c['rmse'] == b['rmse']
                    if c['rmse'] > b['rmse'] + max(.005, .05 * b['rmse']):
                        reasons.append('per-bag clean regression: ' + row['bag'] + '/' + receiver)
    return dict(eligible=not reasons, rejection_reasons=reasons,
                clean_gain=clean_gain, fault_gain=fault_gain,
                paired=dict(improved=int(wins), worse=int(worse), tied=int(ties)),
                qualification='Reused validation, not independent test; not a claim of statistical significance')


def run(output, data_root, workers, check_disabled=False, check_inner=False):
    if workers < 1:
        raise ValueError('workers must be positive')
    store = ev.ex.Store(data_root)
    model_set = models(check_inner)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'bags').mkdir()
    paths = [Path(__file__), ROOT / 'src/reserve_odometry/reserve_odometry/core.py',
             ROOT / 'src/reserve_odometry/reserve_odometry/timeline.py',
             ROOT / 'tools/finalization/evaluate.py', ROOT / 'tools/research_v3/experiment.py',
             ROOT / 'tools/export_bags.py', ROOT / 'research/split_v3.json', ROOT / 'research/plan_v3.json']
    paths += [ROOT / p for p in ('src/reserve_odometry/config/guarded_readout_v7.json', 'src/reserve_odometry/config/guarded_readout_v7.yaml', 'src/reserve_odometry/reserve_odometry/guarded_readout.py')]
    plan = dict(base_commit=BASE_COMMIT, active_main_model='main',
                selection_commit='f525b09393160163544038e6b7f2ebfa172a3202', baseline_core_git_blob=BASE_CORE_BLOB,
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                models={name: asdict(m[1]) for name, m in model_set.items()}, readout=asdict(ReadoutConfig()), operational=OPS,
                source_sha256={str(p.relative_to(ROOT)): ev.sha(p) for p in paths},
                split_sha256=store.plan['manifest_sha256'],
                python=platform.python_version(), numpy=np.__version__, workers=workers,
                role='validation', test_evaluated=False, check_disabled=check_disabled, check_inner=check_inner,
                selection='Selected on development, fixed before the original validation; this runner does not select or fit parameters')
    save(output / 'started.json', plan)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(worker, [(bag, data_root, output, check_disabled, check_inner) for bag in store.plan['splits']['validation']]))
    clean = [r['clean'] for r in rows]
    stress = [s for r in rows for s in r['stress']]
    summary = aggregate(clean, stress)
    report = dict(plan=plan, summary=summary, clean=clean, stress=stress,
                  decision=decision(clean, stress, summary), elapsed_s=time.perf_counter() - started)
    save(output / 'access.json', [a for r in rows for a in r['access']])
    save(output / 'results.json', report)
    print(json.dumps(dict(summary=summary, decision=report['decision']), indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=ROOT / 'dataset/data')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--check-disabled', action='store_true', help='Assert disabled outputs are exactly main, including faults')
    parser.add_argument('--check-inner', action='store_true', help='Assert every inner field against an independent baseline on every tick')
    args = parser.parse_args()
    report = run(args.output, args.data_root, args.workers, args.check_disabled, args.check_inner)
    if not report['decision']['eligible']:
        raise SystemExit('Candidate did not pass the documented comparison gates')

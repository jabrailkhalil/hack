"""Preregistered H25 train-only premise check; no runtime modification.

No validation/development entry point. A failed identifiability check stops the
research before candidate deployment. Wheel ratios are proxies, not truth.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, fields
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'tools/finalization'), str(ROOT / 'src/reserve_odometry')]
import evaluate as ev
import numpy as np
from reserve_odometry.core import Config
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig

BASE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
OPS = {'rate_hz': 20., 'alignment_delay_s': 0.}
COLS = ['t', 'delta', 'speed', 'regime', 'sign', 'skew', 'timing_bound', 'front', 'rear']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def profile():
    model, readout, scalar = {}, {}, {}
    path = ROOT / 'src/reserve_odometry/config/champion_v8.yaml'
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if not sep or key.startswith('#'):
            continue
        if key.startswith('model.'):
            model[key[6:]] = float(value)
        elif key.startswith('readout.'):
            readout[key[8:]] = float(value)
        elif key in ('rate_hz', 'alignment_delay_s', 'front_scale', 'rear_scale'):
            scalar[key] = float(value)
    if set(model) != {f.name for f in fields(Config)}:
        raise ValueError('Profile must supply ALL model fields; never use Config defaults')
    assert {k: scalar[k] for k in OPS} == OPS
    assert scalar['front_scale'] == scalar['rear_scale'] == 1 / 3.6
    assert readout == {'gain': 1., 'holdoff_s': .5}
    assert model['common_mode_quarantine_s'] == 1.5
    assert model['adaptation_tau_s'] == .5 and model['wheel_time_compensation'] == 0
    return Config(**model), ReadoutConfig(**readout)


def verify_sources():
    manifest = json.loads((HERE / 'baseline_manifest.json').read_text())
    assert manifest['baseline'] == BASE
    for name, digest in manifest['sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('Changed baseline/scorer/role file: ' + name)
    return manifest


def ratio_delta(front, rear):
    if not all(math.isfinite(x) for x in (front, rear)) or front * rear <= 0:
        raise ValueError('A relative ratio requires finite same-sign nonzero readings')
    return .5 * math.log(rear / front)


class Probe(GuardedReadoutObserver):
    """Read-only diagnostic collector; inherited runtime code is unchanged."""
    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.pairs = []  # OFFLINE artifact collector, not proposed runtime state.
        self.counts = Counter()
        self.prior_pair = None
        self.good_since = None
        self.blocked_until = -math.inf

    def step(self, t, command=None, front=None, rear=None):
        result = super().step(t, command, front, rear)
        self.counts['outputs'] += 1
        self.counts['mode:' + result.mode] += 1
        statuses = (result.front_status, result.rear_status)
        self.counts.update('status:' + s for s in statuses)
        if any(s not in ('ACCEPTED', 'DUPLICATE_OR_OLD') for s in statuses):
            self.blocked_until = t + .5
            self.good_since = None
            self.prior_pair = None
        if result.mode != 'FUSED' or result.command_stale:
            if self.prior_pair and t - max(x.t for x in self.prior_pair) > .25:
                self.good_since = None
                self.prior_pair = None
            return result
        self.counts['fused_new_pairs'] += 1
        previous = self.prior_pair
        self.prior_pair = (front, rear)
        valid = (t >= self.blocked_until and front.value * rear.value > 0
                 and all(2 <= abs(x.value) <= 30 and 0 <= t - x.t <= .10
                         for x in (front, rear))
                 and abs(front.t - rear.t) <= .025)
        rates = []
        if previous:
            for x, old in zip((front, rear), previous):
                elapsed = x.t - old.t
                if not .05 <= elapsed <= .25:
                    valid = False
                else:
                    rates.append(abs(x.value - old.value) / elapsed)
        else:
            valid = False
        valid = valid and len(rates) == 2 and max(rates) <= .20
        if not valid:
            self.good_since = None
            self.counts['pair_filter_rejected'] += 1
            return result
        if self.good_since is None:
            self.good_since = t
        if t - self.good_since < .5 - 1e-9:
            self.counts['dwell_rejected'] += 1
            return result
        value = ratio_delta(front.value, rear.value)
        speed = (abs(front.value) + abs(rear.value)) * .5
        regime = 1 if command.value > self.c.command_deadband else (
            -1 if command.value < -self.c.command_deadband else 0)
        skew = abs(front.t - rear.t)
        bound = max(rates) * skew / (2 * min(abs(front.value), abs(rear.value)))
        self.pairs.append((t, value, speed, regime, 1 if front.value > 0 else -1,
                           skew, bound, front.value, rear.value))
        self.counts['selected_pairs'] += 1
        return result


def predict(events, observer, config):
    original = ev.Observer
    try:
        ev.Observer = lambda c: observer
        return ev.replay(events, config, OPS)
    finally:
        ev.Observer = original


def median(a):
    return float(np.median(a)) if len(a) else None


def bag_stats(a):
    return dict(n=len(a), delta_median=median(a[:, 1]),
                delta_q10=float(np.quantile(a[:, 1], .1)) if len(a) else None,
                delta_q90=float(np.quantile(a[:, 1], .9)) if len(a) else None,
                speed_median=median(a[:, 2]), timing_bound=median(a[:, 6]))


def group_stats(records, arrays, selector=None):
    by_group = defaultdict(list)
    for row in records:
        if not row['representative']:
            continue
        a = arrays[row['bag']]
        if selector is not None:
            a = a[selector(a)]
        if len(a) >= 30:
            by_group[row['group']].append((row['bag'], a))
    result = []
    for group, bags in sorted(by_group.items()):
        total = sum(len(a) for _, a in bags)
        if total < 100:
            continue
        result.append(dict(group=group, n=total, bags=[b for b, _ in bags],
                           delta=median([median(a[:, 1]) for _, a in bags]),
                           timing_bound=median([median(a[:, 6]) for _, a in bags])))
    return result


def evaluate_premise(records, arrays, train_groups):
    roles = {g: 'check' if i % 3 == 0 else 'fit' for i, g in enumerate(sorted(train_groups))}
    groups = [dict(x, role=roles[x['group']]) for x in group_stats(records, arrays)]
    fit = [x for x in groups if x['role'] == 'fit']
    check = [x for x in groups if x['role'] == 'check']
    raw_delta = median([x['delta'] for x in fit])
    delta = max(-.01, min(.01, raw_delta)) if raw_delta is not None else None
    bound = median([x['timing_bound'] for x in fit])
    epsilon = max(.0001, 2 * bound) if bound is not None else None
    count = sum(x['n'] for x in groups)
    coverage = len(groups) >= 8 and len(fit) >= 5 and len(check) >= 3 and count >= 1000
    tolerance = max(.0005, .5 * abs(delta)) if delta is not None else None
    slices = {}
    for low, high in ((2, 5), (5, 10), (10, 20), (20, 30.000001)):
        slices[f'speed:{low}-{high:g}'] = group_stats(records, arrays,
            lambda a, lo=low, hi=high: (a[:, 2] >= lo) & (a[:, 2] < hi))
    for value, name in ((1, 'traction'), (0, 'coast'), (-1, 'brake')):
        slices['regime:' + name] = group_stats(records, arrays, lambda a, x=value: a[:, 3] == x)
    for value in (-1, 1):
        slices['sign:' + str(value)] = group_stats(records, arrays, lambda a, x=value: a[:, 4] == x)
    slice_stats = {k: dict(groups=v, covered=len(v) >= 3,
                    delta=median([x['delta'] for x in v])) for k, v in slices.items()}
    issues, stability = [], {}
    if not coverage:
        issues.append('INSUFFICIENT_TRAIN_COVERAGE')
    if delta is None or epsilon is None or abs(delta) <= epsilon:
        issues.append('NO_RESOLVED_RELATIVE_MISMATCH')
    if raw_delta is not None and abs(raw_delta) > .01:
        issues.append('OUTSIDE_PREREGISTERED_CAP')
    if delta is not None:
        for name, values in (('fit', fit), ('check', check)):
            sign_fraction = sum(x['delta'] * delta > 0 for x in values) / len(values) if values else 0
            close_fraction = sum(abs(x['delta'] - delta) <= tolerance for x in values) / len(values) if values else 0
            stability[name] = dict(same_sign_fraction=sign_fraction, compatible_fraction=close_fraction)
            if min(sign_fraction, close_fraction) < .8:
                issues.append('GROUP_UNSTABLE:' + name)
        spread = float(np.quantile([x['delta'] for x in groups], .9) -
                       np.quantile([x['delta'] for x in groups], .1)) if groups else None
        stability['q90_minus_q10'] = spread
        if spread is None or spread > max(.002, abs(delta)):
            issues.append('GROUP_UNSTABLE:spread')
        for key, value in slice_stats.items():
            if value['covered'] and (value['delta'] * delta <= 0 or abs(value['delta'] - delta) > tolerance):
                issues.append('REGIME_DEPENDENT:' + key)
    for prefix in ('speed:', 'regime:'):
        if sum(k.startswith(prefix) and v['covered'] for k, v in slice_stats.items()) < 2:
            issues.append('INSUFFICIENT_REGIME_COVERAGE:' + prefix)
    proxy = None
    # Proxy check only after identifiability admission: never use it to pick delta.
    if not issues:
        checked = []
        for g in check:
            bag_arrays = [arrays[b] for b in g['bags']]
            before = median([median(abs(a[:, 1])) for a in bag_arrays])
            after = median([median(abs(a[:, 1] - delta)) for a in bag_arrays])
            checked.append(dict(group=g['group'], before=before, after=after))
        before = float(np.mean([x['before'] for x in checked]))
        after = float(np.mean([x['after'] for x in checked]))
        worse = sum(x['after'] > x['before'] + max(.0001, .05 * x['before']) for x in checked)
        proxy = dict(before=before, after=after, groups=checked, worse_groups=worse)
        if before <= 0 or after > .9 * before or worse / len(checked) > .2:
            issues.append('RELATIVE_FIT_NOT_TRANSFERABLE')
    verdict = ('REJECTED' if any(x in issues for x in ('OUTSIDE_PREREGISTERED_CAP', 'RELATIVE_FIT_NOT_TRANSFERABLE'))
               else 'INCONCLUSIVE') if issues else 'PREREQUISITE_PASS'
    return dict(scientific_verdict=verdict, reasons=issues,
                mechanism_status='TRAIN_RATIO_DIAGNOSED_RUNTIME_NOT_IMPLEMENTED',
                coverage_status='SUFFICIENT_TRAIN_PAIRS' if coverage else 'INSUFFICIENT_TRAIN_PAIRS',
                accuracy_contract_passed=False, runtime_verified=False, ready_to_merge=False,
                delta_raw=raw_delta, delta=delta, timing_bound=bound, effect_epsilon=epsilon,
                compatibility_tolerance=tolerance, qualified_groups=len(groups), fitting_groups=len(fit),
                check_groups=len(check), selected_pairs_unique_qualified=count, groups=groups,
                roles=roles, stability=stability, slices=slice_stats, check_proxy=proxy,
                development_evaluated=False, validation_evaluated=False, test_evaluated=False,
                candidate_runtime_sha=None, validation_freeze_sha=None,
                accuracy_metrics=None, runtime_cpu_overhead=None)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = verify_sources()
    config, readout = profile()
    source_ref = os.environ.get('GITHUB_SHA', 'local')
    started = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), baseline=BASE,
                   source_ref=source_ref, phase='train_prerequisite_only',
                   plan_sha256=sha(HERE / 'PLAN.md'),
                   source_sha256={str(f.relative_to(ROOT)): sha(f) for f in HERE.rglob('*') if f.is_file() and '__pycache__' not in str(f)},
                   protected_sources=manifest, model=asdict(config), readout=asdict(readout), ops=OPS,
                   python=sys.version, numpy=np.__version__, test_evaluated=False)
    save(args.output / 'started.json', started)
    store = ev.ex.Store()
    names = sorted(store.plan['splits']['train'])
    representatives = {}
    for bag in names:
        row = store.records[bag]
        representatives.setdefault((row['group'], row['vehicle_wire_sha256']), bag)
    records, arrays = [], {}
    for index, bag in enumerate(names):
        events, refs = store.load(bag, 'train')
        assert not any(refs.values()), 'Train reference must remain inaccessible'
        metadata = store.records[bag]
        probe = Probe(config, readout=readout)
        baseline = GuardedReadoutObserver(config, readout=readout)
        outputs, timing = {}, {}
        for label, obj in (('baseline', baseline), ('probe', probe)) if index % 2 == 0 else (('probe', probe), ('baseline', baseline)):
            start_cpu, start_wall = time.process_time(), time.perf_counter()
            outputs[label] = predict(events, obj, config)
            timing[label] = dict(cpu_s=time.process_time() - start_cpu, wall_s=time.perf_counter() - start_wall)
        b, br = outputs['baseline']; c, cr = outputs['probe']
        if not np.array_equal(b, c, equal_nan=True) or br != cr:
            raise AssertionError('Diagnostic collector changed baseline: ' + bag)
        if br['causal_errors'] or br['resets']:
            raise AssertionError('Train causality/reset failure: ' + bag)
        a = np.asarray(probe.pairs, dtype=float).reshape(-1, len(COLS)); arrays[bag] = a
        rows = dict(bag=bag, group=metadata['group'], role='train',
                    representative=representatives[(metadata['group'], metadata['vehicle_wire_sha256'])] == bag,
                    representative_bag=representatives[(metadata['group'], metadata['vehicle_wire_sha256'])],
                    wire_sha256=metadata['vehicle_wire_sha256'], data_sha256=metadata['sha256'],
                    stats=bag_stats(a), counts=dict(probe.counts), runtime=br, timing=timing,
                    exact_baseline_reproduction=True, published_output_sha256=hashlib.sha256(b[:, :3].tobytes()).hexdigest())
        records.append(rows)
        save(args.output / 'access.json', store.access)
        save(args.output / 'bags' / (bag + '.json'), rows)
        print('TRAIN', bag, 'pairs', len(a), 'exact_baseline', True, flush=True)
    decision = evaluate_premise(records, arrays, {store.records[b]['group'] for b in names})
    np.savez_compressed(args.output / 'selected_pairs.npz', **arrays)
    decision.update(baseline=BASE, diagnostic_source_sha=source_ref,
                    all_bags=len(records), unique_wire_bags=sum(r['representative'] for r in records),
                    total_outputs=sum(r['counts']['outputs'] for r in records),
                    total_pairs_including_duplicates=sum(r['stats']['n'] for r in records),
                    all_exact_baseline_reproduction=all(r['exact_baseline_reproduction'] for r in records))
    save(args.output / 'SUMMARY.json', decision)
    save(args.output / 'per_bag.json', records)
    save(args.output / 'pairs_manifest.json', dict(file='selected_pairs.npz', sha256=sha(args.output / 'selected_pairs.npz'),
                columns=COLS, meaning='Offline wheel-proxy pairs, not independent truth or runtime state'))
    print(json.dumps({k: v for k, v in decision.items() if k not in ('groups', 'roles', 'slices')}, indent=2), flush=True)


if __name__ == '__main__':
    main()

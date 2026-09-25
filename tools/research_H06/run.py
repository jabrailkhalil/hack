"""One frozen H06 candidate, unchanged v6 evaluator and fault definitions.

Train does not access GNSS. Validation requires a prior immutable freeze.
FinalStore/final-test payloads are never used. Run from a full git checkout.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import csv

ROOT = Path(__file__).resolve().parents[2]
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
NAME = 'H06_evidence_04s_15x'
CORE = 'src/reserve_odometry/reserve_odometry/core.py'
sys.path.insert(0, str(ROOT / 'tools/research_v6'))
import compare as v6
from reserve_odometry.recovery import RecoveryConfig, RecoveryObserver

ev, ex, np = v6.ev, v6.ex, v6.np
OPS = dict(rate_hz=20., alignment_delay_s=0.)
PINNED = (
    'tools/finalization/evaluate.py', 'tools/research_v3/experiment.py',
    'tools/research_v3/manifest.py', 'tools/export_bags.py',
    'tools/research_v6/compare.py', 'research/split_v3.json',
    'research/plan_v3.json', 'src/reserve_odometry/config/adaptive_v5.yaml',
    'src/reserve_odometry/config/default.yaml',
    'src/reserve_odometry/config/candidates_v3/balanced_physics.json',
    'src/reserve_odometry/reserve_odometry/timeline.py',
    'src/reserve_odometry/reserve_odometry/node.py',
    'src/reserve_odometry/reserve_odometry/route.py',
)
ORIGINAL = None


def git_bytes(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)


def setup():
    global ORIGINAL
    for path in PINNED:
        if (ROOT / path).read_bytes() != git_bytes(path):
            raise AssertionError('Pinned source/config/split changed: ' + path)
    source = git_bytes(CORE)
    digest = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if digest != 'f6fc8ecd0b4e16018d814407b1944ce26ea550b0':
        raise AssertionError('Wrong baseline core')
    manifest = json.loads((ROOT / 'research/H06/CANDIDATE.json').read_text())
    for path, expected in manifest['sha256'].items():
        if ev.sha(ROOT / path) != expected:
            raise AssertionError('Candidate changed before run: ' + path)
    spec = importlib.util.spec_from_loader('h06_original_runtime', loader=None)
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    exec(compile(source, BASE + ':' + CORE, 'exec'), original.__dict__)
    ORIGINAL = original.Observer
    # Only the runtime factory varies. score/replay/match/metrics and the
    # original v6 validate_bag (including all fault anchors) remain unchanged.
    ev.Observer = observer_factory
    v6.configurations = configurations


def observer_factory(config):
    return RecoveryObserver(config) if isinstance(config, RecoveryConfig) else ORIGINAL(config)


def configurations():
    base = json.loads((ROOT / 'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    adaptive = base | {'adaptation_tau_s': .5}
    return {'baseline_v2': ex.Config(**base), 'balanced_physics': ex.Config(**adaptive),
            NAME: RecoveryConfig(**adaptive)}


def fingerprint():
    return dict(baseline=BASE, candidate=NAME,
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_sha256=ev.protected_files(), runner_sha256=ev.sha(__file__),
        plan_sha256=ev.sha(ROOT / 'research/H06/PLAN.md'),
        manifest_sha256=ev.sha(ROOT / 'research/H06/CANDIDATE.json'),
        core_patch_sha256=ev.sha(ROOT / 'research/H06/core-hooks.patch'),
        models={v6.ALIASES.get(n, n): asdict(c) for n, c in configurations().items()},
        observer_classes={'baseline': 'original SHA core.Observer', 'candidate': 'recovery.RecoveryObserver'},
        operational=OPS, python=platform.python_version(), numpy=np.__version__, test_evaluated=False)


def exclusive_json(path, data):
    with path.open('x') as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


def train_freeze(output):
    if (output / 'candidate-freeze.json').exists():
        raise FileExistsError('Do not overwrite a candidate freeze')
    store = ex.Store()
    bag = store.plan['splits']['train'][0]
    events, refs = store.load(bag, 'train')
    if any(refs.values()):
        raise AssertionError('Train must not expose reference measurements')
    events = events[events[:, 0] <= events[0, 0] + 180.]
    records, schedule = {}, None
    for name, config in configurations().items():
        a, info = ev.replay(events, config, OPS)
        if info['causal_errors'] or info['resets']:
            raise AssertionError(('Train runtime invariant', name, info))
        if schedule is None:
            schedule = a[:, 0]
        elif not np.array_equal(a[:, 0], schedule):
            raise AssertionError('Train output schedule changed')
        records[v6.ALIASES.get(name, name)] = dict(outputs=len(a), runtime=info,
            first_output_s=float(a[0, 0]) if len(a) else None,
            last_output_s=float(a[-1, 0]) if len(a) else None)
    if not len(schedule):
        raise AssertionError('Empty train smoke')
    train = dict(bag=bag, role='train', duration_limit_s=180., events=len(events),
        reference_used=False, purpose='execution/invariants only, no fitting and no accuracy claim',
        records=records, access=store.access)
    exclusive_json(output / 'train.json', train)
    exclusive_json(output / 'candidate-freeze.json', fingerprint())
    print('FROZEN', NAME, 'after train-only execution', json.dumps(train), flush=True)


def export_csv(output, clean, stress, decision):
    fields = ['bag', 'group', 'kind', 'start', 'end', 'receiver', 'candidate', 'n',
        'coverage', 'rmse', 'event_rmse', 'mae', 'p95', 'bias', 'recovery_s',
        'false_stop_samples', 'distance_rmse']
    with (output / 'per-bag.csv').open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in clean + stress:
            fault = row.get('fault', {})
            for receiver, models in row['receivers'].items():
                for name in ('v4_default', 'v5_adaptive_05s', NAME):
                    m = models[name]
                    item = {k: m.get(k) for k in fields if k in m}
                    item.update(bag=row['bag'], group=row['group'], kind=fault.get('kind', 'clean'),
                        start=fault.get('start'), end=fault.get('end'), receiver=receiver, candidate=name,
                        distance_rmse=v6.metric_value(m, 'distance'))
                    writer.writerow(item)
    fields = ['candidate'] + [k for k in decision['candidates'][NAME] if k != 'rejection_reasons']
    with (output / 'aggregate.csv').open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for name, row in decision['candidates'].items():
            writer.writerow(dict(candidate=name, **row))


def validation(output, workers):
    frozen = json.loads((output / 'candidate-freeze.json').read_text())
    if frozen != fingerprint():
        raise AssertionError('Candidate/evaluator changed after freeze')
    target = output / 'validation'
    target.mkdir(exist_ok=False)
    store = ex.Store(); clean, stress, access = [], [], []
    started = time.perf_counter()
    ev.save(target / 'started.json', frozen)
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('fork')) as pool:
        for c, faults, journal in pool.map(v6.validate_bag, store.plan['splits']['validation']):
            clean.append(c); stress.extend(faults); access.extend(journal)
            ev.save(target / 'bags' / (c['bag'] + '.json'), dict(clean=c, stress=faults))
            ev.save(target / 'access.json', dict(test_evaluated=False, access=access))
            print('CHECKPOINT', c['bag'], flush=True)
    reproduction = v6.reproduce_published_v5(clean)
    names = [v6.ALIASES.get(n, n) for n in configurations()]
    result = dict(**frozen, clean=clean, stress=stress, baseline_reproduction=reproduction,
        elapsed_s=time.perf_counter() - started)
    ev.save(target / 'results.json', result)
    decision = v6.decide(clean, stress, names)
    candidate, baseline = decision['candidates'][NAME], decision['candidates']['v5_adaptive_05s']
    # Fixed additional gate demanded by H06; do not edit the published v6 gate.
    candidate['pooled_change_vs_v5'] = candidate['pooled_rmse'] / baseline['pooled_rmse'] - 1.
    if candidate['pooled_change_vs_v5'] > .005:
        candidate['eligible'] = False
        candidate['rejection_reasons'].append('pooled_aggregate_regression')
        decision['selected'] = 'v5_adaptive_05s'
    candidate['rejection_reasons'] = sorted(set(candidate['rejection_reasons']))
    decision['hypothesis_outcome'] = 'supported_on_reused_validation_only' if candidate['eligible'] else 'rejected'
    decision['runtime_certified'] = False
    decision['limitations'] = [
        'Reused validation is not an independent final test.',
        'No new installed ROS latency/memory benchmark for H06.',
        'Dynamically consistent common-mode false speed may accelerate reacquisition.',
        'Train smoke uses only first 180 seconds of first permitted train bag; no accuracy claim.',
    ]
    ev.save(target / 'decision.json', decision)
    export_csv(target, clean, stress, decision)
    print(json.dumps(decision, indent=2, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('train-freeze', 'validation'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        raise ValueError('workers must be 1 or 2')
    if not args.output.is_dir():
        raise ValueError('Create a fresh output directory first')
    setup()
    if args.stage == 'train-freeze':
        train_freeze(args.output)
    else:
        validation(args.output, args.workers)


if __name__ == '__main__':
    main()

"""H05: one preregistered candidate, unchanged v6 evaluator, no final-test loader."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import csv
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research_v6'))
import compare as common

ev, ex, np = common.ev, common.ex, common.np
BASELINE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
CORE = 'src/reserve_odometry/reserve_odometry/core.py'
FREEZE = ROOT / 'research/H05/FREEZE.json'
CANDIDATE = 'H05_ttl2s'
TRAIN_BAGS = ['30618_0259fe53', '30618_082f1d65', '30618_095a115b']
ALIASES = common.ALIASES
NAMES = ['v4_default', 'v5_adaptive_05s', CANDIDATE]
ORIGINAL = None


def git_bytes(path):
    return subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def configurations():
    base = json.loads((ROOT / 'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    adaptive = base | {'adaptation_tau_s': .5}
    return {'baseline_v2': ex.Config(**base), 'balanced_physics': ex.Config(**adaptive),
            CANDIDATE: ex.Config(**(adaptive | {'h05_history_s': 2., 'h05_min_reliability': .25}))}


def dispatch(config):
    """Select implementation only; replay/score/masks/fault definitions unchanged."""
    if config.h05_history_s > 0:
        return ex.Observer(config)
    original = {k: v for k, v in asdict(config).items() if not k.startswith('h05_')}
    return ORIGINAL.Observer(ORIGINAL.Config(**original))


def setup():
    global ORIGINAL
    frozen = json.loads(FREEZE.read_text())
    if frozen['baseline'] != BASELINE or frozen['candidate'] != CANDIDATE:
        raise AssertionError('Wrong frozen experiment')
    if frozen['candidate_delta'] != {'h05_history_s': 2., 'h05_min_reliability': .25}:
        raise AssertionError('Candidate was not frozen as preregistered')
    if frozen['train_bags'] != TRAIN_BAGS:
        raise AssertionError('Training smoke membership changed')
    for path, expected in frozen['file_sha256'].items():
        if ev.sha(ROOT / path) != expected:
            raise AssertionError('Frozen candidate file changed: ' + path)
    raw = git_bytes(CORE)
    if sha_bytes(raw) != frozen['baseline_core_sha256']:
        raise AssertionError('Baseline core changed')
    if ev.sha(ROOT / CORE) != frozen['patched_core_sha256']:
        raise AssertionError('Apply exactly the frozen H05 patch before replay')
    protected = ev.protected_files()
    for path, actual in protected.items():
        if path != CORE and actual != sha_bytes(git_bytes(path)):
            raise AssertionError('Protected source/evaluator modified: ' + path)
    for path in ['tools/research_v6/compare.py', 'research/plan_v6.json',
                 'requirements-research.txt', 'tools/get_dataset.py']:
        if ev.sha(ROOT / path) != sha_bytes(git_bytes(path)):
            raise AssertionError('Shared method changed: ' + path)
    ORIGINAL = types.ModuleType('h05_pinned_baseline')
    sys.modules[ORIGINAL.__name__] = ORIGINAL
    exec(compile(raw, '<pinned baseline core>', 'exec'), ORIGINAL.__dict__)
    ev.Observer = dispatch
    common.configurations = configurations
    return dict(baseline=BASELINE, hypothesis='H05', candidate=CANDIDATE,
                freeze_sha256=ev.sha(FREEZE), frozen=frozen, source_sha256=protected,
                evaluator_sha256={p: ev.sha(ROOT / p) for p in [
                    'tools/finalization/evaluate.py', 'tools/research_v3/experiment.py',
                    'tools/research_v6/compare.py', 'tools/export_bags.py',
                    'research/split_v3.json', 'research/plan_v3.json']},
                runner_sha256=ev.sha(__file__), source_ref=subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                python=platform.python_version(), numpy=np.__version__, test_evaluated=False)


def train(output, provenance):
    """No GNSS labels and no selection: runtime checks on allowed train only."""
    store = ex.Store(); checks = []
    if store.plan['splits']['train'][:3] != TRAIN_BAGS:
        raise AssertionError('Pinned first-three-train smoke changed')
    for bag in TRAIN_BAGS:
        events, refs = store.load(bag, 'train')
        if any(refs.values()):
            raise AssertionError('Train reference payload unexpectedly exposed')
        scored = ev.score(events, refs, configurations(), dict(rate_hz=20., alignment_delay_s=0.))
        for runtime in scored['runtime'].values():
            if runtime['causal_errors'] or runtime['resets']:
                raise AssertionError(('train causal/reset failure', bag, runtime))
        checks.append(dict(bag=bag, outputs=scored['outputs'], runtime=scored['runtime']))
        ev.save(output / 'access.json', dict(access=store.access, test_evaluated=False))
        ev.save(output / 'bags' / (bag + '.json'), checks[-1])
        print('TRAIN_CHECKPOINT', bag, flush=True)
    result = dict(**provenance, stage='train', passed=True, checks=checks, access=store.access,
                  accuracy_claim=False, parameter_tuning=False,
                  limitation='Three preregistered train bags; only three vehicle topics; no absolute accuracy labels')
    ev.save(output / 'train.json', result)
    print('TRAIN_COMPLETE', len(checks), flush=True)


def percentage(a, b):
    return 100. * (a / b - 1.) if a is not None and b not in (None, 0.) else None


def tables(output, clean, stress, decision):
    fields = ['scope', 'bag', 'group', 'receiver', 'fault_kind', 'fault_start', 'fault_end',
              'metric', 'baseline_v5', 'candidate', 'change_percent']
    with (output / 'per_bag.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for scope, rows in [('clean', clean), ('fault', stress)]:
            for row in rows:
                fault = row.get('fault', {})
                for receiver, scores in row['receivers'].items():
                    a, b = scores[CANDIDATE], scores['v5_adaptive_05s']
                    keys = ['rmse', 'mae', 'p95', 'bias', 'n', 'coverage', 'false_stop_samples']
                    keys += ['distance'] if scope == 'clean' else ['event_rmse', 'recovery_s']
                    for key in keys:
                        av, bv = common.metric_value(a, key), common.metric_value(b, key)
                        writer.writerow(dict(scope=scope, bag=row['bag'], group=row['group'], receiver=receiver,
                            fault_kind=fault.get('kind'), fault_start=fault.get('start'), fault_end=fault.get('end'),
                            metric=key, baseline_v5=bv, candidate=av, change_percent=percentage(av, bv)))
    with (output / 'aggregate.csv').open('w', newline='') as f:
        writer = csv.writer(f); writer.writerow(['metric', 'baseline_v5', 'candidate', 'change_percent'])
        a, b = decision['candidates'][CANDIDATE], decision['candidates']['v5_adaptive_05s']
        for key in ['clean_rmse', 'fault_rmse', 'pooled_rmse', 'distance_rmse', 'samples',
                    'false_stops_clean', 'false_stops_fault', 'unrecovered']:
            writer.writerow([key, b[key], a[key], percentage(a[key], b[key])])


def validate(output, train_output, provenance, workers):
    trained = json.loads((train_output / 'train.json').read_text())
    if not trained.get('passed') or trained.get('stage') != 'train' or trained.get('test_evaluated'):
        raise AssertionError('Successful train-only smoke required first')
    for key in ('source_ref', 'freeze_sha256', 'runner_sha256', 'source_sha256', 'evaluator_sha256'):
        if trained[key] != provenance[key]:
            raise AssertionError('Train/validation candidate or evaluator changed: ' + key)
    if [c['bag'] for c in trained['checks']] != TRAIN_BAGS:
        raise AssertionError('Training membership not preregistered')
    # This is the phase boundary. Candidate was committed/frozen before this call.
    ev.save(output / 'validation_gate.json', dict(candidate=CANDIDATE,
        source_ref=provenance['source_ref'], freeze_sha256=provenance['freeze_sha256'],
        train_result_sha256=ev.sha(train_output / 'train.json'), selection='one candidate fixed a priori'))
    store = ex.Store(); clean, stress, access = [], [], []; started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                             initializer=setup) as pool:
        for c, faults, journal in pool.map(common.validate_bag, store.plan['splits']['validation']):
            clean.append(c); stress.extend(faults); access.extend(journal)
            ev.save(output / 'bags' / (c['bag'] + '.json'), dict(clean=c, stress=faults))
            ev.save(output / 'access.json', dict(access=access, test_evaluated=False))
            print('VALIDATION_CHECKPOINT', c['bag'], flush=True)
    # Save all raw measurements BEFORE any rejection/reproduction assertion.
    result = dict(**provenance, clean=clean, stress=stress, elapsed_s=time.perf_counter()-started,
                  models={ALIASES.get(n, n): asdict(c) for n, c in configurations().items()})
    ev.save(output / 'results.json', result)
    reproduction = common.reproduce_published_v5(clean)
    ev.save(output / 'baseline_reproduction.json', reproduction)
    decision = common.decide(clean, stress, NAMES)
    candidate = decision['candidates'][CANDIDATE]
    baseline = decision['candidates']['v5_adaptive_05s']
    extra = []
    if candidate['pooled_rmse'] > baseline['pooled_rmse'] * 1.005:
        extra.append('pooled_rmse_regression_above_0.5_percent')
    eligible = candidate['eligible'] and not extra
    contract = dict(hypothesis='H05', candidate=CANDIDATE, eligible=eligible,
                    additional_rejection_reasons=extra,
                    verdict='подтверждена на повторно используемом validation' if eligible else 'отвергнута',
                    independent_final_test=False, runtime_ros_verified=False,
                    ready_to_merge=False, validation_bags=len(clean), fault_scenarios=len(stress),
                    scope='One preregistered candidate; no validation tuning; no independent final test')
    ev.save(output / 'decision_v6_unchanged.json', decision)
    ev.save(output / 'H05_contract.json', contract)
    tables(output, clean, stress, decision)
    print(json.dumps(dict(contract=contract, decision=decision), ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['train', 'validation'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--train-output', type=Path)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        raise ValueError('H05 permits one or two workers')
    if args.stage == 'validation' and args.train_output is None:
        parser.error('--train-output is required before validation')
    args.output.mkdir(parents=True, exist_ok=False)
    provenance = setup(); ev.save(args.output / 'started.json', provenance | {'stage': args.stage})
    if args.stage == 'train': train(args.output, provenance)
    else: validate(args.output, args.train_output, provenance, args.workers)


if __name__ == '__main__': main()

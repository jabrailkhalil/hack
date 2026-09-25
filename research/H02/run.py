"""H02: reference-free train checks, explicit freeze, then one validation run.

No metric or fault implementation is copied or edited. The stock v6 bag runner
and decision functions are used; only the algorithm factory/configurations are
injected. The extra pooled-RMSE guard enforces the preregistered 0.5% contract.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import csv
import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from build_candidate import (ROOT, BASELINE, CORE, candidate_module, candidate_source,
                             candidate_yaml, profile, sha_bytes)
sys.path.insert(0, str(ROOT / 'tools/research_v6'))
import compare as v6

ev, ex, np = v6.ev, v6.ex, v6.np
PRISTINE_OBSERVER = ev.Observer
CANDIDATE = 'H02_timing_05'
BASE_NAME = 'v5_adaptive_05s'
OPS = dict(rate_hz=20.0, alignment_delay_s=0.0)


def observer_factory(config):
    module = candidate_module()
    if isinstance(config, module.Config):
        return module.Observer(config)
    return PRISTINE_OBSERVER(config)


def configurations():
    base = profile()
    return {'baseline_v2': ex.Config(**(base | {'adaptation_tau_s': 8.0})),
            'balanced_physics': ex.Config(**base),
            CANDIDATE: candidate_module().Config(**base, timing_accel_fraction=0.5)}


# Dependency injection is limited to algorithms. The pristine baseline has its
# own original class, not merely the candidate with a disabled parameter.
ev.Observer = observer_factory
v6.configurations = configurations


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def checked_sources():
    protected = ev.protected_files()
    protected['tools/research_v6/compare.py'] = ev.sha(ROOT / 'tools/research_v6/compare.py')
    protected['reports/research_v5/round3/results.json'] = ev.sha(ROOT / 'reports/research_v5/round3/results.json')
    for path, actual in protected.items():
        original = subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT)
        if sha_bytes(original) != actual:
            raise AssertionError('Protected baseline/evaluator changed: ' + path)
    own = {str(p.relative_to(ROOT)): ev.sha(p) for p in sorted((ROOT / 'research/H02').glob('*')) if p.is_file()}
    return dict(baseline=BASELINE, protected_sha256=protected, research_sha256=own,
                candidate_core_sha256=sha_bytes(candidate_source()), candidate=CANDIDATE,
                config=asdict(configurations()[CANDIDATE]), operational=OPS,
                source_ref=os.environ.get('GITHUB_SHA') or subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())


def train(output):
    output.mkdir(parents=True, exist_ok=False)
    started = checked_sources()
    ev.save(output / 'started.json', dict(created_utc=now(), **started, test_evaluated=False))
    with (output / 'unit.log').open('w') as log:
        subprocess.run([sys.executable, str(ROOT / 'research/H02/test_h02.py')],
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    store = ex.Store()
    rows = []
    models = configurations()
    disabled = candidate_module().Config(**profile(), timing_accel_fraction=0.0)
    # Bounded, reference-free diagnostic on every train bag's first 180 seconds.
    # No train GNSS queries, no proxy labels, no parameter selection.
    for bag in store.plan['splits']['train']:
        ev.save(output / 'access_requested.json', dict(stage='train', bag=bag, test_evaluated=False))
        events, refs = store.load(bag, 'train')
        assert not any(refs.values()), 'Train references are forbidden'
        if len(events):
            events = events[events[:, 0] <= events[:, 0].min() + 180.0]
        arrays, runtime = {}, {}
        for name, config in [('baseline', models['balanced_physics']), ('disabled', disabled),
                             ('candidate', models[CANDIDATE])]:
            arrays[name], runtime[name] = ev.replay(events, config, OPS)
        assert np.array_equal(arrays['baseline'], arrays['disabled'], equal_nan=True), ('disabled', bag)
        assert runtime['baseline'] == runtime['disabled'], ('disabled_runtime', bag)
        assert np.array_equal(arrays['baseline'][:, 0], arrays['candidate'][:, 0]), ('schedule', bag)
        assert runtime['candidate']['causal_errors'] == 0, ('causality', bag)
        assert runtime['candidate']['resets'] == runtime['baseline']['resets'], ('resets', bag)
        rows.append(dict(bag=bag, input_events=len(events), outputs=len(arrays['baseline']),
                         disabled_exact=True, schedule_exact=True, runtime=runtime))
        ev.save(output / 'train_progress.json', dict(rows=rows, access=store.access, test_evaluated=False))
        print('TRAIN_CHECK', bag, len(events), len(arrays['baseline']), flush=True)
    ev.save(output / 'train.json', dict(passed=True, created_utc=now(), rows=rows, access=store.access,
        maximum_replayed_seconds_per_bag=180, accuracy_measured=False, parameters_fitted=False,
        unit_tests_passed=True, test_evaluated=False))
    (output / 'candidate_core.py').write_bytes(candidate_source())
    (output / 'candidate.yaml').write_text(candidate_yaml())


def freeze(output):
    train_result = json.loads((output / 'train.json').read_text())
    assert train_result['passed'] and train_result['unit_tests_passed']
    path = output / 'FREEZE.json'
    if path.exists():
        raise FileExistsError('Do not replace the candidate freeze')
    ev.save(path, dict(created_utc=now(), **checked_sources(), train_sha256=ev.sha(output / 'train.json'),
                      selected_apriori=True, candidates_considered=1, validation_opened=False,
                      test_evaluated=False, parameters_fitted=False))
    print('FROZEN', ev.sha(path), CANDIDATE, flush=True)


def validate_one(bag):
    return v6.validate_bag(bag)


def csv_outputs(output, clean, stress, decision):
    fields = ['bag', 'group', 'receiver', 'scenario', 'model', 'rmse', 'mae', 'bias', 'p95',
              'n', 'coverage', 'event_rmse', 'recovery_s', 'false_stop_samples', 'distance_rmse_m']
    with (output / 'per_bag.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in clean + stress:
            fault = row.get('fault')
            scenario = 'clean' if not fault else f"{fault['kind']}:{fault['start']}:{fault['end']}"
            for receiver, models in row['receivers'].items():
                for model in ('v4_default', BASE_NAME, CANDIDATE):
                    metrics = models[model]
                    record = dict(bag=row['bag'], group=row['group'], receiver=receiver,
                                  scenario=scenario, model=model,
                                  distance_rmse_m=metrics.get('distance_surrogate', {}).get('reanchored_span_rmse_m'))
                    record.update({key: metrics.get(key) for key in fields if key in metrics})
                    writer.writerow(record)
    fields = ['model', 'clean_rmse', 'fault_rmse', 'pooled_rmse', 'distance_rmse', 'samples',
              'false_stops_clean', 'false_stops_fault', 'unrecovered', 'eligible']
    with (output / 'aggregate.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for name, entry in decision['candidates'].items():
            writer.writerow(dict(model=name, **{key: entry.get(key) for key in fields if key != 'model'}))


def validation(output, workers):
    frozen = json.loads((output / 'FREEZE.json').read_text())
    current = checked_sources()
    for key, value in current.items():
        if frozen[key] != value:
            raise AssertionError('Changed after freeze: ' + key)
    assert frozen['train_sha256'] == ev.sha(output / 'train.json')
    destination = output / 'validation'
    destination.mkdir(exist_ok=False)
    ev.save(destination / 'started.json', dict(started_utc=now(), freeze_sha256=ev.sha(output / 'FREEZE.json'),
                                             **current, test_evaluated=False))
    started = time.perf_counter()
    store = ex.Store()
    clean, stress, access = [], [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row, faults, journal in pool.map(validate_one, store.plan['splits']['validation']):
            clean.append(row)
            stress.extend(faults)
            access.extend(journal)
            ev.save(destination / 'bags' / (row['bag'] + '.json'), dict(clean=row, stress=faults))
            ev.save(destination / 'access.json', dict(access=access, test_evaluated=False))
            print('VALIDATION_CHECKPOINT', row['bag'], flush=True)
    result = dict(**current, created_utc=now(), freeze_sha256=ev.sha(output / 'FREEZE.json'),
                  clean=clean, stress=stress, access=access, test_evaluated=False,
                  python=platform.python_version(), numpy=np.__version__, elapsed_s=time.perf_counter()-started,
                  models={v6.ALIASES.get(k,k):asdict(v) for k,v in configurations().items()})
    # Preserve raw results even if reproduction or subsequent contract checks fail.
    ev.save(destination / 'results.json', result)
    reproduction = v6.reproduce_published_v5(clean)
    result['baseline_reproduction'] = reproduction
    ev.save(destination / 'results.json', result)
    decision = v6.decide(clean, stress, ['v4_default', BASE_NAME, CANDIDATE])
    base, candidate = decision['candidates'][BASE_NAME], decision['candidates'][CANDIDATE]
    pooled_ok = candidate['pooled_rmse'] <= 1.005 * base['pooled_rmse']
    if not pooled_ok:
        candidate['rejection_reasons'].append('pooled_rmse_regression_over_0.5_percent')
        candidate['eligible'] = False
        decision['selected'] = BASE_NAME
    decision.update(hypothesis='H02', evaluated_candidate=CANDIDATE,
        preregistered_pooled_guard_passed=pooled_ok, parameters_fitted=False,
        scope='one apriori candidate on reused validation; not independent final test',
        conclusion='accuracy_gates_passed_runtime_unverified' if candidate['eligible'] else 'rejected',
        merge_ready=False, ros_candidate_runtime_measured=False)
    ev.save(destination / 'decision.json', decision)
    csv_outputs(destination, clean, stress, decision)
    print(json.dumps(decision, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['train', 'freeze', 'validation'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2:
        raise ValueError('Use 1 or 2 workers')
    if args.stage == 'train':
        train(args.output)
    elif args.stage == 'freeze':
        freeze(args.output)
    else:
        validation(args.output, args.workers)


if __name__ == '__main__':
    main()

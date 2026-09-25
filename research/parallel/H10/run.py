"""H10 orchestration; the shared evaluator, fault policy and metrics stay unchanged."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/research_v6'))
import compare as protocol

ev, ex, np = protocol.ev, protocol.ex, protocol.np
BASE = '984fdf2fc4faf05325249215d6b8541c0e68209a'
HERE = ROOT / 'research/parallel/H10'
NAME = 'H10_joint_q004'
BASE_NAME = 'v5_adaptive_05s'
IMMUTABLE = (
    'tools/finalization/evaluate.py', 'tools/research_v6/compare.py',
    'tools/research_v3/experiment.py', 'tools/research_v3/manifest.py',
    'tools/export_bags.py', 'src/reserve_odometry/reserve_odometry/timeline.py',
    'research/plan_v3.json', 'research/split_v3.json',
    'src/reserve_odometry/config/candidates_v3/balanced_physics.json',
    'src/reserve_odometry/config/adaptive_v5.yaml', 'src/reserve_odometry/config/default.yaml',
)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def configurations():
    plan = json.loads((HERE / 'PLAN.json').read_text())
    assert plan['maximum_algorithm_variants'] == 1 and len(plan['variants']) == 1
    variant = plan['variants'][0]
    assert variant['id'] == NAME and variant['joint_disturbance_process_noise'] == .04
    config = json.loads((ROOT / 'src/reserve_odometry/config/candidates_v3/balanced_physics.json').read_text())['config']
    adaptive = config | {'adaptation_tau_s': .5}
    return {
        'baseline_v2': ex.Config(**config),  # v4 for published-baseline reproduction only
        'balanced_physics': ex.Config(**adaptive),
        NAME: ex.Config(**(adaptive | {'joint_observer_enabled': 1,
                                     'joint_disturbance_process_noise': .04})),
    }


def bind_candidate_factory():
    # Only the algorithm/config factory is replaced. score(), replay(), matching,
    # fault construction, aggregation and acceptance functions are not patched.
    protocol.configurations = configurations


def provenance():
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    immutable_hashes = {}
    for path in IMMUTABLE:
        expected = hashlib.sha256(git('show', BASE + ':' + path)).hexdigest()
        actual = ev.sha(ROOT / path)
        if actual != expected:
            raise AssertionError('Shared evaluator/data/profile was modified: ' + path)
        immutable_hashes[path] = actual
    source = ev.protected_files()
    for path in ('PLAN.json', 'algorithm.patch', 'test_joint.py', 'run.py'):
        source[str((HERE / path).relative_to(ROOT))] = ev.sha(HERE / path)
    return dict(baseline_sha=BASE, source_ref=git('rev-parse', 'HEAD').decode().strip(),
                source_sha256=source, immutable_sha256=immutable_hashes,
                models={k: asdict(v) for k, v in configurations().items()},
                operational=dict(rate_hz=20., alignment_delay_s=0.),
                python=platform.python_version(), numpy=np.__version__,
                test_evaluated=False, hypothesis='H10',
                run_id=os.environ.get('GITHUB_RUN_ID'), run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'))


def train(output):
    output.mkdir(parents=True, exist_ok=False)
    source = provenance()
    store = ex.Store()
    rows = []
    models = configurations()
    for index, bag in enumerate(store.plan['splits']['train']):
        events, refs = store.load(bag, 'train')
        if any(refs.values()):
            raise AssertionError('Train references must remain unavailable')
        records, predictions = {}, {}
        order = ['balanced_physics', NAME]
        if index % 2:
            order.reverse()
        for name in order:
            started = time.perf_counter()
            prediction, runtime = ev.replay(events, models[name], source['operational'])
            wall = time.perf_counter() - started
            predictions[name] = prediction
            records[name] = dict(runtime=runtime, outputs=len(prediction), wall_s=wall,
                                 wall_us_per_output=1e6*wall/len(prediction) if len(prediction) else None,
                                 trace_tvs_sha256=hashlib.sha256(prediction[:, :3].tobytes()).hexdigest())
            if runtime['causal_errors'] or runtime['resets']:
                raise AssertionError((bag, name, runtime))
        a, b = predictions['balanced_physics'], predictions[NAME]
        if a.shape != b.shape or not np.allclose(a[:, 0], b[:, 0], rtol=0, atol=1e-8):
            raise AssertionError('Train output schedule differs: ' + bag)
        row = dict(bag=bag, group=store.records[bag]['group'], input_events=len(events),
                   order=order, models=records, accuracy_claim=False)
        rows.append(row)
        ev.save(output/'bags'/(bag+'.json'), row)
        ev.save(output/'access.json', dict(test_evaluated=False, access=store.access))
        print('TRAIN', bag, {n: records[n]['outputs'] for n in order}, flush=True)
    ev.save(output/'results.json', dict(**source, rows=rows, completed_utc=now(),
            purpose='Restricted-input replay and timing, NOT reference accuracy or parameter fitting'))


def freeze(output, training):
    if output.exists():
        raise FileExistsError('Never overwrite a candidate freeze')
    training_result = json.loads((training/'results.json').read_text())
    source = provenance()
    if training_result['source_sha256'] != source['source_sha256']:
        raise AssertionError('Source changed after train diagnostics')
    ev.save(output, dict(**source, frozen_utc=now(),
        train_results_sha256=ev.sha(training/'results.json'),
        selection='Only preregistered candidate; no parameter tuning',
        scope='One evaluation on reused validation, not an independent final test'))
    print('FROZEN', output, ev.sha(output), flush=True)


def validate_bag(bag):
    bind_candidate_factory()
    return protocol.validate_bag(bag)


def write_csv(output, clean, stress):
    fields = ['split', 'bag', 'group', 'receiver', 'model', 'fault', 'start', 'end',
              'n', 'coverage', 'rmse', 'mae', 'bias', 'p95', 'event_rmse',
              'recovery_s', 'false_stop_samples', 'distance_rmse']
    with output.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in clean + stress:
            fault = row.get('fault', {})
            for receiver, scores in row['receivers'].items():
                for name in (BASE_NAME, NAME):
                    metrics = scores[name]
                    item = dict(split='validation', bag=row['bag'], group=row['group'], receiver=receiver,
                                model=name, fault=fault.get('kind', 'clean'),
                                start=fault.get('start'), end=fault.get('end'),
                                distance_rmse=protocol.metric_value(metrics, 'distance'))
                    item.update({key: metrics.get(key) for key in fields if key not in item})
                    writer.writerow(item)


def report(output, decision, clean, stress):
    entries = decision['candidates']
    base, candidate = entries[BASE_NAME], entries[NAME]
    lines = ['# H10: совместный observer [v, d]', '',
             '**Вывод: '+decision['conclusion']+'. Не готов к merge.**', '',
             'Baseline: `'+BASE+'`, профиль adaptive_v5. Один вариант qd=0.04; параметры не подбирались.',
             'Общий evaluator, его hashes, data split, Timeline, fault-окна и reference-маски не менялись.',
             'Состояние и config заморожены до первого validation-bag. Train reference не открывался; final test не использован.', '',
             '| Метрика | adaptive_v5 | H10 | Изменение |', '|---|---:|---:|---:|']
    for key in ('clean_rmse', 'fault_rmse', 'pooled_rmse', 'distance_rmse', 'samples',
                'false_stops_clean', 'false_stops_fault', 'unrecovered'):
        b, a = base[key], candidate[key]
        delta = f'{100*(a/b-1):+.6f}%' if b else ('0' if a == b else f'{a-b:+}')
        lines.append(f'| {key} | {b:.9g} | {a:.9g} | {delta} |')
    lines += ['', '## Причины отказа / ограничения', '',
              '```json', json.dumps(decision['contract_rejection_reasons'], ensure_ascii=False, indent=2), '```', '',
              '## Все per-bag / receiver clean-регрессии', '',
              '| Bag | Receiver | Baseline RMSE | H10 RMSE | Δ, м/с | Порог превышен |',
              '|---|---|---:|---:|---:|---|']
    for row in clean:
        for receiver, scores in row['receivers'].items():
            b, a = scores[BASE_NAME]['rmse'], scores[NAME]['rmse']
            if b is not None and a is not None and a > b:
                veto = a > b + max(.005, .05*b)
                lines.append(f'| {row["bag"]} | {receiver} | {b:.9f} | {a:.9f} | {a-b:+.9f} | {veto} |')
    lines += ['', '## Воспроизводимость', '',
              f'{len(clean)} validation-bag, {len(stress)} fault-сценариев. Полные clean/fault результаты: `results.json`, `bags/*.json`, `comparison.csv`; доступ к данным: `access.json`.',
              'Предыдущие v4/v5 показатели проверяются неизменной `reproduce_published_v5` до принятия решения.',
              'Train `wall_us_per_output` — время offline replay с Timeline и сбором массивов, не ROS publisher-to-subscriber latency.', '',
              '## Не доказано', '',
              'Независимое обобщение: validation уже использовался ранее. Distance — скалярный переякоренный surrogate, не xyz.',
              'Полный ROS end-to-end benchmark H10 с лимитами 2 CPU / 500 MB здесь не запускался. Unit-тесты, fixed-size state и replay не доказывают соблюдение всех runtime-бюджетов.',
              'Ковариация локально-линеаризованная: uncertainty actuator-state не входит в [v,d]. Проекция состояния и robust R не дают калиброванный доверительный интервал.',
              'Согласованная common-mode ошибка двух колёс остаётся неидентифицируемой без независимого источника. Никакие GNSS/IMU не входят в observer.',
              'Default, опубликованные отчёты, исторический freeze/final test и main не изменены.']
    output.write_text('\n'.join(lines)+'\n')


def validation(output, frozen, workers):
    frozen_data = json.loads(frozen.read_text())
    actual = provenance()
    for key in ('source_ref', 'source_sha256', 'immutable_sha256', 'models', 'operational'):
        if frozen_data[key] != actual[key]:
            raise AssertionError('Candidate/evaluator changed after freeze: ' + key)
    output.mkdir(parents=True, exist_ok=False)
    ev.save(output/'started.json', dict(**actual, started_utc=now(), freeze_sha256=ev.sha(frozen)))
    store = ex.Store()
    clean, stress, access = [], [], []
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row, faults, journal in pool.map(validate_bag, store.plan['splits']['validation']):
            clean.append(row)
            stress.extend(faults)
            access.extend(journal)
            ev.save(output/'bags'/(row['bag']+'.json'), dict(clean=row, stress=faults))
            ev.save(output/'access.json', dict(test_evaluated=False, access=access))
            print('VALIDATION', row['bag'], flush=True)
    reproduction = protocol.reproduce_published_v5(clean)
    names = ['v4_default', BASE_NAME, NAME]
    decision = protocol.decide(clean, stress, names)
    reasons = list(decision['candidates'][NAME]['rejection_reasons'])
    # The written contract says EACH primary aggregate, including pooled RMSE.
    # This adds a veto at the same 0.5% threshold; it never relaxes v6 decide().
    b, a = decision['candidates'][BASE_NAME], decision['candidates'][NAME]
    if a['pooled_rmse'] > b['pooled_rmse'] * 1.005:
        reasons.append('pooled_rmse_regression')
    decision['contract_rejection_reasons'] = sorted(set(reasons))
    decision['accuracy_contract_passed'] = not reasons
    decision['runtime_end_to_end_measured'] = False
    decision['conclusion'] = 'отвергнута' if reasons else 'недостаточно данных: точность прошла, полный runtime не проверен'
    decision['merge_ready'] = False
    ev.save(output/'results.json', dict(**actual, freeze_sha256=ev.sha(frozen), clean=clean, stress=stress,
            baseline_reproduction=reproduction, elapsed_s=time.perf_counter()-started, completed_utc=now()))
    ev.save(output/'decision.json', decision)
    write_csv(output/'comparison.csv', clean, stress)
    report(output/'REPORT.md', decision, clean, stress)
    print(json.dumps(decision, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('train', 'freeze', 'validation'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--training', type=Path)
    parser.add_argument('--freeze', type=Path)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error('workers must be between 1 and 8')
    if args.stage == 'train':
        train(args.output)
    elif args.stage == 'freeze':
        if args.training is None:
            parser.error('--training is required for freeze')
        freeze(args.output, args.training)
    else:
        if args.freeze is None:
            parser.error('--freeze is required for validation')
        validation(args.output, args.freeze, args.workers)


if __name__ == '__main__':
    main()

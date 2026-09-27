"""Job entry point; fits only TRAIN, selects only VALIDATION."""
from copy import deepcopy
import json
import math
import sys
import traceback
import numpy as np
from ..catalog import merge, source_digest, resolved_config
from ..data import read_bag, write_json
from ..experiments import run_experiment
from ..types import VEHICLE_TOPICS
from .service import manifest, split_for, run_config, artifact, validate_request
from .storage import Settings, Store, now


def set_parameter(values, dotted, value):
    parts = dotted.split('.')
    for key in parts[:-1]:
        values = values.setdefault(key, {})
    values[parts[-1]] = value


def sample_parameters(ranges, rng):
    result = {}
    for key, spec in sorted(ranges.items()):
        if 'values' in spec:
            value = spec['values'][int(rng.integers(len(spec['values'])))]
        else:
            value = float(rng.uniform(spec['min'], spec['max']))
        set_parameter(result, key, value)
    return result


def execute(settings, store, job):
    request, identity = job['request'], job['id']
    validate_request(settings, job['kind'], request)
    results = []
    def log(message):
        store.log(identity, message)
    def run(selection, name, bags=None, weights=None):
        output = settings.runs / ('web_' + identity) / name
        config = run_config(settings, request, selection, output, bags)
        if weights:
            overrides = selection.get('parameters', {})
            if selection.get('artifact'):
                overrides = merge(artifact(settings, selection['artifact']).get('parameters', {}), overrides)
            config['estimator'] = resolved_config(selection['id'], overrides, weights)
        summary = run_experiment(config, progress=log)
        run_id = output.relative_to(settings.runs).as_posix()
        write_json(output / 'web.json', dict(model_id=selection['id'], job_id=identity, label=request.get('name', ''), kind=job['kind']))
        results.append(run_id)
        store.update(identity, result=dict(runs=results))
        return summary, run_id

    if job['kind'] == 'experiment':
        for i, selection in enumerate(request['models']):
            log(f'Модель {i+1}/{len(request["models"])}: {selection["id"]}')
            run(selection, f'{i+1:02d}_{selection["id"]}')
        return dict(runs=results)

    split = split_for(settings, request)
    by_id = {r['id']: r for r in manifest(settings)['bags']}
    selection = deepcopy(request['models'][0])
    model_id = selection['id']
    weights = None
    parameters = selection.get('parameters', {})
    if selection.get('artifact'):
        previous = artifact(settings, selection['artifact'])
        parameters = merge(previous.get('parameters', {}), parameters)
        weights = previous.get('weights')
    trials = []
    if job['kind'] == 'train':
        from ..training.fit import fit_training
        def trips():
            for i, bag in enumerate(split['splits']['train']):
                record = by_id[bag]
                log(f'TRAIN {i+1}/{len(split["splits"]["train"])}: {bag}')
                events = [e for e in read_bag(record, settings.cache, settings.dataset / 'tram_vehicle_msgs/msg') if e.topic in VEHICLE_TOPICS]
                yield bag, events, record['start_ns'], record['end_ns']
        weights = fit_training(trips, learn_residual=model_id == 'C')
        log('Веса обучены. Проверка на validation…')
        summary, run_id = run(selection, 'validation', split['splits']['validation'], weights)
    else:
        rng = np.random.default_rng(int(request.get('seed', 42)))
        budget = int(request.get('budget', 24))
        baseline_coverage = None
        baseline_prediction_coverage = None
        best = None
        for i in range(budget):
            candidate = parameters if i == 0 else merge(parameters, sample_parameters(request['ranges'], rng))
            picked = dict(selection, parameters=candidate)
            log(f'Подбор {i+1}/{budget}')
            try:
                metrics, run_id = run(picked, f'trial_{i:03d}', split['splits']['validation'], weights)
                aggregate = metrics['aggregate']
                coverage = aggregate['coverage']
                if i == 0:
                    baseline_coverage = coverage
                    baseline_prediction_coverage = aggregate['prediction_coverage']
                rmse = aggregate['pooled_speed']['rmse_mps']
                floor = float(request.get('coverage_floor', .95))
                eligible = (rmse is not None and math.isfinite(rmse) and coverage >= baseline_coverage * floor
                            and aggregate['prediction_coverage'] >= baseline_prediction_coverage * floor)
                trial = dict(index=i, parameters=candidate, rmse_mps=rmse, coverage=coverage,
                             prediction_coverage=aggregate['prediction_coverage'], eligible=eligible, run_id=run_id, metrics=metrics)
                if eligible and (best is None or rmse < best['rmse_mps']):
                    best = trial
            except (ValueError, FloatingPointError) as exc:
                if i == 0:
                    raise
                trial = dict(index=i, parameters=candidate, eligible=False, error=str(exc))
                log(f'Кандидат отклонён: {exc}')
            trials.append(trial)
            write_json(settings.runs / ('web_' + identity) / 'trials.json', trials)
        if best is None:
            raise ValueError('Нет допустимых кандидатов с эталоном и требуемым покрытием')
        parameters, summary = best['parameters'], best['metrics']
        log(f'Выбран кандидат {best["index"]}, RMSE {best["rmse_mps"]:.6f} м/с')

    folder = settings.models / identity
    folder.mkdir(exist_ok=False)
    model = dict(id=identity, name=request.get('name') or f'{model_id} · {now()[:19]}', model_id=model_id,
                 parameters=parameters, weights=weights, created=now(), seed=request.get('seed', 42),
                 split=split, source_sha256=source_digest(), validation=summary, kind=job['kind'],
                 test_used=False, training_source='TRAIN wheels only' if job['kind'] == 'train' else 'parameter search on VALIDATION',
                 trials=trials, parent_artifact=selection.get('artifact'), request=request)
    write_json(folder / 'artifact.json', model)
    return dict(runs=results, artifact=identity)


def main():
    settings = Settings.environment()
    store = Store(settings)
    identity = sys.argv[1]
    try:
        result = execute(settings, store, store.get(identity))
        if store.get(identity)['status'] != 'cancelling':
            store.update(identity, status='succeeded', result=result)
    except Exception as exc:
        store.log(identity, traceback.format_exc())
        if store.get(identity)['status'] != 'cancelling':
            store.update(identity, status='failed', error=str(exc))
        raise


if __name__ == '__main__':
    main()

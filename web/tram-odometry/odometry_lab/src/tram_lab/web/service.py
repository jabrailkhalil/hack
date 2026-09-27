"""Dataset selection and reproducible run configuration (also used by jobs)."""
from functools import lru_cache
import json
from pathlib import Path
from ..catalog import registry, resolved_config
from ..data import build_manifest, make_split
from ..experiments import select_records
from .storage import safe_path


@lru_cache(maxsize=4)
def _manifest(dataset, cache, stamp):
    return build_manifest(dataset, cache)


def manifest(settings):
    archive = settings.dataset / 'data.zip'
    source = archive if archive.exists() else settings.dataset
    stat = source.stat()
    return _manifest(str(settings.dataset), str(settings.cache), (stat.st_mtime_ns, stat.st_size))


def split_for(settings, request):
    data = manifest(settings)
    split = make_split(data, request.get('split', 'chronological'), request.get('train_vehicle', '30618'))
    for subset in ('train', 'validation'):
        selected = request.get(subset + '_bags')
        if selected:
            if len(set(selected)) != len(selected) or not set(selected) <= set(split['splits'][subset]):
                raise ValueError('Поездки должны принадлежать выбранной ' + subset + '-выборке, без повторов')
            split['splits'][subset] = selected
    groups = [set(split['bag_hashes'][i] for i in split['splits'][s]) for s in ('train', 'validation', 'test')]
    if any(groups[a] & groups[b] for a, b in [(0, 1), (0, 2), (1, 2)]):
        raise ValueError('Пересечение выборок по содержимому поездок')
    return split


def selected_bags(settings, request):
    bags = request.get('bags') or split_for(settings, request)['splits'][request.get('subset', 'validation')]
    return [r['id'] for r in select_records(manifest(settings), bags)]


def artifact(settings, identity):
    return json.loads(safe_path(settings.models, identity + '/artifact.json').read_text(encoding='utf-8'))


def model_config(settings, selection):
    if not isinstance(selection, dict) or not isinstance(selection.get('id'), str):
        raise ValueError('Модель должна содержать строковый id')
    model_id = selection['id']
    weights = None
    parameters = selection.get('parameters', {})
    if not isinstance(parameters, dict):
        raise ValueError('Параметры модели должны быть JSON-объектом')
    if selection.get('artifact'):
        stored = artifact(settings, selection['artifact'])
        if stored['model_id'] != model_id:
            raise ValueError('Артефакт принадлежит другой модели')
        from ..catalog import merge
        parameters = merge(stored.get('parameters', {}), parameters)
        weights = stored.get('weights')
    config = resolved_config(model_id, parameters, weights)
    from ..estimators import make_estimator
    make_estimator(config)  # validate before enqueueing
    return config


def validate_parent_split(settings, identity, split):
    """Frozen weights and selected parameters must not leak across a new split."""
    validation = {split['bag_hashes'][i] for i in split['splits']['validation']}
    test = {split['bag_hashes'][i] for i in split['splits']['test']}
    visited = set()
    while identity:
        if identity in visited:
            raise ValueError('Циклическая ссылка между версиями модели')
        visited.add(identity)
        stored = artifact(settings, identity)
        origin = stored['split']
        hashes = origin['bag_hashes']
        trained = {hashes[i] for i in (stored.get('weights') or {}).get('training_ids', []) if i in hashes}
        selected = {hashes[i] for i in origin['splits']['validation']} if stored['kind'] == 'tune' else set()
        if trained & (validation | test) or selected & test:
            raise ValueError('Сохранённая версия использовала поездки нового validation/test. Выберите совместимое разбиение или исходную модель')
        identity = stored.get('parent_artifact')


def run_config(settings, request, selection, output, bags=None):
    return dict(dataset=str(settings.dataset), cache=str(settings.cache),
                msg_dir=str(settings.dataset / 'tram_vehicle_msgs/msg'), output=str(output),
                bags=bags or selected_bags(settings, request), estimator=model_config(settings, selection),
                period_ms=50, tolerance_ms=50, seed=int(request.get('seed', 42)),
                faults=request.get('faults', []), quality=request.get('quality', {}), plots=False)


def validate_request(settings, kind, request):
    if kind not in ('experiment', 'train', 'tune'):
        raise ValueError('Неизвестный тип задания')
    json.dumps(request, allow_nan=False)
    selections = request.get('models', [])
    if not isinstance(selections, list) or not 1 <= len(selections) <= 16:
        raise ValueError('Выберите от 1 до 16 моделей')
    if not isinstance(request.get('quality', {}), dict):
        raise ValueError('Настройки качества должны быть JSON-объектом')
    for selection in selections:
        model_config(settings, selection)
    from ..faults import inject_faults
    list(inject_faults([], request.get('faults', [])))
    if kind == 'experiment':
        selected_bags(settings, request)
    else:
        if len(selections) != 1:
            raise ValueError('Для обучения или подбора выберите одну модель')
        split = split_for(settings, request)
        if selections[0].get('artifact'):
            validate_parent_split(settings, selections[0]['artifact'], split)
        if not split['splits']['train'] or not split['splits']['validation']:
            raise ValueError('Нужны непустые train и validation')
        if kind == 'train' and not registry()[selections[0]['id']]['training']:
            raise ValueError('Для этой модели доступен подбор параметров, но не обучение весов')
        if kind == 'tune':
            if not 2 <= int(request.get('budget', 24)) <= 200:
                raise ValueError('Бюджет подбора должен быть от 2 до 200')
            if not 0 < float(request.get('coverage_floor', .95)) <= 1:
                raise ValueError('Минимальное покрытие должно быть в (0,1]')
            if not isinstance(request.get('ranges'), dict) or not request['ranges']:
                raise ValueError('Укажите диапазоны параметров')
            names = {p['name'] for p in registry()[selections[0]['id']]['parameters']}
            import math
            for key, spec in request['ranges'].items():
                if key not in names:
                    raise ValueError('Неизвестный параметр подбора: ' + key)
                if 'values' in spec:
                    if not spec['values'] or not all(isinstance(v, (bool, int, float)) and math.isfinite(v) for v in spec['values']):
                        raise ValueError('Нужен непустой список конечных значений')
                elif not all(math.isfinite(spec.get(k, float('nan'))) for k in ('min', 'max')) or spec['min'] > spec['max']:
                    raise ValueError('Некорректный диапазон ' + key)


def runs(settings):
    result = []
    for path in settings.runs.rglob('metrics.json'):
        if not (path.parent / 'config.json').exists():
            continue
        try:
            metrics = json.loads(path.read_text(encoding='utf-8'))
            config = json.loads((path.parent / 'config.json').read_text(encoding='utf-8'))
            result.append(dict(id=path.parent.relative_to(settings.runs).as_posix(),
                               config=config, metrics=metrics, updated=path.stat().st_mtime))
        except (OSError, ValueError):
            continue
    return sorted(result, key=lambda r: r['updated'], reverse=True)

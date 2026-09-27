"""Model registry shared by web and CLI. Plugins are trusted local configuration."""
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
from .hack_adapter import PROFILES, profile

ROOT = Path(__file__).parent


def merge(base, changes):
    result = deepcopy(base)
    for key, value in changes.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def model_document():
    return json.loads((ROOT / 'training/model.json').read_text())


def parameter_schema(values, prefix=''):
    result = []
    for key, value in values.items():
        name = prefix + key
        if isinstance(value, dict):
            result.extend(parameter_schema(value, name + '.'))
        elif isinstance(value, (int, float, bool)):
            unit = 'м/с²' if key.endswith('mps2') else 'м/с' if key.endswith('mps') else 'с' if key.endswith('_s') else 'кг' if key.endswith('_kg') else ''
            result.append(dict(name=name, default=value, type='boolean' if isinstance(value, bool) else 'number', unit=unit))
    return result


def registry():
    fitted = model_document()
    common = dict(wheel_scale=1/3.6, stale_after_s=.5, innovation_gate_mps=.75,
                  dynamics=fitted['dynamics'])
    specs = {}
    def add(key, label, factory, defaults, training=False, aliases=()):
        specs[key] = dict(id=key, label=label, factory=factory, defaults=defaults,
                          training=training, aliases=list(aliases), parameters=parameter_schema(defaults))
    for key, label in [('front', 'Передняя тележка'), ('rear', 'Задняя тележка'), ('mean', 'Среднее колёс')]:
        add(key, label, 'tram_lab.estimators:WheelEstimator', dict(name=key, wheel_scale=1/3.6, stale_after_s=.5))
    for key, label, cls in [('A', 'A · устойчивое объединение', 'concept_a:RobustEstimator'),
                            ('B', 'B · адаптивный EKF', 'concept_b:AdaptiveEKF'),
                            ('C', 'C · EKF с поправкой', 'concept_c:ResidualEKF')]:
        defaults = deepcopy(common)
        if key == 'C':
            defaults['residual_model'] = fitted['residual']
        add(key, label, 'tram_lab.hypotheses.' + cls, defaults, True, ['hack/experiments/tram-' + key.lower()])
    add('H1', 'H1 · перенос времени', 'tram_lab.hypotheses.round2.h01:Estimator',
        dict(common, age_transport=True, physics=False), aliases=['hack/experiments/tram-h01'])
    add('H2', 'H2 · поздние измерения', 'tram_lab.hypotheses.round2.h02:Estimator',
        dict(common, history_s=.5), aliases=['hack/experiments/tram-h02'])
    for key in PROFILES:
        doc = profile(key)
        defaults = dict(profile=key, core=doc['config'], wheel_scale=1/3.6)
        if 'readout' in doc:
            defaults['readout'] = doc['readout']
        add(key, key.replace('_', ' ') + ' · native', 'tram_lab.hack_adapter:HackEstimator', defaults)
    from .research.models import register as register_research
    register_research(add, specs)
    custom = os.environ.get('TRAM_MODEL_REGISTRY')
    if custom and Path(custom).is_file():
        for item in json.loads(Path(custom).read_text()):
            if item['id'] in specs:
                raise ValueError('duplicate model id')
            add(item['id'], item['label'], item['factory'], item.get('defaults', {}))
    return specs


def resolved_config(model_id, parameters=None, weights=None):
    spec = registry()[model_id]
    parameters = parameters or {}
    def validate(given, defaults):
        for key, value in given.items():
            if key not in defaults:
                raise ValueError('Unknown model parameter: ' + key)
            if isinstance(value, dict):
                if not isinstance(defaults[key], dict):
                    raise ValueError('Invalid model parameter: ' + key)
                validate(value, defaults[key])
            elif isinstance(value, str) and key in ('name', 'profile') and value != defaults[key]:
                raise ValueError('Model identity cannot be overridden')
    validate(parameters, spec['defaults'])
    config = deepcopy(spec['defaults'])
    if weights:
        config['dynamics'] = weights['dynamics']
        if model_id == 'C':
            config['residual_model'] = weights['residual']
    config = merge(config, parameters)
    return dict(config, factory=spec['factory'])


def source_digest():
    digest = hashlib.sha256()
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.json'):
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()

import json
from dataclasses import asdict
from pathlib import Path
import numpy as np
import pytest

from tram_lab.catalog import registry, resolved_config, source_digest
from tram_lab.estimators import make_estimator
from tram_lab.hack_adapter import HackEstimator
from tram_lab.metrics import evaluate, path_series
from tram_lab.replay import replay
from tram_lab.types import Event, FRONT, REAR, COMMAND, MASTER_VEL, Estimate
from tram_lab.vendor.hack.core import Sample
from tram_lab.web.geometry import route_geometry, project
from tram_lab.web.series import envelope_indices, clean
from tram_lab.web.storage import Settings, Store, safe_path
from tram_lab.web.jobs import sample_parameters

BASE = 1786353518961320453


def event(topic, t, value, sequence=0, delay=0):
    return Event(topic, BASE+round(t*1e9), BASE+round((t+delay)*1e9), sequence,
                 {'position' if topic == COMMAND else 'velocity': value})


@pytest.mark.parametrize('model_id', list(registry()))
def test_registry_causal_reset_and_no_reference_inputs(model_id):
    model = make_estimator(resolved_config(model_id))
    events = [event(FRONT, 0, 36, 0), event(REAR, 0, 36, 1)]
    first = list(replay(events, model, BASE, BASE+500_000_000))
    model.reset(resolved_config(model_id))
    second = list(replay(events, model, BASE, BASE+500_000_000))
    assert [(x.velocity, x.distance) for x in first] == [(x.velocity, x.distance) for x in second]
    assert all(x.time_ns == BASE+i*50_000_000 for i, x in enumerate(first))
    assert first[0].velocity == pytest.approx(10)
    with pytest.raises(ValueError):
        model.update(Event(MASTER_VEL, BASE, BASE, 3, {'x': 100, 'y': 0}))


@pytest.mark.parametrize('model_id', ['hack_v5', 'hack_v6', 'hack_v7', 'hack_v8'])
def test_hack_exact_kernel_parity_and_epoch_precision(model_id):
    adapter = make_estimator(resolved_config(model_id))
    native = make_estimator(resolved_config(model_id)).observer
    for i in range(20):
        offset = i*50_000_000
        for seq, topic in enumerate((COMMAND, FRONT, REAR)):
            adapter.update(Event(topic, BASE+offset, BASE+offset, i*3+seq,
                                 {'position': 3} if topic == COMMAND else {'velocity': 36+i*.01}))
        actual = adapter.predict(BASE+offset)
        expected = native.step(offset/1e9, Sample(offset/1e9, .2),
                               Sample(offset/1e9, (36+i*.01)/3.6), Sample(offset/1e9, (36+i*.01)/3.6))
        assert actual.velocity == pytest.approx(expected.v, abs=1e-12)
        assert actual.distance == pytest.approx(expected.s, abs=1e-12)


def test_hack_future_headers_wait_and_late_duplicate_rejected():
    model = make_estimator(resolved_config('hack_v8'))
    for i, topic in enumerate((FRONT, REAR)):
        model.update(Event(topic, BASE+100_000_000, BASE, i, {'velocity': 36}))
    assert model.predict(BASE).velocity is None
    assert model.predict(BASE+50_000_000).velocity is None
    assert model.predict(BASE+100_000_000).velocity == 10
    model.update(Event(FRONT, BASE, BASE+110_000_000, 3, {'velocity': 99}))
    out = model.predict(BASE+150_000_000)
    assert out.diagnostics['rejected_values'] == 1
    assert out.velocity < 11
    with pytest.raises(ValueError):
        model.predict(BASE)


def test_segment_path_charts_equal_metric_and_gaps():
    estimates = [Estimate(BASE+i*50_000_000, 2., i*.1, 'ok') for i in range(7)]
    gnss = [Event(MASTER_VEL, BASE+i*50_000_000, BASE+i*50_000_000, i, {'x': 1., 'y': 0.}) for i in [0,1,2,4,5,6]]
    metrics, detail = evaluate(estimates, gnss, tolerance_ns=0)
    paths = path_series(detail['time_ns'], detail['distance'], detail['reference'], detail['matched'])
    assert np.isnan(paths['distance_error'][3])
    assert paths['reference_distance'][4] == 0
    assert paths['local_distance'][4] == 0
    assert metrics['path']['rmse_m'] == pytest.approx(np.sqrt(np.nanmean(paths['distance_error']**2)))
    assert paths['path_segment'].tolist() == [0,0,0,-1,1,1,1]


def fix(t, lon, status=0):
    return Event('/sensing/gnss/master/fix', BASE+round(t*1e9), BASE+round(t*1e9), 0,
                 dict(latitude=55., longitude=lon, status=status))


def test_route_projection_anchor_no_clamp_and_gaps():
    route = route_geometry([fix(0,37),fix(.1,37.0001),fix(.2,37.0002),fix(.3,37.1,-1),
                            fix(2,37.001),fix(2.1,37.0011)], BASE)
    assert len(route['segments']) == 2
    t = np.array([0., .1, .2, .5, 2, 2.1])
    predicted, actual, segments = project(route, t, np.array([50.,51.,500.,501.,502.,503.]))
    np.testing.assert_allclose(predicted[0], [55,37])
    assert predicted[1,1] < actual[1,1]  # no point-by-point GNSS correction
    assert np.isnan(predicted[2]).all()  # no endpoint clamping
    assert np.isnan(actual[3]).all()
    assert segments[3] == -1
    assert predicted[4,1] == pytest.approx(37.001)
    empty = route_geometry([], BASE)
    assert empty['source'] is None
    assert np.isnan(project(empty, t, np.zeros(len(t)))[0]).all()


def test_decimation_keeps_fault_peak_gaps_and_segment_boundaries():
    values = np.zeros(10000); values[137] = 100; values[5431] = -99; values[1500:1700] = np.nan
    segments = np.zeros(10000); segments[3001:] = 1
    selected = envelope_indices([values], segments, 100)
    assert {0,9999,137,5431,1499,1500,1699,1700,3000,3001} <= set(selected)
    assert clean([np.nan,np.inf,3.]) == [None,None,3.]


def test_rover_geometry_accepts_iterator():
    from dataclasses import replace
    events = (replace(fix(i/10, 37+i*.0001), topic='/sensing/gnss/rover/fix') for i in range(4))
    result = route_geometry(events, BASE)
    assert result['source'] == 'rover'
    assert len(result['segments']) == 1


def test_training_selection_cannot_include_test(monkeypatch):
    from tram_lab.web import service
    data = {'bags': [dict(id=f'a_{i}', canonical_id=f'a_{i}', vehicle='a', start_ns=i, sha256=f'h{i}') for i in range(20)]}
    monkeypatch.setattr(service, 'manifest', lambda _: data)
    original = service.split_for(None, {})
    with pytest.raises(ValueError):
        service.split_for(None, {'train_bags': original['splits']['test']})
    selected = service.split_for(None, {'train_bags': original['splits']['train'][:2]})
    assert len(selected['splits']['train']) == 2


def test_queue_restart_cancel_and_path_boundary(tmp_path):
    settings = Settings(*(tmp_path / p for p in ['dataset','cache','runs','models','state']))
    store = Store(settings)
    job = store.create('experiment', {'seed': 42})
    assert store.claim()['id'] == job['id']
    assert store.claim() is None
    store.recover()
    assert store.get(job['id'])['status'] == 'interrupted'
    second = store.create('experiment', {})
    assert store.cancel(second['id'])['status'] == 'cancelled'
    with pytest.raises(ValueError):
        safe_path(tmp_path, '../escape')


def test_search_repeatable_nested_and_discrete():
    ranges = {'core.max_age_s': {'min': .1, 'max': .5}, 'physics': {'values': [True, False]}}
    a = np.random.default_rng(42); b = np.random.default_rng(42)
    assert [sample_parameters(ranges,a) for _ in range(12)] == [sample_parameters(ranges,b) for _ in range(12)]
    assert len(source_digest()) == 64


def test_explicit_tuning_parameters_override_frozen_weights():
    from tram_lab.catalog import model_document
    weights = model_document()
    config = resolved_config('B', {'dynamics':{'tau_traction_s':.7}}, weights)
    assert config['dynamics']['tau_traction_s'] == .7
    assert config['dynamics']['coefficients'] == weights['dynamics']['coefficients']


def test_saved_weights_cannot_leak_into_new_split(monkeypatch):
    from tram_lab.web import service
    split = dict(bag_hashes={'a': 'hash-a', 'b': 'hash-b', 'c': 'hash-c'},
                 splits={'train': ['a'], 'validation': ['b'], 'test': ['c']})
    stored = dict(split=split, kind='train', weights={'training_ids':['a']})
    monkeypatch.setattr(service, 'artifact', lambda *_: stored)
    service.validate_parent_split(None, 'version', split)
    # The new validation bag has the same contents as a prior training bag.
    changed = dict(bag_hashes=split['bag_hashes'], splits={'train':['b'], 'validation':['a'], 'test':['c']})
    with pytest.raises(ValueError, match='Сохранённая версия'):
        service.validate_parent_split(None, 'version', changed)
    stored['kind'] = 'tune'
    changed = dict(bag_hashes=split['bag_hashes'], splits={'train':['a'], 'validation':['c'], 'test':['b']})
    with pytest.raises(ValueError, match='Сохранённая версия'):
        service.validate_parent_split(None, 'version', changed)


def test_fit_reproducible_and_no_truth_labels():
    from tram_lab.training.fit import fit_training
    from tram_lab.training.synthetic import generate, BASE_NS, DURATION_S
    events = generate(1)[0]
    trips = [('train-only', events, BASE_NS, BASE_NS + int(DURATION_S*1e9))]
    a = fit_training(trips, learn_residual=True)
    b = fit_training(trips, learn_residual=True)
    assert a == b
    assert a['training_ids'] == ['train-only']
    assert not a['test_used_for_fit']
    with pytest.raises(ValueError, match='insufficient'):
        fit_training([('empty', [], BASE_NS, BASE_NS+1_000_000_000)])


def test_api_contract_and_local_origin(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    for key in ['dataset','cache','runs','models','state']:
        monkeypatch.setenv('TRAM_'+key.upper(), str(tmp_path/key))
    import importlib
    import tram_lab.web.app as module
    module = importlib.reload(module)
    with TestClient(module.app) as client:
        assert client.get('/api/v1/health').json()['status'] == 'ok'
        assert len(client.get('/api/v1/models').json()['models']) >= 12
        assert client.post('/api/v1/jobs', json={'kind':'experiment','request':{}}).status_code == 400
        assert client.post('/api/v1/jobs', json={}, headers={'Origin':'https://unrelated.example'}).status_code == 403
        assert client.get('/api/v1/download', params={'run':'..','file':'secret.json'}).status_code == 400
        assert client.get('/api/v1/jobs/missing').status_code == 404

"""Regression cases discovered during review; synthetic, not accuracy evidence."""
from copy import deepcopy
from dataclasses import replace
import json
import pytest
from test_research_integration import route_doc, fix, rows, fixture_service
from tram_lab.research.route import Route
from tram_lab.research.localization import Fix, Policy, Localizer
from tram_lab.web import research_api as api
from tram_lab.types import Event


def test_late_first_fix_cannot_reopen_initial_window():
    a=Localizer(Route(route_doc()))
    for r in rows(81): a.step(r['time_ns'],r['distance'])
    result=a.step(4_050_000_000,40.5,[fix(4.05,140.5)])
    assert result['status']=='UNLOCALIZED'
    assert a.last_decisions[0]['reason']=='initial_window_expired'


def test_initial_only_cannot_reinitialize_after_raw_reset():
    a=Localizer(Route(route_doc()),Policy(initial_only=True))
    a.step(0,5.,[fix(0)])
    result=a.step(50_000_000,0.,[fix(.05,200.)])
    assert result['status']=='UNLOCALIZED'
    assert a.counts['initialized']==1


def test_nan_fix_status_is_not_a_valid_observation():
    a=Localizer(Route(route_doc()))
    result=a.step(0,0.,[replace(fix(0),status=float('nan'))])
    assert result['status']=='UNLOCALIZED'


def test_frame_change_is_rejected():
    a=Localizer(Route(route_doc()))
    a.step(0,0.,[replace(fix(0),frame_id='gps')])
    result=a.step(50_000_000,.5,[replace(fix(.05,110.5),frame_id='wrong')])
    assert result['route_s']==pytest.approx(100.5)
    assert a.last_decisions[0]['reason']=='frame_mismatch'


def test_correction_bound_is_not_arbitrarily_large():
    with pytest.raises(ValueError): Policy(max_correction_m=100.)


def test_route_keeps_an_immutable_source_snapshot():
    d=route_doc();r=Route(d);d['paths'][0]['points'][1][0]=2000
    assert r.document['paths'][0]['points'][1][0]==1000


def test_missing_run_membership_refuses_existing_prediction(fixture_service):
    settings,records,client,_=fixture_service
    path=settings.runs/'base/config.json';cfg=json.loads(path.read_text());cfg['bags']=[];path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='membership'):api.load_prediction(settings,'base',records[0]['id'])


def test_oversized_json_float_is_rejected(fixture_service):
    _,_,client,_=fixture_service
    response=client.post('/api/v1/research/compare',content='{"x":1e999}')
    assert response.status_code==400
    assert 'finite' in response.text.lower()


def test_raw_gap_does_not_draw_an_unbroken_old_anchor():
    a=Localizer(Route(route_doc()));a.step(0,0.,[fix(0)])
    result=a.step(5_000_000_000,50.,[])
    assert result['status']=='UNLOCALIZED'


def test_closed_route_wraps_without_a_fake_clamp():
    d=route_doc([[0,0,0],[100,0,0],[100,100,0],[0,100,0],[0,0,0]])
    d['paths'][0]['closed']=True
    r=Route(d)
    assert r.point('line',410.)==pytest.approx((10,0,0))


def test_bad_first_fix_does_not_starve_the_startup_window():
    ev=[Event('/sensing/gnss/master/fix',i*100_000_000,i*100_000_000,i,
              dict(latitude=55.,longitude=37.,altitude=103.,status=-1 if i==0 else 0),
              frame_id='gps') for i in range(41)]
    selected=list(api.selected_fixes(ev,'master',30.,0,Route(route_doc()),initial_window_s=3.))
    assert len(selected)==31 and selected[0].status==-1 and selected[1].status==0
    assert all(f.initialization_only for f in selected)
    data=api.replay_localization(rows(100),selected,Route(route_doc()),Policy())
    assert data['counts']['initial_only']['initialized']==1
    assert data['counts']['sparse']['initialized']==1
    assert data['counts']['sparse'].get('corrected',0)==0


def test_closed_route_projection_keeps_unwrapped_lap():
    d=route_doc([[0,0,0],[100,0,0],[100,100,0],[0,100,0],[0,0,0]])
    d['paths'][0]['closed']=True;r=Route(d)
    projection,_=r.project((.127,0,3),(-9.873,0,3),path='line',expected_s=410.)
    assert projection.s==pytest.approx(410.)


def test_empty_frame_fails_closed():
    a=Localizer(Route(route_doc()))
    result=a.step(0,0.,[replace(fix(0),frame_id='')])
    assert result['status']=='UNLOCALIZED'
    assert a.last_decisions[0]['reason']=='frame_mismatch'


def test_whole_artifact_has_identity_and_source_hashes(fixture_service):
    settings,records,client,_=fixture_service
    response=client.post('/api/v1/research/localize',json=dict(run='candidate',bag=records[0]['id'],route=route_doc(),period_s=1))
    assert response.status_code==200,response.text
    data=response.json();stored=json.loads((settings.runs/data['artifact_run']/'result.json').read_text())
    assert stored['artifact_run']==data['artifact_run']
    assert stored['total_points']==len(stored['points'])==100
    assert len(stored['implementation_sha256'])==5


def test_duplicate_provenance_row_is_not_silently_accepted(fixture_service):
    settings,records,client,_=fixture_service
    path=settings.runs/'base/provenance.json';d=json.loads(path.read_text());d['bags'].append(d['bags'][0]);path.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='hash'):api.load_prediction(settings,'base',records[0]['id'])


def test_thinning_does_not_hide_reordered_events():
    ev=[Event('/sensing/gnss/master/fix',int(t*1e9),int(t*1e9),i,
              dict(latitude=55.,longitude=37.,altitude=103.,status=0),frame_id='gps') for i,t in enumerate((1.,.9))]
    with pytest.raises(ValueError,match='receipt order'):
        list(api.selected_fixes(ev,'master',30.,0,Route(route_doc())))


def test_register_preserves_every_existing_model(monkeypatch):
    from tram_lab import catalog
    from tram_lab.research import models
    register=models.register
    monkeypatch.setattr(models,'register',lambda *_:None)
    before=catalog.registry()
    monkeypatch.setattr(models,'register',register)
    after=catalog.registry()
    assert set(after)-set(before)=={models.MODEL_ID}
    assert all(after[key]==value for key,value in before.items())
    cfg=catalog.resolved_config(models.MODEL_ID)
    assert cfg['factory']=='tram_lab.hack_adapter:HackEstimator'
    assert cfg['profile']=='hack_v8'
    assert cfg['core']['max_brake_force_n']==45568.80940352644


def test_closed_route_requires_explicit_topological_closure():
    d=route_doc();d['paths'][0]['closed']=True
    with pytest.raises(ValueError,match='repeat'):Route(d)


def test_no_second_initialization_after_gap_even_with_a_good_fix():
    a=Localizer(Route(route_doc()),Policy(initial_only=True))
    a.step(0,0.,[fix(0)])
    a.step(50_000_000,None)
    value=a.step(100_000_000,1.,[fix(.1,101.)])
    assert value['status']=='UNLOCALIZED'
    assert a.counts['initialized']==1 and a.last_decisions[0]['reason']=='restart_required'


def test_ecef_independent_pyproj_oracle():
    pyproj=pytest.importorskip('pyproj')
    import random
    from tram_lab.research.route import ecef
    converter=pyproj.Transformer.from_crs('EPSG:4979','EPSG:4978',always_xy=True)
    rng=random.Random(20260926)
    for _ in range(500):
        lat,lon,alt=rng.uniform(-89,89),rng.uniform(-180,180),rng.uniform(-100,5000)
        assert ecef(lat,lon,alt)==pytest.approx(converter.transform(lon,lat,alt),abs=2e-8,rel=0.)

"""Synthetic implementation tests. None of these numbers are real-bag accuracy."""
from copy import deepcopy
from dataclasses import asdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from tram_lab.research.models import candidate_defaults, register, MODEL_ID, TRACTION
from tram_lab.research.route import Route, to_enu, ecef
from tram_lab.research.localization import Localizer, Policy, Fix, ANTENNAS
from tram_lab.hack_adapter import HackEstimator, profile
from tram_lab.types import Event, FRONT, REAR, COMMAND
from tram_lab.web import research_api as api


def route_doc(points=None):
    return {'schema':'tram-route-enu-v1','frame':'ENU','source':'SYNTHETIC TEST ONLY',
            'origin_wgs84':[55.,37.,100.], 'reference_point':'base_link','height_reference':'unknown',
            'paths':[{'id':'line','direction':'forward','points':points or [[0.,0.,0.],[1000.,0.,0.]]}]}


def fix(t, base_s=100., receiver='master', received=None, lateral=0.):
    return Fix(round(t*1e9), round((t if received is None else received)*1e9),
               (base_s+ANTENNAS[receiver][0],lateral,3.), receiver)


def rows(n=100):
    return [dict(time_ns=i*50_000_000, distance=i*.5,velocity=10.,reference=10.,matched=True) for i in range(n)]


def test_candidate_exact_two_parameter_changes():
    base=profile('hack_v8'); c=candidate_defaults()
    assert {k for k in c['core'] if c['core'][k]!=base['config'][k]}==set(TRACTION)
    assert c['readout']==base['readout'] and c['profile']=='hack_v8'
    assert c['core']['max_brake_force_n']==45568.80940352644


def test_config_not_shared_and_baseline_not_changed():
    before=profile('hack_v8');a=candidate_defaults();a['core']['max_brake_force_n']=0
    assert candidate_defaults()['core']['max_brake_force_n']==45568.80940352644
    assert profile('hack_v8')==before


def test_registry_adapter_uses_existing_factory():
    seen={}
    def add(key,label,factory,defaults):seen[key]=dict(factory=factory,defaults=defaults)
    register(add,seen)
    assert seen[MODEL_ID]['factory']=='tram_lab.hack_adapter:HackEstimator'
    assert seen[MODEL_ID]['research']['status']=='PREPARED_NOT_ACCURACY_VALIDATED'


def test_candidate_matches_independent_native_lab_adapter():
    a,b=HackEstimator(),HackEstimator();a.reset(candidate_defaults())
    d=profile('hack_v8');c=dict(profile='hack_v8',core=deepcopy(d['config']),readout=d['readout'],wheel_scale=1/3.6)
    c['core'].update(TRACTION);b.reset(c)
    for i in range(600):
        t=1_700_000_000_000_000_000+i*50_000_000
        events=[Event(COMMAND,t,t,3*i,{'position':4 if i<300 else -4})]
        if i%2==0 and not 200<i<250:
            events.extend([Event(FRONT,t,t,3*i+1,{'velocity':12.}),Event(REAR,t,t,3*i+2,{'velocity':12.})])
        for e in events:a.update(e);b.update(e)
        assert a.predict(t)==b.predict(t)
        assert vars(a.observer)==vars(b.observer)


def test_candidate_rejects_gnss_input_and_keeps_guards():
    a=HackEstimator();a.reset(candidate_defaults())
    with pytest.raises(ValueError):a.update(Event('/sensing/gnss/master/fix',0,0,0,{}))
    assert a.observer.c.common_mode_quarantine_s==1.5
    assert a.observer.c.adaptation_tau_s==.5


@pytest.mark.parametrize('origin',[(0.,0.,0.),(55.,37.,100.),(-45.,150.,-10.)])
def test_geodetic_origin_maps_to_zero(origin):
    assert to_enu(*origin,origin)==pytest.approx((0.,0.,0.),abs=1e-9)


def test_geodetic_equator_axes():
    east=to_enu(0.,.001,0.,(0.,0.,0.));north=to_enu(.001,0.,0.,(0.,0.,0.))
    assert east[0]>111 and abs(east[1])<1e-9
    assert north[1]>110 and abs(north[0])<1e-9


@pytest.mark.parametrize('key,value',[('frame','MGRS'),('reference_point','antenna'),('origin_wgs84',[float('nan'),0,0]),('height_reference','made-up'),('source',''),('paths',[])])
def test_route_schema_fails_closed(key,value):
    doc=route_doc();doc[key]=value
    with pytest.raises(ValueError):Route(doc)


@pytest.mark.parametrize('points',[[[0,0,0],[0,0,0]],[[0,0,0],[0,0,5]],[[0,0,0],[5000,0,0]],[[0,0],[1,0]]])
def test_degenerate_route_rejected(points):
    with pytest.raises(ValueError):Route(route_doc(points))


@pytest.mark.parametrize('receiver',['master','rover'])
def test_lever_arm_east_and_north(receiver):
    for pts,xyz in [([[0,0,0],[1000,0,0]],(100+ANTENNAS[receiver][0],0,3)),
                    ([[0,0,0],[0,1000,0]],(0,100+ANTENNAS[receiver][0],3))]:
        match,reason=Route(route_doc(pts)).project(xyz,ANTENNAS[receiver])
        assert reason=='accepted' and match.s==pytest.approx(100.)


def test_full_pitch_rotation_not_fixed_world_axis():
    pts=[[0,0,0],[100,0,10]];route=Route(route_doc(pts));s=50
    base=route.point('line',s);length=math.sqrt(10100)
    ex=(100/length,0,10/length);ez=(-10/length,0,100/length)
    lever=ANTENNAS['master'];xyz=tuple(base[k]+lever[0]*ex[k]+lever[2]*ez[k] for k in range(3))
    match,_=route.project(xyz,lever)
    assert match.s==pytest.approx(s)


def test_parallel_paths_abstain_but_explicit_path_works():
    d=route_doc();d['paths'].append({'id':'parallel','direction':'forward','points':[[0,.1,0],[1000,.1,0]]})
    r=Route(d);match,reason=r.project((90.127,.05,3),ANTENNAS['master'])
    assert match is None and reason=='ambiguous_route'
    assert r.project((90.127,.05,3),ANTENNAS['master'],path='line')[0].s==pytest.approx(100)


def test_endpoint_not_clamped():
    r=Route(route_doc());assert r.point('line',1000)==(1000,0,0)
    assert r.point('line',1000.01) is None and r.point('line',-.01) is None


def test_initialization_and_raw_distance_separate():
    a=Localizer(Route(route_doc()));result=a.step(0,7.,[fix(0)])
    assert result['route_s']==pytest.approx(100.) and result['raw_distance']==7.
    assert result['offset_m']==pytest.approx(93.)


def test_bounded_correction_no_speed_or_integral_reset():
    a=Localizer(Route(route_doc()),Policy(gain=1,max_correction_m=2))
    a.step(0,0.,[fix(0)]);r=a.step(50_000_000,.5,[fix(.05,110.5)])
    assert r['route_s']==pytest.approx(102.5) and r['raw_distance']==.5
    assert a.last_decisions[0]['correction_m']==pytest.approx(2)


def test_delayed_fix_uses_source_time_not_arrival_time():
    a=Localizer(Route(route_doc()));a.step(0,0.,[fix(0)])
    for i in range(1,17):
        batch=[fix(.5,105.,received=.8)] if i==16 else []
        result=a.step(i*50_000_000,i*.5,batch)
    assert result['route_s']==pytest.approx(108.) and a.offset==pytest.approx(100.)


@pytest.mark.parametrize('case,expected',[
    (Fix(100_000_000,50_000_000,(100,0,3)),'future_fix'),
    (Fix(50_000_000,100_000_000,(100,0,3)),'future_fix'),
    (Fix(50_000_000,50_000_000,(100,100,3)),'outside_gate'),
    (Fix(50_000_000,50_000_000,(100,0,3),'master',-1),'invalid_fix'),
    (Fix(50_000_000,50_000_000,(float('nan'),0,3)),'invalid_coordinate')])
def test_fix_vetoes(case,expected):
    a=Localizer(Route(route_doc()));a.step(0,0.,[fix(0)]);a.step(50_000_000,.5,[case])
    assert a.last_decisions[0]['reason']==expected


def test_stale_duplicate_and_innovation_veto():
    a=Localizer(Route(route_doc()));a.step(0,0.,[fix(0)])
    a.step(50_000_000,.5,[fix(0),fix(.05,200.)])
    assert [x['reason'] for x in a.last_decisions]==['duplicate_or_reordered','outside_gate']
    a.step(1_000_000_000,10.,[fix(.1,101.,received=1.)])
    assert a.last_decisions[0]['reason']=='stale_fix'


def test_no_gnss_stays_unlocalized():
    a=Localizer(Route(route_doc()))
    for r in rows():
        output=a.step(r['time_ns'],r['distance']);assert output['status']=='UNLOCALIZED'
        assert output['raw_distance']==r['distance']


def test_history_is_bounded_and_clock_reset_explicit():
    a=Localizer(Route(route_doc()))
    for i in range(10000):a.step(i*50_000_000,float(i))
    assert len(a.history)<=128
    with pytest.raises(ValueError):a.step(0,0.)


def test_reverse_or_lost_segment_does_not_keep_old_anchor():
    a=Localizer(Route(route_doc()));a.step(0,5.,[fix(0)])
    result=a.step(50_000_000,4.);assert result['status']=='UNLOCALIZED'
    a.step(100_000_000,None);r=a.step(150_000_000,7.)
    assert r['status']=='UNLOCALIZED'


def test_future_extension_and_reference_changes_do_not_affect_prefix():
    r=Route(route_doc());short=rows(50);long=rows(100)
    a=api.replay_localization(short,[fix(0),fix(4.,141.)],r,Policy())
    b=api.replay_localization(long,[fix(0),fix(4.,999.)],r,Policy())
    assert a['points']==b['points'][:50]
    changed=deepcopy(short)
    for row in changed:row['reference']=999.;row['matched']=False
    assert api.replay_localization(changed,[fix(0)],r,Policy())['points']==a['points']


@pytest.mark.parametrize('field,value',[('gain',0),('gain',1.1),('max_age_s',float('nan')),('max_age_s',3),('lateral_gate_m',-1),('gain',True)])
def test_invalid_policy(field,value):
    with pytest.raises(ValueError):Policy(**{field:value})


def test_thinning_before_quality_no_same_slot_replacement():
    ev=[Event('/sensing/gnss/master/fix',i*1_000_000_000,i*1_000_000_000,i,
              dict(latitude=55.,longitude=37.,altitude=100.,status=-1 if i==0 else 0)) for i in range(11)]
    chosen=list(api.selected_fixes(ev,'master',10.,0,Route(route_doc())))
    assert [f.stamp_ns for f in chosen]==[0,10_000_000_000] and chosen[0].status==-1


def test_scope_missing_reference_not_zero():
    a=rows(4);b=deepcopy(a)
    for row in a+b:row['reference']=None;row['matched']=False
    metric=api.compare_predictions(a,b)
    summary=api.summarize_pairs([dict(group='g',**metric)])
    assert summary['baseline']['group_macro_rmse_mps'] is None and summary['candidate']['samples']==0


@pytest.mark.parametrize('field,value',[('time_ns',9),('reference',9),('matched',False),('velocity',None)])
def test_comparison_rejects_schedule_reference_or_coverage_drift(field,value):
    a=rows(3);b=deepcopy(a);b[0][field]=value
    with pytest.raises(ValueError):api.compare_predictions(a,b)


def test_pooled_and_group_macro_not_conflated():
    rs=[dict(group=g,baseline=dict(count=n,sse=n*rmse**2,rmse_mps=rmse),candidate=dict(count=n,sse=n*rmse**2,rmse_mps=rmse)) for g,n,rmse in [('a',1,1.),('b',9,3.)]]
    summary=api.summarize_pairs(rs)['baseline']
    assert summary['group_macro_rmse_mps']==2. and summary['pooled_rmse_mps']==pytest.approx(math.sqrt(8.2))


def test_role_denied_before_prediction_read(tmp_path):
    with pytest.raises(ValueError,match='development'):api.load_prediction(SimpleNamespace(runs=tmp_path),'missing','30618_NOT_DEVELOPMENT')


@pytest.mark.parametrize('name',['../secret','/etc/passwd','',None])
def test_artifact_path_safety(tmp_path,name):
    with pytest.raises(ValueError):api.inside(tmp_path,name)


@pytest.fixture
def fixture_service(tmp_path,monkeypatch):
    pins=api.contract()['development'];pin=next(p for p in pins if p['bag'].startswith('30618_'))
    other=next(p for p in pins if p['bag'].startswith('30639_'))
    settings=SimpleNamespace(runs=tmp_path/'runs',cache=tmp_path/'cache',dataset=tmp_path/'dataset')
    records=[dict(id=p['bag'],sha256=p['sha256'],start_ns=0,duration_ns=5_000_000_000,vehicle=p['bag'].split('_')[0],canonical_id=p['bag']) for p in (pin,other)]
    configs=[]
    for identity,delta in [('base',0.),('candidate',.1)]:
        folder=settings.runs/identity;folder.mkdir(parents=True)
        config={'bags':[r['id'] for r in records], 'estimator':candidate_defaults(),'faults':[],'quality':{},'seed':42,'period_ms':50,'tolerance_ms':50}
        (folder/'provenance.json').write_text(json.dumps({'bags':records}))
        (folder/'config.json').write_text(json.dumps(config))
        for record in records:
            p=folder/'bags'/record['id'];p.mkdir(parents=True)
            with (p/'predictions.csv').open('w',newline='') as stream:
                w=csv.DictWriter(stream,fieldnames=['time_ns','velocity_mps','distance_m','reference_mps','matched']);w.writeheader()
                for row in rows():w.writerow(dict(time_ns=row['time_ns'],velocity_mps=10.+delta,distance_m=row['distance'],reference_mps=10.,matched=True))
    service=ModuleType('tram_lab.web.service');service.manifest=lambda _: {'bags':records}
    captured=[];service.validate_request=lambda settings,kind,req:captured.append((kind,req))
    monkeypatch.setitem(sys.modules,'tram_lab.web.service',service)
    data=ModuleType('tram_lab.data')
    def read_bag(*args):
        for i in range(50):
            # Synthetic geographic fixes, not an extracted real bag.
            t=i*.1;s=100+10*t
            yield Event('/sensing/gnss/master/fix',round(t*1e9),round(t*1e9),i,
                dict(latitude=55.,longitude=37+(s-9.873)/(111320*math.cos(math.radians(55))),altitude=103.,status=0), frame_id='gps')
    data.read_bag=read_bag;monkeypatch.setitem(sys.modules,'tram_lab.data',data)
    store=SimpleNamespace(create=lambda kind,request:dict(id='synthetic-test-job',status='queued',kind=kind,request=request))
    app=FastAPI()
    @app.exception_handler(ValueError)
    def invalid(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)
    app.include_router(api.router_for(settings,store))
    return settings,records,TestClient(app),captured


def test_compare_scopes_preserve_other_vehicle(fixture_service):
    s,records,client,_=fixture_service
    payload=dict(baseline='base',candidate='candidate',bags=[r['id'] for r in records],vehicle='30618')
    response=client.post('/api/v1/research/compare',json=payload);assert response.status_code==200
    r=response.json();assert len(r['rows'])==1 and r['excluded_by_vehicle']==[records[1]['id']]
    assert r['summary']['candidate']['pooled_rmse_mps']==pytest.approx(.1)
    payload['vehicle']='all';assert len(client.post('/api/v1/research/compare',json=payload).json()['rows'])==2


def test_real_router_enqueue_has_fixed_pair_and_dev_scope(fixture_service):
    _,records,client,captured=fixture_service
    response=client.post('/api/v1/research/enqueue',json={'bags':[records[0]['id']]})
    assert response.status_code==202 and response.json()['request']['models']==[{'id':'hack_v8'},{'id':MODEL_ID}]
    assert captured[0][0]=='experiment'
    assert client.post('/api/v1/research/enqueue',json={'bags':['hidden-test']}).status_code==400


def test_router_assets_and_bad_json(fixture_service):
    _,_,client,_=fixture_service
    html=client.get('/api/v1/research/page');assert html.status_code==200 and 'Content-Security-Policy' in html.headers
    assert client.get('/api/v1/research/page.js').status_code==200
    assert client.post('/api/v1/research/compare',content='{"x":NaN}').status_code==400
    assert client.post('/api/v1/research/compare',content='x'*2_500_001).status_code==413


def test_route_replay_artifact_and_original_csv_unchanged(fixture_service):
    settings,records,client,_=fixture_service
    path=settings.runs/'candidate/bags'/records[0]['id']/'predictions.csv';before=path.read_bytes()
    request=dict(run='candidate',bag=records[0]['id'],route=route_doc(),period_s=1,receiver='master')
    response=client.post('/api/v1/research/localize',json=request);assert response.status_code==200,response.text
    result=response.json();assert result['official_xyz_score'] is None and result['reference_not_used'] is True
    assert result['counts']['sparse']['initialized']==1 and result['counts']['sparse']['corrected']>=1
    assert path.read_bytes()==before
    assert (settings.runs/result['artifact_run']/'result.json').is_file()
    assert result['points'][10]['raw_distance']==5. and result['points'][10]['velocity']==pytest.approx(10.1)


def test_pipeline_rejects_missing_geometry_before_bag_io(fixture_service):
    _,records,client,_=fixture_service
    response=client.post('/api/v1/research/localize',json=dict(run='candidate',bag=records[0]['id'],route={}))
    assert response.status_code==400 and 'ENU' in response.text


def test_equal_counts_do_not_hide_different_available_ticks():
    a=rows(3);b=deepcopy(a)
    a[0]['velocity']=None;b[1]['velocity']=None
    with pytest.raises(ValueError,match='paired ticks'):
        api.compare_predictions(a,b)

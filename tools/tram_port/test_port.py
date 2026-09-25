"""Contract tests for the native integration, separate from algorithm quality."""
from pathlib import Path
import sys,math
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'vendor/hack'),str(ROOT/'vendor/ours')]
from reserve_odometry.core import Sample,Config,Observer
from reserve_odometry.timeline import Timeline
from ports import OurObserver,our_factory
from tram_lab.types import Event,COMMAND,FRONT,REAR
import native_functions as nf

METHODS=['mean','A','B','C','H1_10','H2_050']

@pytest.mark.parametrize('name',METHODS)
def test_port_exact_direct_parity(name):
    port=OurObserver(name);direct=our_factory(name);keys=[None]*3;seq=0
    held=[None,None,None]
    for i in range(81):
        now=i*.05
        held[0]=Sample(now,.2 if i<40 else -.2)
        if i%2==0:held[1]=Sample(now-.025,5+now*.01)
        if i%2==1:held[2]=Sample(now-.015,5+now*.01)
        got=port.step(now,*held)
        for j,(topic,s) in enumerate(zip((COMMAND,FRONT,REAR),held)):
            if s is not None and (s.t,s.value)!=keys[j]:
                keys[j]=(s.t,s.value)
                direct.update(Event(topic,round(s.t*1e9),round(now*1e9),seq,
                    {'position' if j==0 else 'velocity':s.value*(15 if j==0 else 3.6)}))
                seq+=1
        want=direct.predict(round(now*1e9))
        if want.velocity is None:assert got.mode=='WAITING_FOR_INITIALIZATION'
        else:
            assert got.v==want.velocity
            assert got.s==want.distance

@pytest.mark.parametrize('name',METHODS)
def test_port_native_timeline_reset_repeat(name):
    tl=Timeline(OurObserver(name),delay_s=0.)
    def series():
        result=[]
        for i in range(21):
            t=i*.05
            for ch,value in [(0,0.),(1,5.),(2,5.)]:
                tl.ingest(ch,Sample(t,value))
                result.extend(e for e,_ in tl.advance())
        return result
    first=series();tl.reset();second=series()
    assert first==second

@pytest.mark.parametrize('name',METHODS)
def test_future_input_rejected_and_no_external_initialization(name):
    port=OurObserver(name)
    with pytest.raises(ValueError):port.step(0.,None,Sample(1.,5.),None)
    with pytest.raises(ValueError):port.reset(velocity=4.)

def test_native_matching_tie_convention():
    # Native matcher selects later point on an exact tie.
    assert nf.match([(0.,1.),(.0625,2.)],np.array([.03125]))[0]==2.

def test_native_speed_metrics():
    result=nf.metrics(np.array([0.,.05,.1]),np.array([1.,3.,5.]),np.array([1.,2.,3.]),np.array([1,1,1],bool))
    assert result['rmse']==pytest.approx(math.sqrt(5/3))
    assert result['bias']==1.
    assert result['integrated_error_m_not_xyz']==pytest.approx(.1)

def test_native_path_no_gap_bridging():
    t=np.arange(61)*.05;pred=np.column_stack((t,np.full(61,2.),2*t,np.zeros((61,3))))
    reference=np.ones(61);reference[25:35]=np.nan
    result=nf.distance_surrogate(pred,reference)
    assert result['continuous_spans']==2
    assert result['full_span_terminal_error_m'] is None

def test_d_native_route_parity():
    from reserve_odometry.route import Route as HackRoute
    from tram_lab.hypotheses.concept_d import Route as OurRoute
    for points in ([(0,0,0),(10,0,0),(10,10,0)],[(0,0,0),(3,4,5),(8,12,7)]):
        a=HackRoute(points);b=OurRoute(points)
        s=np.linspace(0,a.arc[-1],401)
        np.testing.assert_allclose([a.at(x)[0] for x in s],b.position(s),rtol=0,atol=2e-14)
        assert all(abs(sum(x*x for x in a.at(t)[1])-1)<1e-14 for t in s)

def test_fixed_source_blobs():
    import hashlib
    expected={'core.py':'a382e484f10208c6ea2fa0d9260b6876308724f8','timeline.py':'e98b17c1a4d47d825ef2ad26b06094784da3a452','guarded_readout.py':'4b9033fd2a3ff88be3a7f82cb178d37041769e46'}
    for f,sha in expected.items():
        blob=(ROOT/'vendor/hack/reserve_odometry'/f).read_bytes()
        assert hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()==sha

import json,math,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'src/reserve_odometry'))
from geo_math import ecef,geodetic,LocalENU
from map_model import *
from start_prefix import initial_anchor


def fixture(paths=None):
    if paths is None:paths=[np.array([[0.,0.,0.],[10.,0.,0.]])]
    ts=[dict(id=f'e{i}',bag=f'b{i}',group=f'g{i}',receiver='master',stamp_bounds=[0,10],xyz=x) for i,x in enumerate(paths)]
    return map_value(ts,dict(llh=[55.,37.,170.],bag='fixture',receiver='master',stamp_ns=0),'CONTROL','SYNTHETIC')


class Maps(unittest.TestCase):
    def test_origin(self):
        f=LocalENU((55,37,170));self.assertLess(math.dist(f.forward((55,37,170)),(0,0,0)),1e-12)
    def test_ecef_roundtrip(self):
        for p in [(0,0,0),(45,45,100),(-80,-170,10),(89.99,170,1000),(90,0,0)]:
            q=geodetic(ecef(p));self.assertLess(math.dist(ecef(q),ecef(p)),1e-6)
    def test_enu_roundtrip(self):
        f=LocalENU((55,37,170))
        for x in [(100,200,10),(-5000,1000,-100),(0,0,0)]:self.assertLess(math.dist(x,f.forward(f.reverse(x))),1e-6)
    def test_orthonormal(self):
        a=np.array(LocalENU((55,37,170)).rotation);np.testing.assert_allclose(a@a.T,np.eye(3),atol=1e-15)
    def test_axis_orientation(self):
        f=LocalENU((0,0,0));self.assertGreater(f.forward((0,.001,0))[0],100);self.assertGreater(f.forward((.001,0,0))[1],100)
    def test_invalid_geo(self):
        for p in [(91,0,0),(0,181,0),(0,0,float('nan'))]:
            with self.assertRaises(ValueError):ecef(p)
    def test_rdp_line(self):
        x=np.column_stack([np.arange(100),np.zeros(100),np.zeros(100)]);self.assertEqual(len(rdp(x)),2)
    def test_rdp_corner(self):
        x=np.array([[0,0,0],[5,0,0],[5,5,0]]);np.testing.assert_array_equal(rdp(x),x)
    def test_rdp_loop(self):
        x=np.array([[0,0,0],[5,0,0],[5,5,0],[0,5,0],[0,0,0]]);np.testing.assert_array_equal(rdp(x),x)
    def test_deterministic_bytes(self):
        v=fixture();self.assertEqual(canonical(v),canonical(json.loads(canonical(v))))
    def test_components(self):self.assertTrue(verify_map(fixture())['passed'])
    def test_crossing_not_connected(self):
        v=fixture([np.array([[-10,0,0],[10,0,0]]),np.array([[0,-10,0],[0,10,0]])]);g=as_graph(v)
        self.assertFalse(g.successors('e0'));self.assertEqual(len(g.nearest_candidates((0,0,0),max_distance_m=1,tie_tolerance_m=.25)),2)
    def test_same_edge_loop_ambiguity(self):
        v=fixture([np.array([[-5,-5,0],[5,5,0],[-5,5,0],[5,-5,0]])]);self.assertTrue(SegmentIndex(v,'master').project([[0,0,0]])['ambiguous'][0])
    def test_reverse(self):self.assertLess(verify_map(fixture())['reverse_max_m'],1e-8)
    def test_radius_not_mask(self):
        p=SegmentIndex(fixture(),'master').project([[0,100,0]]);self.assertEqual(p['distance'][0],100)
    def test_missing_layer(self):self.assertTrue(np.isnan(SegmentIndex(fixture(),'rover').project([[0,0,0]])['distance'][0]))
    def test_projection_vs_brute(self):
        rng=np.random.default_rng(48);paths=[rng.normal(size=(7,3))*100 for _ in range(6)];v=fixture(paths);ix=SegmentIndex(v,'master');q=rng.normal(size=(200,3))*200;p=ix.project(q)
        for a,d in zip(q,p['distance']):
            w=a-ix.a;u=np.clip(np.sum(w[:,:2]*ix.d[:,:2],axis=1)/ix.den,0,1)
            want=np.linalg.norm(w[:,:2]-u[:,None]*ix.d[:,:2],axis=1).min();self.assertAlmostEqual(d,want,places=10)
    def test_gap(self):
        t=np.array([0,100000000,200000000,2000000000,2100000000,2200000000]);x=np.column_stack([np.arange(6)*3.,np.zeros(6),np.zeros(6)])
        d={'b':{r:dict(stamp=t,xyz=x,speed=np.ones(6)) for r in ('master','rover')}}
        tracks,_=tracklets(d,{'b':{'group':'g'}},{'b'});self.assertEqual(len(tracks),4)
    def test_slow_map_not_fabricated(self):
        t=np.arange(5)*100000000;x=np.column_stack([np.arange(5),np.zeros(5),np.zeros(5)])
        d={'b':{r:dict(stamp=t,xyz=x,speed=np.zeros(5)) for r in ('master','rover')}}
        tracks,_=tracklets(d,{'b':{'group':'g'}},{'b'});self.assertFalse(tracks)
    def test_robust_support_and_cap(self):
        tracks=[]
        for i,off in enumerate([0.,.2,.4]):
            x=np.column_stack([np.arange(0,40,.5),np.full(80,off),np.zeros(80)])
            tracks.append(dict(id=f'e{i}',bag=f'b{i}',group=f'g{i}',receiver='master',stamp_bounds=[0,100],xyz=x))
        v=control(tracks,dict(llh=[55.,37.,170.]),'SYNTHETIC');c,s=robust(tracks,v,'SYNTHETIC');self.assertGreater(s['supported_anchors'],0);self.assertGreater(s['changed_anchors'],0);self.assertLessEqual(s['max_shift_m'],.5)
        for a,b in zip(v['edges'],c['edges']):self.assertEqual(a['xyz'][0],b['xyz'][0]);self.assertEqual(a['xyz'][-1],b['xyz'][-1])
    def test_single_group_abstention(self):
        tr=dict(id='e0',bag='b0',group='g0',receiver='master',stamp_bounds=[0,1],xyz=np.array([[0.,0.,0.],[10.,0.,0.]]));c=control([tr],dict(llh=[55.,37.,170.]),'SYNTHETIC');r,s=robust([tr],c,'SYNTHETIC');self.assertEqual(s['changed_anchors'],0)
    def test_start_unique(self):
        v=fixture();f=LocalENU(v['frame']['origin']['llh']);llh=f.reverse((1,0,0))
        ev=[dict(receiver='master',kind='fix',record_ns=1,stamp_ns=0,status=0,position=list(llh))]
        ev+=[dict(receiver=r,kind='vel',record_ns=i+2,stamp_ns=0,linear=[1.,0.,0.]) for i,r in enumerate(('master','rover'))]
        self.assertEqual(initial_anchor(ev,0,v)['status'],'ANCHORED_ANTENNA_PROXY')
    def test_prefix_cutoff(self):
        class Poison(dict):
            def __getitem__(self,k):
                if k!='record_ns':raise AssertionError('Future payload read')
                return 3_000_000_001
        a=initial_anchor([],0,fixture());b=initial_anchor([Poison()],0,fixture());self.assertEqual(a,b)
    def test_start_no_teacher(self):
        self.assertEqual(initial_anchor([],0,fixture())['status'],'UNLOCALIZED')
    def test_start_alias_abstention(self):
        v=fixture([np.array([[0.,0.,0.],[10.,0.,0.]])]*2);llh=LocalENU(v['frame']['origin']['llh']).reverse((1,0,0))
        ev=[dict(receiver='master',kind='fix',record_ns=1,stamp_ns=0,status=0,position=list(llh))]
        ev+=[dict(receiver=r,kind='vel',record_ns=i+2,stamp_ns=0,linear=[1.,0.,0.]) for i,r in enumerate(('master','rover'))]
        self.assertEqual(initial_anchor(ev,0,v)['reason'],'AMBIGUOUS_EDGE_OR_ARC')

if __name__=='__main__':unittest.main()

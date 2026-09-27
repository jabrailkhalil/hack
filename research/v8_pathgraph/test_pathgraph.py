import ast
from dataclasses import replace
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from pathgraph import *


def doc(points=None,indices=None):
    p=points or [(0,0,0),(1000,0,0)]
    # Use <=100m spacing to honor the importer connection budget.
    if points is None:p=[(i*10,0,0) for i in range(101)]
    rows=[dict(x=x,y=y,z=z,tang=0.,curv=0.) for x,y,z in p]
    return {'points':rows,'paths':[{'ext_id':None,'point_indices':indices if indices is not None else list(range(len(p)))}]}


class IdentityGrid:
    frame='map'
    def xy(self,lat,lon):return lat,lon


def fixture(mode='sparse'):
    return Localizer([Pathgraph(doc())],IdentityGrid(),Settings(mode=mode))


def stream(loc,seconds=5,offset=20.,start=0):
    rows=[]
    for i in range(start,seconds*20+1):
        ns=i*50000000;raw=i*.1
        fixes=[] if i%2 else [Fix(ns,ns,'rover',raw+offset+ARMS['rover'][0],0.)]
        rows.append(loc.advance(ns,raw,ns,fixes))
    return rows


class MapTests(unittest.TestCase):
    def test_exact_order_indices(self):
        a=Pathgraph(doc([(1,2,3),(5,6,7),(9,10,11)],[0,2,1]))
        self.assertEqual(a.points,[(1.,2.,3.),(9.,10.,11.),(5.,6.,7.)])

    def test_input_not_modified(self):
        a=doc();text=json.dumps(a);Pathgraph(a);self.assertEqual(json.dumps(a),text)

    def test_invalid_indices(self):
        for indices in ([0,10000],[0,True],[0,-1],[1]):
            with self.assertRaises(ValueError):Pathgraph(doc(indices=indices))

    def test_repeated_and_large_gaps_rejected(self):
        for points in ([(0,0,0),(0,0,0)],[(0,0,0),(0,0,10)],[(0,0,0),(500,0,0)]):
            with self.assertRaises(ValueError):Pathgraph(doc(points))

    def test_nonfinite_and_missing_fields(self):
        for key,value in [('x',float('nan')),('curv',None),('tang',True)]:
            d=doc();d['points'][0][key]=value
            with self.assertRaises(ValueError):Pathgraph(d)

    def test_exact_csv_round_trip(self):
        route=Pathgraph(doc())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'r.csv';route.write_csv(path)
            with path.open() as f:points=[tuple(float(row[k]) for k in ('x','y','z')) for row in csv.DictReader(f)]
            self.assertEqual(points,route.points)
            with self.assertRaises(FileExistsError):route.write_csv(path)

    def test_at_never_clamps_or_wraps(self):
        a=Pathgraph(doc())
        for s in (-1,a.length+1,float('nan')):
            with self.assertRaises(ValueError):a.at(s)
        self.assertEqual(a.at(a.length)[0],a.points[-1])

    def test_tangent_wrap(self):
        d=doc([(0,0,0),(-10,0,0)]);d['points'][0]['tang']=math.pi-.1;d['points'][1]['tang']=-math.pi+.1
        self.assertAlmostEqual(abs(Pathgraph(d).at(5)[1]),math.pi)

    def test_lever_arm_along_route(self):
        a=Pathgraph(doc());p,reason=a.project((22.563,0),ARMS['rover'],heading=0)
        self.assertIsNone(reason);self.assertAlmostEqual(p['s'],20)

    def test_rotation_not_scalar_subtraction(self):
        d=doc([(0,0,0),(0,100,0)]);d['points'][0]['tang']=d['points'][1]['tang']=math.pi/2
        a=Pathgraph(d);p,reason=a.project((0,22.563),ARMS['rover'],heading=math.pi/2)
        self.assertIsNone(reason);self.assertAlmostEqual(p['s'],20)

    def test_height_arm_changes_horizontal_on_slope(self):
        a=Pathgraph(doc([(0,0,0),(20,0,2)]));pitch=-math.atan(.1)
        ox=math.cos(pitch)*2.563+math.sin(pitch)*3
        p,_=a.project((10+ox,0),ARMS['rover'],heading=0)
        self.assertAlmostEqual(p['s'],math.sqrt(101))

    def test_wrong_heading_is_not_selected(self):
        p,reason=Pathgraph(doc()).project((20,0),ARMS['rover'],heading=math.pi)
        self.assertIsNone(p)

    def test_cross_and_innovation_gates(self):
        a=Pathgraph(doc())
        self.assertIsNone(a.project((20,500),ARMS['rover'])[0])
        self.assertIsNone(a.project((500,0),ARMS['rover'],expected_s=20)[0])

    def test_ambiguous_self_overlap_rejected(self):
        p=[(0,0,0),(30,0,0),(30,30,0),(0,30,0),(0,0,0),(30,0,0)]
        self.assertEqual(Pathgraph(doc(p)).project((15,0),(0,0,0))[1],'ambiguous_projection')


class GridTests(unittest.TestCase):
    def test_no_silent_crs_assumption(self):
        with self.assertRaises(ValueError):Grid(37,300000,6100000,'map','source')

    def test_explicit_optin(self):
        self.assertFalse(Grid(37,300000,6100000,'map','hypothesis',allow_hypothesis=True).confirmed)

    def test_outside_zone_invalid_coords(self):
        g=Grid(37,0,0,'map','test',confirmed=True)
        for lat,lon in [(-10,38),(85,38),(55,30),(float('nan'),38),(True,38)]:
            with self.assertRaises(ValueError):g.xy(lat,lon)

    def test_grid_region_against_proj(self):
        from pyproj import Transformer
        tf=Transformer.from_crs(4326,32637,always_xy=True);g=Grid(37,300000,6100000,'map','test',confirmed=True)
        for lat in (55.75,55.80,55.85,55.9):
            for lon in (37.3,37.4,37.5,37.6):
                x,y=tf.transform(lon,lat);a,b=g.xy(lat,lon)
                self.assertLess(math.hypot(a-(x-300000),b-(y-6100000)),.002)


class StateTests(unittest.TestCase):
    def test_initializes_only_from_past_fixes(self):
        loc=fixture();rows=stream(loc)
        self.assertIsNone(rows[0]['xyz']);self.assertEqual(loc.counts['initialized'],1)
        self.assertAlmostEqual(rows[-1]['xyz'][0],30)

    def test_no_fix_means_no_position(self):
        loc=fixture()
        for i in range(100):self.assertIsNone(loc.advance(i*50000000,i*.1,i*50000000)['xyz'])

    def test_future_and_stale(self):
        loc=fixture();stream(loc,2)
        ns=3000000000
        loc.advance(ns,6,ns,[Fix(ns+1,ns,'rover',30,0),Fix(0,ns,'rover',30,0)])
        self.assertEqual(loc.counts['future'],1);self.assertEqual(loc.counts['stale'],1)

    def test_receipt_clock_is_independent_of_source_clock(self):
        loc=fixture();stream(loc,2)
        ns=3000000000
        # Delivered on monotonic clock 12345; source UTC is a separate domain.
        loc.advance(ns,6,12345,[Fix(ns,12345,'rover',28.563,0)])
        self.assertNotIn('stale',loc.counts)

    def test_duplicate_bad_status_frame_change(self):
        loc=fixture();stream(loc,2)
        loc.advance(3000000000,6,3000000000,[Fix(3000000000,3000000000,'rover',28.563,0,status=-1)])
        loc.advance(4000000000,8,4000000000,[Fix(4000000000,4000000000,'rover',30.563,0,frame_id='other')])
        loc.advance(5000000000,10,5000000000,[Fix(4000000000,4000000000,'rover',30.563,0)])
        self.assertEqual(loc.counts['bad_status'],1);self.assertEqual(loc.counts['frame_change'],1);self.assertEqual(loc.counts['duplicate_or_reordered'],1)

    def test_course_and_history_bounded(self):
        loc=fixture();stream(loc,80)
        self.assertLessEqual(len(loc.history),256);self.assertLessEqual(len(loc.fix_history),64)
        self.assertLessEqual(len(loc.decisions),1)

    def test_reset_clears_anchor(self):
        loc=fixture();stream(loc);loc.reset()
        self.assertIsNone(loc.offset);self.assertIsNone(loc.advance(0,0,0)['xyz'])

    def test_first_only_does_not_correct(self):
        loc=fixture('first_on_map');stream(loc,40);offset=loc.offset
        stream(loc,80,offset=24,start=801);self.assertEqual(loc.offset,offset)

    def test_fixed_sparse_steps_are_bounded(self):
        loc=fixture();stream(loc,40);before=loc.offset
        stream(loc,80,offset=24,start=801)
        self.assertGreater(loc.offset,before);self.assertLessEqual(loc.offset-before,1.)

    def test_no_teleport_to_other_route_or_past_endpoint(self):
        loc=fixture();stream(loc)
        value=loc.advance(6000000000,1001,6000000000)
        self.assertEqual(value['status'],'OUTSIDE_MAP');self.assertIsNone(value['xyz'])
        self.assertIsNone(loc.advance(7000000000,0,7000000000)['xyz'])

    def test_unlocalized_outside_map_not_forced_to_endpoint(self):
        loc=fixture();rows=stream(loc,20,offset=2000)
        self.assertTrue(all(x['xyz'] is None for x in rows));self.assertNotIn('initialized',loc.counts)

    def test_initial_window_never_reopens(self):
        loc=fixture('initial_window');stream(loc,10,offset=2000)
        rows=stream(loc,20,offset=20,start=201)
        self.assertTrue(all(x['xyz'] is None for x in rows))

    def test_reversal_requires_explicit_reset(self):
        loc=fixture();stream(loc)
        with self.assertRaises(ValueError):loc.advance(0,0,0)

    def test_future_extension_keeps_past(self):
        a=stream(fixture(),10);b=stream(fixture(),15)
        self.assertEqual(a,b[:len(a)])

    def test_settings_validation(self):
        for kwargs in ({'mode':'best'},{'receiver':[]},{'gain':float('nan')},{'max_age_s':10},{'interval_s':0}):
            with self.assertRaises(ValueError):Settings(**kwargs)

    def test_no_reference_input_surface(self):
        source=Path(__file__).with_name('ros_node.py').read_text()
        self.assertNotIn('/localization/',source);self.assertNotIn('/sensing/gnss/rover/vel',source)
        self.assertIn('super().publish(e,held)',source)
        tree=ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign):
                self.assertFalse(any(isinstance(t,ast.Attribute) and t.attr in ('v','s','observer') for t in node.targets))


if __name__=='__main__':unittest.main()

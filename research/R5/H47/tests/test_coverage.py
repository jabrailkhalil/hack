from pathlib import Path
import importlib.util
import io
import json
import math
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('h47_coverage',HERE/'coverage.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class CoverageTests(unittest.TestCase):
    def test_index_matches_pure_reference(self):
        rng=random.Random(470026)
        points=[c.TeacherPoint(rng.uniform(-1,10),rng.uniform(0,15),rng.random()>.2) for _ in range(500)]
        points += points[:20]
        points += [c.TeacherPoint(float('nan'),2.,True),c.TeacherPoint(0.,-1.,True)]
        index=c.IndexedTeacher(points)
        for _ in range(3000):
            t=rng.uniform(-1.1,10.1)
            self.assertEqual(index.nearest(t),c.unique_nearest(points,t))
    def test_nearest_edges_duplicates_and_ties(self):
        for points in ([c.TeacherPoint(0.,2.,True)],
                       [c.TeacherPoint(-.05,2.,True),c.TeacherPoint(.05,3.,True)],
                       [c.TeacherPoint(0.,2.,True),c.TeacherPoint(0.,3.,True)]):
            for t in (0.,.05,-.05,.050000000001,-.050000000001,math.nan):
                self.assertEqual(c.IndexedTeacher(points).nearest(t),c.unique_nearest(points,t))
    def test_episode_does_not_inflate_continuous_fault(self):
        self.assertEqual(c.episode_onsets([i*.1 for i in range(100)]),[0.])
    def test_episode_boundary_is_strict(self):
        self.assertEqual(c.episode_onsets([0.,1.,2.0000001]),[0.,2.0000001])
    def test_episode_duplicates_count_once(self):
        self.assertEqual(c.episode_onsets([3.,0.,0.,3.]),[0.,3.])
    def test_episode_nonfinite_rejected(self):
        with self.assertRaises(ValueError):c.episode_onsets([math.nan])
    def test_group_boundaries(self):
        self.assertTrue(c.qualifies_group(10,100,2))
        for x in [(9,100,2),(10,99,2),(10,100,1)]:self.assertFalse(c.qualifies_group(*x))
    def test_representative_is_metadata_only(self):
        def row(b):return dict(bag=b,split='train',fold='fit',group='g',wire_sha256='w')
        self.assertEqual(c.representatives([row('z'),row('a')]),{'a':'a','z':'a'})
    def test_cross_fold_wire_rejected(self):
        rows=[dict(bag='a',split='train',fold='fit',group='g',wire_sha256='w'),
              dict(bag='b',split='train',fold='check',group='h',wire_sha256='w')]
        with self.assertRaises(ValueError):c.representatives(rows)
    def test_role_gate_precedes_hash_and_sql(self):
        with patch.object(c,'sha',side_effect=AssertionError('IO')),patch.object(c.sqlite3,'connect',side_effect=AssertionError('SQL')):
            for role in ('test','validation','development',None):
                r=dict(bag='x',split=role,fold='fit')
                with self.assertRaises(PermissionError):c.load_vehicle_events(r,'/not-present',io.StringIO())
                with self.assertRaises(PermissionError):c.load_teacher(r,'/not-present',io.StringIO())
    def test_no_training_subcommand(self):
        import subprocess
        p=subprocess.run([sys.executable,str(HERE/'coverage.py'),'train'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('invalid choice',p.stderr)
    def test_real_loader_query_only_allowed_topics(self):
        import inspect
        text=inspect.getsource(c.load_vehicle_events)
        self.assertIn('WHERE t.name IN (?,?,?) ORDER BY m.timestamp,m.id',text)
        self.assertNotIn('/sensing/',text)
        self.assertEqual(len(c.TOPICS),3)
    def test_passive_double_replay_and_labels(self):
        events=[]
        for k in range(81):
            for ch,v in ((0,0.),(1,2.),(2,2.02)):events.append((k*.05,ch,v))
        arrays,stats=c.replay_passive(events)
        self.assertTrue(stats['native_state_and_estimate_exact'])
        self.assertGreater(stats['state_comparisons'],50)
        self.assertLessEqual(stats['max_feature_history'],16)
        self.assertEqual(stats['causal_errors'],0)
        teacher=c.IndexedTeacher([c.TeacherPoint(k*.05,2.,True) for k in range(81)])
        stats=c.label_saved(arrays,teacher)
        self.assertGreater(stats['clean_updates'],0)
        self.assertEqual(stats['fault_updates'],0)
    def test_frozen_label_bounds_both_signs(self):
        for sign in [-1,1]:
            a=c.Sample(0.,sign*2.51);b=c.Sample(0.,sign*2.1);t=c.TeacherPoint(0.,2.,True)
            self.assertEqual(c.proxy_pair_labels(a,b,t,t,features_ready=True),(1,0))
            self.assertIsNone(c.proxy_pair_labels(a,a,t,t,features_ready=True))
    def test_aggregate_does_not_join_episode_onsets_across_bags(self):
        def row(b,t):return dict(bag=b,fold='fit',group='g',ready_pairs=60,clean_updates=100,
                                  fault_updates=10,episode_onsets_s=[t])
        g=c.aggregate([row('a',0.),row('b',100.)],{'a':'a','b':'b'})[0]
        self.assertFalse(g['qualified']);self.assertEqual(g['max_episodes_same_bag'],1)
    def test_aggregate_excludes_wire_duplicates(self):
        def row(b):return dict(bag=b,fold='fit',group='g',ready_pairs=60,clean_updates=50,
                               fault_updates=5,episode_onsets_s=[0.,3.])
        g=c.aggregate([row('a'),row('b')],{'a':'a','b':'a'})[0]
        self.assertEqual((g['clean_updates'],g['fault_updates']),(50,5));self.assertFalse(g['qualified'])
    def test_teacher_ignored_fields_never_deserialized(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'labels.npz'
            c.np.savez(p,stamp_ns=c.np.array([10**18,10**18+50000000],dtype='int64'),
                      speed_mps=c.np.array([2.,2.]),accepted=c.np.array([True,True]),
                      available_after_bag_record_ns=c.np.array([object()],dtype=object))
            r=dict(bag='b',split='train',fold='fit',sensor_start_ns=10**18,
                   teacher=dict(path='labels.npz',sha256=c.sha(p),teacher_rows=2,accepted_rows=2))
            t=c.load_teacher(r,d,io.StringIO());self.assertEqual(t.nearest(0.).speed_magnitude,2.)
    def test_deterministic_npz(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a.npz',Path(d)/'b.npz'
            c.savez(a,dict(x=c.np.array([1.,float('nan')])));c.savez(b,dict(x=c.np.array([1.,float('nan')])))
            self.assertEqual(c.sha(a),c.sha(b))
            with self.assertRaises(FileExistsError):c.savez(a,{})

if __name__=='__main__':unittest.main()

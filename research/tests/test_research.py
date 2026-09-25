"""Research checks; separate from dependency-free runtime unit tests."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/research_v3'))
import experiment as ex
import numpy as np


class ResearchTests(unittest.TestCase):
    def setUp(self):self.store=ex.Store()

    def test_frozen_partition_covers_inventory_once(self):
        roles=self.store.plan['splits'];flat=[b for bs in roles.values() for b in bs]
        self.assertEqual(len(flat),122);self.assertEqual(len(set(flat)),122)
        group_roles={}
        for r in self.store.records.values():group_roles.setdefault(r['group'],set()).add(r['split'])
        self.assertTrue(all(len(v)==1 for v in group_roles.values()))

    def test_test_bag_denied_before_io(self):
        bag=self.store.plan['splits']['test'][0]
        with patch.object(ex.sqlite3,'connect') as connect:
            for role in ['train','validation','test']:
                with self.assertRaises(PermissionError):self.store.load(bag,role)
            connect.assert_not_called()

    def test_validation_cannot_train(self):
        with patch.object(ex.sqlite3,'connect') as connect:
            with self.assertRaises(PermissionError):self.store.load(self.store.plan['splits']['validation'][0],'train')
            connect.assert_not_called()

    def test_development_cannot_be_validation(self):
        with self.assertRaises(PermissionError):self.store.load(self.store.plan['splits']['development'][0],'validation')

    def test_group_intervals_do_not_cross_roles(self):
        rows=list(self.store.records.values())
        for i,a in enumerate(rows):
            for b in rows[:i]:
                if a['vehicle']==b['vehicle'] and a['split']!=b['split']:
                    for start,end in [('start_ns','end_ns'),('sensor_start_ns','sensor_end_ns')]:
                        self.assertGreater(max(a[start],b[start]),min(a[end],b[end])+60_000_000_000)
                    self.assertNotEqual(a['vehicle_wire_sha256'],b['vehicle_wire_sha256'])

    def test_baseline_gauge_roundtrip(self):
        c=ex.configuration(ex.X0);baseline=ex.Config()
        for k,v in ex.asdict(c).items():self.assertAlmostEqual(v,getattr(baseline,k),places=8)

    def test_neutral_dynamics(self):
        a=ex.acceleration(ex.X0,np.zeros(50),np.full(50,5.))
        np.testing.assert_allclose(a,-.0325)

    def test_all_candidates_valid(self):
        for f in ex.MODELS.glob('*.json'):
            d=json.loads(f.read_text());ex.Config(**d['config'])
            if d['fitted']:self.assertTrue(d['solver_success'])

    @staticmethod
    def events():
        return np.array([(i*.05,ch,0. if ch==0 else 5.) for i in range(121) for ch in range(3)])

    def test_future_values_cannot_change_prefix(self):
        events=self.events();changed=events.copy();changed[(changed[:,0]>3)&(changed[:,1]>0),2]=20
        a,_=ex.replay(events,ex.Config());b,_=ex.replay(changed,ex.Config())
        np.testing.assert_equal(a[a[:,0]<=3],b[b[:,0]<=3])

    def test_reference_mutation_only_changes_scores(self):
        events=self.events();config={'baseline_v2':ex.Config()}
        refs={'master':[(t,5.) for t in np.arange(0,6,.05)]}
        before,_=ex.replay(events,config['baseline_v2'])
        original=ex.compare(events,refs,config)
        changed=ex.compare(events,{'master':[(t,50.) for t,_ in refs['master']]},config)
        after,_=ex.replay(events,config['baseline_v2'])
        np.testing.assert_equal(before,after)
        self.assertGreater(changed['receivers']['master']['baseline_v2']['rmse'],original['receivers']['master']['baseline_v2']['rmse']+40)

    def test_missing_reference_is_null(self):
        m=ex.metrics(np.arange(3),np.ones(3),np.full(3,np.nan),np.ones(3,bool))
        self.assertIsNone(m['rmse']);self.assertEqual(m['n'],0)

    def test_reference_nearest_tolerance(self):
        x=ex.match([(1,3.)],np.array([1.,1.04,1.06]))
        self.assertEqual(x[0],3);self.assertTrue(np.isnan(x[2]))

    def test_deletion_changes_no_sensor_input(self):
        events=self.events();a,_=ex.replay(events,ex.Config())
        ex.compare(events,{'master':[]},dict(baseline_v2=ex.Config()))
        b,_=ex.replay(events,ex.Config());np.testing.assert_equal(a,b)

if __name__=='__main__':unittest.main()

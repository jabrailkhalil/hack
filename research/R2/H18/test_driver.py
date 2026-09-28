"""Offline driver checks; scientific dependencies are research-only."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('h18_driver',Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class DriverTests(unittest.TestCase):
    def test_test_and_role_mismatch_denied_before_any_io(self):
        with tempfile.TemporaryDirectory() as d:
            store=r.RoleStore(Path(d)/'access.json')
            with patch.object(r.sqlite3,'connect',side_effect=AssertionError('must not open')), patch.object(r,'sha',side_effect=AssertionError('must not read bytes')):
                for bag in store.plan['splits']['test']:
                    for purpose in ('train','development','validation','test'):
                        with self.assertRaises(PermissionError):store.load(bag,purpose)
                for bag in store.plan['splits']['development']:
                    with self.assertRaises(PermissionError):store.load(bag,'validation')
            self.assertEqual(store.access,[])

    def test_direct_factory_off_and_unchanged_score(self):
        events=r.np.array([(i*.1+j*.001,j,0. if j==0 else 5.) for i in range(601) for j in range(3)])
        refs={n:[(i*.05,5.) for i in range(1201)] for n in ('master','rover')}
        meta=dict(bag='synthetic',group='sanity',role='development')
        with tempfile.TemporaryDirectory() as d:
            row,_=r.paired(events,refs,meta,Path(d),'clean',compatibility=True)
            self.assertTrue(row['disabled_and_canonical_reproduced'])
            self.assertEqual(row['receivers']['master']['main']['rmse'],row['receivers']['master']['candidate']['rmse'])
            for i,(fault,window) in enumerate(r.gc.fault_windows(events)):
                row,_=r.paired(window,refs,meta,Path(d),str(i),fault,compatibility=True)
                self.assertTrue(row['disabled_and_canonical_reproduced'])

    def test_pooled_gate_not_omitted(self):
        b=dict(macro_rmse=1.,fault_macro=1.,pooled_rmse=1.,distance_macro=1.)
        c=dict(b,macro_rmse=.97,pooled_rmse=1.006)
        self.assertIn('aggregate_regression:pooled_rmse',r.gate([],[],dict(main=b,candidate=c)))
        c['pooled_rmse']=1.005
        self.assertEqual(r.gate([],[],dict(main=b,candidate=c)),[])

    def test_zero_baseline_never_divides_by_zero_or_claims_gain(self):
        b=dict(macro_rmse=0.,fault_macro=0.,pooled_rmse=0.,distance_macro=0.)
        self.assertEqual(r.gate([],[],dict(main=b,candidate=b)),['insufficient_gain'])

    def test_false_pair_injection_does_not_change_command_or_reference(self):
        events=r.np.array([(i*.1,j,0. if j==0 else 5.) for i in range(501) for j in range(3)])
        out,fault,start=r.diagnostic_events(events,25.,'after_dropout_false_pair',6.)
        self.assertEqual(start,30.);self.assertEqual(fault['end'],31.)
        self.assertFalse(r.np.any(r.np.isin(out[:,1],(1,2))&(out[:,0]>=25)&(out[:,0]<30)))
        self.assertTrue(r.np.all(out[out[:,1]==0,2]==0.))
        self.assertTrue(r.np.all(out[(out[:,1]>0)&(out[:,0]>=30)&(out[:,0]<31),2]==7.))

if __name__=='__main__':unittest.main()

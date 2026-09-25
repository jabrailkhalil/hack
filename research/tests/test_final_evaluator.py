"""Checks the final-test gate and the explicitly labelled distance surrogate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/finalization'))
import evaluate as ev


class FinalEvaluatorTests(unittest.TestCase):
    def test_heldout_denied_without_authorization_before_io(self):
        store=ev.FinalStore();bag=store.plan['splits']['test'][0]
        with patch.object(ev.sqlite3,'connect') as connect:
            for purpose in ('train','validation','test'):
                with self.assertRaises(PermissionError):store.load(bag,purpose)
            connect.assert_not_called()

    def test_freeze_contains_22_ids_and_no_data_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'freeze.json'
            with patch.object(ev.sqlite3,'connect') as connect:
                ev.freeze(path,'unit-test-source')
                data=ev.verify_freeze(path)
                self.assertEqual(len(data['test_bags']),22)
                self.assertIn('src/reserve_odometry/reserve_odometry/node.py',data['source_sha256'])
                connect.assert_not_called()
                with self.assertRaises(FileExistsError):ev.freeze(path,'other-source')

    def test_source_mutation_invalidates_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'freeze.json';ev.freeze(path,'unit-test')
            with patch.object(ev,'protected_files',return_value={'changed':'hash'}):
                with self.assertRaises(ValueError):ev.verify_freeze(path)

    def test_exact_distance_surrogate(self):
        t=np.arange(41)*.05
        prediction=np.column_stack([t,5+0*t,5*t,5+0*t,5+0*t,0*t])
        score=ev.distance_surrogate(prediction,5+0*t)
        self.assertAlmostEqual(score['full_span_terminal_error_m'],0.)
        self.assertAlmostEqual(score['full_span_reference_distance_m'],10.)
        self.assertAlmostEqual(score['reanchored_span_rmse_m'],0.)

    def test_reference_gap_does_not_claim_full_bag_drift(self):
        t=np.arange(81)*.05;target=5+0*t;target[40]=np.nan
        prediction=np.column_stack([t,5+0*t,5*t,5+0*t,5+0*t,0*t])
        score=ev.distance_surrogate(prediction,target)
        self.assertIsNone(score['full_span_terminal_drift_percent'])
        self.assertEqual(score['continuous_spans'],2)

    def test_missing_reference_is_not_zero_error(self):
        events=np.array([(i*.05,ch,0. if ch==0 else 5.) for i in range(41) for ch in range(3)])
        models,ops=ev.configuration();result=ev.score(events,{'master':[]},models,ops)
        self.assertIsNone(result['receivers']['master']['balanced_physics']['rmse'])

    def test_final_replay_is_causal(self):
        events=np.array([(i*.05,ch,0. if ch==0 else 5.) for i in range(121) for ch in range(3)])
        changed=events.copy();changed[(changed[:,0]>3)&(changed[:,1]>0),2]=20.
        models,ops=ev.configuration();a,_=ev.replay(events,models['balanced_physics'],ops)
        b,_=ev.replay(changed,models['balanced_physics'],ops)
        np.testing.assert_equal(a[a[:,0]<=3],b[b[:,0]<=3])

if __name__=='__main__':unittest.main()

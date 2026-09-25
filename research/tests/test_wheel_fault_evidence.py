"""Prove the shipped guard is the measured one and preserves the original suite."""
import hashlib
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]


class WheelFaultEvidenceTests(unittest.TestCase):
    def test_runtime_is_measured_prototype_and_baseline_is_frozen_v4(self):
        runtime=(ROOT/'src/reserve_odometry/reserve_odometry/core.py').read_bytes()
        prototype=(ROOT/'tools/research_lock/prototype_core.py').read_bytes()
        self.assertEqual(runtime,prototype)
        evidence=json.loads((ROOT/'reports/research_lock/deployment_validation/results.json').read_text())
        self.assertEqual(hashlib.sha256(runtime).hexdigest(),evidence['prototype_sha256'])
        freeze=json.loads((ROOT/'submission/FREEZE.json').read_text())
        original=(ROOT/'tools/research_lock/baseline_core.py').read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),freeze['source_sha256']['src/reserve_odometry/reserve_odometry/core.py'])

    def test_original_metrics_do_not_change_in_either_profile(self):
        data=json.loads((ROOT/'reports/research_lock/deployment_validation/results.json').read_text())
        self.assertEqual(len(data['clean']),19);self.assertEqual(len(data['stress']),76)
        for row in data['clean']+data['stress']:
            for scores in row['receivers'].values():
                for baseline,candidate in [('main_v4','v4_zero_lock'),('main','v5_zero_lock')]:
                    self.assertEqual(scores[baseline],scores[candidate])
        self.assertEqual({a['purpose'] for a in data['access']},{'validation'})
        self.assertFalse(data['test_evaluated'])

    def test_low_speed_extension_passes_for_both_profiles(self):
        data=json.loads((ROOT/'reports/research_lock/deployment_low_speed/results.json').read_text())
        self.assertTrue(data['eligible']);self.assertFalse(data['case_regressions'])
        self.assertEqual(len(data['stress']),38)
        for baseline,candidate in [('main_v4','v4_zero_lock'),('main_v5','v5_zero_lock')]:
            a=data['summary'][candidate];b=data['summary'][baseline]
            self.assertLess(a['event_group_macro_rmse'],b['event_group_macro_rmse']*.95)
            self.assertEqual(a['false_stop_samples'],0)
            self.assertEqual(a['unrecovered'],0)
            for row in data['stress']:
                for scores in row['receivers'].values():
                    a=scores[candidate];b=scores[baseline]
                    self.assertEqual(a['n'],b['n'])
                    self.assertLessEqual(a.get('false_stop_samples',0),b.get('false_stop_samples',0))
                    if b.get('recovery_s') is not None:self.assertIsNotNone(a.get('recovery_s'))
        self.assertEqual({a['purpose'] for a in data['access']},{'validation'})
        self.assertFalse(data['test_evaluated'])

if __name__=='__main__':unittest.main()

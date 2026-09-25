"""Acceptance checks: missing data and faults must not manufacture a winner."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/research_v5'))
import compare as v5
import hashlib
sys.path.insert(0,str(ROOT/'tools'))
from evidence_archive import read_v4


class V5GateTests(unittest.TestCase):
    def rows(self):
        metric = dict(rmse=1., event_rmse=1., n=100, coverage=1., false_stop_samples=0)
        row = dict(bag='bag', group='group', receivers={'master': {'main':metric,
                   'candidate':dict(metric, rmse=.9, event_rmse=.9)}},
                   counts={'main':dict(causal_errors=0), 'candidate':dict(causal_errors=0)})
        return [copy.deepcopy(row)], [copy.deepcopy(row)]

    def test_gain_can_pass(self):
        clean, stress = self.rows()
        self.assertTrue(v5.decision(clean, stress, ['candidate'])['candidate']['eligible'])

    def test_bad_evidence_rejects(self):
        for change in ('coverage', 'n', 'false_stop_samples', 'causal', 'rmse'):
            with self.subTest(change=change):
                clean, stress = self.rows()
                if change == 'causal':
                    clean[0]['counts']['candidate']['causal_errors'] = 1
                else:
                    target = (stress if change == 'false_stop_samples' else clean)[0]['receivers']['master']['candidate']
                    target[change] = {'coverage':.99, 'n':99, 'false_stop_samples':1, 'rmse':1.11}[change]
                self.assertFalse(v5.decision(clean, stress, ['candidate'])['candidate']['eligible'])

    def test_no_reference_rejects(self):
        clean, stress = self.rows()
        for row in clean + stress:
            for score in row['receivers']['master'].values():
                score.update(rmse=None, event_rmse=None, n=0, coverage=0.)
        self.assertFalse(v5.decision(clean, stress, ['candidate'])['candidate']['eligible'])

    def test_unchanged_is_not_a_gain(self):
        clean, stress = self.rows()
        for row in clean + stress:
            row['receivers']['master']['candidate'] = dict(row['receivers']['master']['main'])
        result = v5.decision(clean, stress, ['candidate'])['candidate']
        self.assertIn('insufficient_gain', result['rejection_reasons'])

    def test_selected_profile_matches_evaluated_eligible_candidate(self):
        data = json.loads((ROOT/'reports/research_v5/round3/results.json').read_text())
        expected = json.loads((ROOT/'reports/research_v5/round3/decision.json').read_text())
        self.assertEqual(v5.decision(data['clean'], data['stress'], data['plan']['candidates']), expected)
        profile = json.loads((ROOT/'src/reserve_odometry/config/adaptive_v5.json').read_text())
        self.assertTrue(expected[profile['name']]['eligible'])
        self.assertEqual(profile['config'], data['models'][profile['name']])
        self.assertFalse(data['test_evaluated'])
        self.assertEqual({a['purpose'] for a in data['access']}, {'validation'})
        self.assertEqual(len(data['access']), 19)

    def test_historical_comparison_matches_immutable_archive(self):
        data = json.loads((ROOT/'reports/research_v5/round3/results.json').read_text())
        for path, digest in data['source_sha256'].items():
            self.assertEqual(hashlib.sha256(read_v4(path)).hexdigest(), digest, path)


if __name__ == '__main__':
    unittest.main()

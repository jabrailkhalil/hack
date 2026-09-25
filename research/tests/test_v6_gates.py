"""Selection decisions must remain reproducible and keep held-out data closed."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('compare_v6', ROOT/'tools/research_v6/compare.py')
v6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v6)


class V6GateTests(unittest.TestCase):
    def test_recompute_both_decisions_from_complete_evidence(self):
        for number in (1, 2):
            root = ROOT/f'reports/research_v6/round{number}'
            data = json.loads((root/'results.json').read_text())
            expected = json.loads((root/'decision.json').read_text())
            self.assertEqual(v6.decide(data['clean'], data['stress'], list(data['models'])), expected)
            self.assertTrue(data['baseline_reproduction']['passed'])
            self.assertEqual(data['baseline_reproduction']['max_absolute_delta'], 0.)

    def test_only_validation_measurements_were_opened(self):
        plan = json.loads((ROOT/'research/plan_v3.json').read_text())
        for number in (1, 2):
            access = json.loads((ROOT/f'reports/research_v6/round{number}/access.json').read_text())
            self.assertFalse(access['test_evaluated'])
            self.assertEqual(len(access['access']), 19)
            self.assertEqual({r['purpose'] for r in access['access']}, {'validation'})
            self.assertEqual({r['bag'] for r in access['access']}, set(plan['splits']['validation']))

    def test_fallback_does_not_promote_more_false_stops(self):
        data=json.loads((ROOT/'reports/research_v6/round2/results.json').read_text())
        clean=copy.deepcopy(data['clean'])
        scores=next(iter(clean[0]['receivers'].values()))
        scores['v5_adaptive_05s']['false_stop_samples'] += 100
        decision=v6.decide(clean,data['stress'],list(data['models']))
        self.assertEqual(decision['selected'],'v4_default')
